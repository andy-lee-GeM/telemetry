#!/usr/bin/env python3
"""
Fast TDMS to Database Processor
Optimized for maximum throughput using PostgreSQL COPY and bulk operations
"""

import argparse
import logging
import sys
import io
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Generator, Dict, List, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
import tempfile
import csv

import nptdms
import numpy as np
import psycopg2
from psycopg2.extras import execute_values
from tqdm import tqdm

# Add project root to Python path
import os
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from utils.downsampling_utils import downsample, calculate_max_samples_from_hz

# Configuration
DB_CONFIG = {
    'host': '169.254.77.77',
    'port': 5433,
    'database': 'telemetry',
    'user': 'admin',
    'password': 'admin'
}

# Optimized settings
CHUNK_SIZE = 1000000  # Samples per chunk
BATCH_SIZE = 100000    # Records per database batch
MAX_WORKERS = 6         # Parallel workers (leave some CPU for DB)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('FastTDMSProcessor')


class FastDatabaseWriter:
    """High-performance database writer using execute_values (simpler than COPY)"""
    
    def __init__(self, connection):
        self.conn = connection
        self.cursor = connection.cursor()
        self.buffer = []
        
    def add_records(self, records: List[Tuple]) -> None:
        """Add records to buffer"""
        self.buffer.extend(records)
    
    def flush_to_database(self) -> int:
        """Flush buffered records to database using execute_values"""
        if not self.buffer:
            return 0
            
        # Convert metadata dicts to JSON strings for database
        import json
        processed_records = []
        for record in self.buffer:
            ts, source, sensor, value, metadata_dict = record
            processed_record = (
                ts, source, sensor, value, 
                json.dumps(metadata_dict)
            )
            processed_records.append(processed_record)
            
        # Use execute_values for bulk insert (faster than individual INSERTs)
        from psycopg2.extras import execute_values
        
        execute_values(
            self.cursor,
            """
            INSERT INTO telemetry (ts, source, sensor, value, metadata)
            VALUES %s
            ON CONFLICT (ts, source, sensor) DO UPDATE SET
                value = EXCLUDED.value,
                metadata = EXCLUDED.metadata,
                ingest_ts = NOW()
            """,
            processed_records,
            template="(%s, %s, %s, %s, %s)",
            page_size=1000
        )
        
        records_written = len(self.buffer)
        self.buffer = []
        return records_written


def process_channel_fast(channel, group_name: str, base_timestamp: datetime,
                        filename: str, target_hz: float, max_samples: int,
                        downsample_method: str) -> Generator[List[Tuple], None, Dict]:
    """
    Fast channel processing that yields raw tuples for COPY
    """
    try:
        total_samples = len(channel)
        if total_samples == 0:
            return {'processed': 0, 'output': 0, 'channel': channel.name}
        
        # Check if data is numeric
        sample = channel[0:1]
        if not np.issubdtype(sample.dtype, np.number):
            return {'processed': 0, 'output': 0, 'channel': channel.name}
        
        # Calculate chunking strategy
        needs_downsampling = total_samples > max_samples
        if needs_downsampling:
            downsample_ratio = total_samples / max_samples
            read_chunk_size = min(int(CHUNK_SIZE * downsample_ratio), total_samples)
        else:
            read_chunk_size = min(CHUNK_SIZE, total_samples)
        
        # Pre-calculate metadata dict (will be JSON-serialized at insert time)
        metadata_dict = {
            'group': group_name,
            'file': filename,
            'sample_rate': target_hz,
            'original_samples': total_samples,
            'downsampled': needs_downsampling
        }
        
        time_delta_seconds = 1.0 / target_hz
        output_count = 0
        sample_index = 0
        
        # Process in chunks
        for start_idx in range(0, total_samples, read_chunk_size):
            end_idx = min(start_idx + read_chunk_size, total_samples)
            
            # Read chunk efficiently
            chunk_data = channel[start_idx:end_idx]
            
            # Downsample if needed
            if needs_downsampling:
                target_chunk_samples = int(len(chunk_data) / downsample_ratio)
                if target_chunk_samples > 0:
                    chunk_data = downsample(chunk_data, target_chunk_samples, downsample_method)
            
            # Create raw tuples (no Python objects)
            records = []
            for value in chunk_data:
                timestamp = base_timestamp + timedelta(seconds=sample_index * time_delta_seconds)
                records.append((
                    timestamp,
                    'NI-DAQ',
                    channel.name,
                    float(value),
                    metadata_dict  # Will be JSON-serialized by psycopg2
                ))
                sample_index += 1
            
            output_count += len(records)
            yield records
        
        return {'processed': total_samples, 'output': output_count, 'channel': channel.name}
        
    except Exception as e:
        logger.error(f"Error processing {channel.name}: {e}")
        return {'processed': 0, 'output': 0, 'channel': channel.name}




def process_tdms_file_fast(file_path: str, target_hz: float = 10.0,
                          max_duration_hours: float = 12.0,
                          downsample_method: str = 'decimation',
                          parallel: bool = True) -> Dict:
    """Fast TDMS processing with optimized database writes"""
    
    # Validate file
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")
    if path.suffix.lower() != '.tdms':
        raise ValueError(f"Not a TDMS file: {file_path}")
    
    # Setup
    base_timestamp = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    max_samples = calculate_max_samples_from_hz(target_hz, max_duration_hours)
    
    logger.info(f"Processing {path.name}")
    logger.info(f"Target: {target_hz} Hz for {max_duration_hours} hours = {max_samples:,} samples/channel")
    logger.info(f"Parallel processing: {'enabled' if parallel else 'disabled'}")
    
    # Database connection
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        conn.autocommit = False  # Use transactions for speed
        db_writer = FastDatabaseWriter(conn)
        logger.info("Database connection established")
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        return {'channels': 0, 'records': 0, 'errors': 1}
    
    stats = {
        'channels': 0,
        'records': 0,
        'errors': 0,
        'original_samples': 0,
        'output_samples': 0
    }
    
    try:
        # Open TDMS with memory mapping
        with tempfile.TemporaryDirectory() as temp_dir:
            logger.info("Opening TDMS file...")
            tdms_file = nptdms.TdmsFile.read(str(path), memmap_dir=temp_dir)
            
            # Get data channels
            logger.info("Scanning channels...")
            skip_groups = ['Test Information', 'Events_time', 'Events']
            channels = [
                (group.name, channel)
                for group in tdms_file.groups()
                if group.name not in skip_groups
                for channel in group.channels()
            ]
            
            logger.info(f"Found {len(channels)} data channels")
            logger.info("Starting optimized processing...")
            
            # Process channels
            if parallel and len(channels) > 1:
                # Parallel processing - simplified approach
                logger.info("Using parallel processing...")
                
                def process_single_channel(channel_info):
                    """Process a single channel and return all records"""
                    group_name, channel = channel_info
                    all_records = []
                    channel_stats = {'processed': 0, 'output': 0, 'channel': channel.name}
                    
                    try:
                        generator = process_channel_fast(
                            channel, group_name, base_timestamp, path.name,
                            target_hz, max_samples, downsample_method
                        )
                        
                        # Collect all records
                        try:
                            while True:
                                records = next(generator)
                                all_records.extend(records)
                        except StopIteration as e:
                            if hasattr(e, 'value') and e.value:
                                channel_stats = e.value
                                
                    except Exception as e:
                        logger.error(f"Error processing {channel.name}: {e}")
                        channel_stats['error'] = str(e)
                    
                    return channel_stats, all_records
                
                # Process in batches
                with tqdm(total=len(channels), desc="Processing channels") as pbar:
                    batch_size = MAX_WORKERS
                    for i in range(0, len(channels), batch_size):
                        batch = channels[i:i + batch_size]
                        
                        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                            future_to_channel = {
                                executor.submit(process_single_channel, ch): ch[1].name 
                                for ch in batch
                            }
                            
                            for future in as_completed(future_to_channel):
                                channel_name = future_to_channel[future]
                                try:
                                    channel_stats, records = future.result()
                                    
                                    if records:
                                        db_writer.add_records(records)
                                        stats['records'] += len(records)
                                        
                                        # Flush periodically
                                        if len(db_writer.buffer) >= BATCH_SIZE:
                                            written = db_writer.flush_to_database()
                                            conn.commit()
                                    
                                    # Update stats
                                    stats['channels'] += 1
                                    if 'processed' in channel_stats:
                                        stats['original_samples'] += channel_stats['processed']
                                        stats['output_samples'] += channel_stats['output']
                                    
                                    if 'error' in channel_stats:
                                        stats['errors'] += 1
                                        
                                except Exception as e:
                                    logger.error(f"Error collecting results for {channel_name}: {e}")
                                    stats['errors'] += 1
                                
                                pbar.update(1)
                                pbar.set_postfix({
                                    'channel': channel_name[:20],
                                    'records': f"{stats['records']:,}"
                                })
                        
            else:
                # Sequential processing (fallback)
                with tqdm(total=len(channels), desc="Processing channels") as pbar:
                    for group_name, channel in channels:
                        generator = process_channel_fast(
                            channel, group_name, base_timestamp, path.name,
                            target_hz, max_samples, downsample_method
                        )
                        
                        try:
                            for records in generator:
                                if records:
                                    db_writer.add_records(records)
                                    stats['records'] += len(records)
                                    
                                    # Flush periodically
                                    if len(db_writer.buffer) >= BATCH_SIZE:
                                        written = db_writer.flush_to_database()
                                        conn.commit()
                                        
                        except StopIteration as e:
                            if hasattr(e, 'value'):
                                channel_stats = e.value
                                stats['channels'] += 1
                                stats['original_samples'] += channel_stats['processed']
                                stats['output_samples'] += channel_stats['output']
                        
                        pbar.update(1)
                        pbar.set_postfix({
                            'channel': channel.name[:20],
                            'records': f"{stats['records']:,}"
                        })
            
            # Final flush
            if len(db_writer.buffer) > 0:
                written = db_writer.flush_to_database()
                conn.commit()
                
            logger.info(f"✅ Processed {stats['channels']} channels, {stats['records']:,} records")
            
            if stats['original_samples'] > 0:
                reduction = 1 - (stats['output_samples'] / stats['original_samples'])
                logger.info(f"📊 Data reduction: {reduction:.1%}")
    
    except Exception as e:
        logger.error(f"Processing failed: {e}")
        conn.rollback()
        stats['errors'] += 1
    
    finally:
        conn.close()
    
    return stats


def main():
    parser = argparse.ArgumentParser(
        description="Fast TDMS to database processor with bulk operations"
    )
    
    parser.add_argument('file', help='TDMS file path')
    parser.add_argument('--hz', type=float, default=1.0,
                       help='Target sample rate in Hz (default: 1.0)')
    parser.add_argument('--hours', type=float, default=12.0,
                       help='Maximum duration in hours (default: 12)')
    parser.add_argument('--method', choices=['decimation', 'averaging'],
                       default='decimation',
                       help='Downsampling method (default: decimation)')
    parser.add_argument('--no-parallel', action='store_true',
                       help='Disable parallel processing')
    
    args = parser.parse_args()
    
    try:
        result = process_tdms_file_fast(
            args.file,
            target_hz=args.hz,
            max_duration_hours=args.hours,
            downsample_method=args.method,
            parallel=not args.no_parallel
        )
        
        if result['errors'] > 0:
            sys.exit(1)
            
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()