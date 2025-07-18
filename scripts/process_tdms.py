#!/usr/bin/env python3
"""
TDMS File Processor - Clean and Simple
Process TDMS files with explicit downsampling and output options
"""

import argparse
import csv
import logging
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List

import nptdms
import numpy as np
from tqdm import tqdm
import json

# Add project root to Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from clients.telemetry_utils import TelemetryReading
from utils.downsampling_utils import downsample, calculate_max_samples_from_hz

# ============================================================================
# DATABASE CONFIGURATION
# ============================================================================

# Database configuration
DB_CONFIG = {
    'host': '169.254.77.77',
    'port': 5433,
    'database': 'telemetry',
    'user': 'admin',
    'password': 'admin'
}

# Build connection string from config
CENTRAL_DB_URL = f"postgresql://{DB_CONFIG['user']}:{DB_CONFIG['password']}@{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}"

def test_database_connection() -> bool:
    """Test database connection before processing"""
    try:
        from sqlalchemy import create_engine, text
        from sqlalchemy.orm import sessionmaker
        
        logger.info(f"🔍 Testing database connection to {DB_CONFIG['host']}:{DB_CONFIG['port']}")
        
        engine = create_engine(CENTRAL_DB_URL)
        Session = sessionmaker(bind=engine)
        session = Session()
        
        # Test connection
        result = session.execute(text("SELECT 1 as test"))
        test_value = result.fetchone()[0]
        
        if test_value == 1:
            logger.info("✅ Database connection successful!")
            session.close()
            return True
        else:
            logger.error("❌ Unexpected database test result")
            session.close()
            return False
            
    except Exception as e:
        logger.error(f"❌ Database connection failed: {e}")
        return False

# ============================================================================
# LOGGING SETUP
# ============================================================================

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger('TDMSProcessor')

# ============================================================================
# FILE VALIDATION
# ============================================================================

def validate_tdms_file(file_path: str) -> Path:
    """Validate TDMS file exists and has correct extension"""
    path = Path(file_path)
    
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")
    
    if path.suffix.lower() != '.tdms':
        raise ValueError(f"Not a TDMS file: {file_path}")
    
    return path

# ============================================================================
# CHANNEL PROCESSING
# ============================================================================

def get_data_channels(tdms_file) -> List[tuple]:
    """Extract data channels from TDMS file, skipping metadata groups"""
    skip_groups = ['Test Information', 'Events_time', 'Events']
    channels = []
    
    for group in tdms_file.groups():
        if group.name not in skip_groups:
            for channel in group.channels():
                channels.append((group.name, channel))
    
    return channels

def process_single_channel(channel, group_name: str, base_timestamp: datetime, 
                          filename: str, target_hz: float, max_samples: int, 
                          downsample_method: str) -> List[TelemetryReading]:
    """Process a single channel and return TelemetryReading objects"""
    
    try:
        # Get channel data
        data = channel[:]
        
        if len(data) == 0 or not np.issubdtype(data.dtype, np.number):
            logger.debug(f"Skipping {channel.name}: empty or non-numeric data")
            return []
        
        original_samples = len(data)
        logger.info(f"📊 {channel.name}: {original_samples:,} samples")
        
        # Apply downsampling if needed
        if original_samples > max_samples:
            data = downsample(data, max_samples, downsample_method)
            logger.info(f"📉 Downsampled: {original_samples:,} → {len(data):,} samples")
        
        # Convert to TelemetryReading objects
        readings = create_telemetry_readings(
            data, channel.name, group_name, base_timestamp, 
            filename, target_hz, original_samples
        )
        
        return readings
        
    except Exception as e:
        logger.error(f"❌ Error processing {channel.name}: {e}")
        return []

def create_telemetry_readings(data: np.ndarray, sensor_name: str, group_name: str, 
                            base_timestamp: datetime, filename: str, target_hz: float, 
                            original_samples: int) -> List[TelemetryReading]:
    """Convert numpy array to TelemetryReading objects"""
    
    readings = []
    time_delta = timedelta(seconds=1.0 / target_hz)
    
    for i, value in enumerate(data):
        timestamp = base_timestamp + (i * time_delta)
        
        reading = TelemetryReading(
            timestamp=timestamp,
            sensor=sensor_name,
            value=float(value),
            metadata={
                'group': group_name,
                'file': filename,
                'sample_rate': target_hz,
                'original_samples': original_samples,
                'downsampled_samples': len(data)
            }
        )
        readings.append(reading)
    
    return readings

# ============================================================================
# OUTPUT HANDLING
# ============================================================================

def write_readings_to_csv(readings: List[TelemetryReading], csv_writer) -> int:
    """Write readings to CSV file"""
    count = 0
    try:
        for reading in readings:
            csv_writer.writerow({
                'timestamp': reading.timestamp.isoformat(),
                'sensor': reading.sensor,
                'value': reading.value,
                'group': reading.metadata.get('group', ''),
                'file': reading.metadata.get('file', '')
            })
            count += 1
    except Exception as e:
        logger.error(f"❌ CSV write error: {e}")
    
    return count

def write_readings_to_database(readings: List[TelemetryReading]) -> dict:
    """Write readings to database using configured connection"""
    if not readings:
        return {"success": 0, "errors": 0}
    
    logger.info(f"💾 Writing {len(readings):,} readings to database at {DB_CONFIG['host']}:{DB_CONFIG['port']}")
    
    try:
        from sqlalchemy import create_engine, text
        from sqlalchemy.orm import sessionmaker
        
        engine = create_engine(CENTRAL_DB_URL)
        Session = sessionmaker(bind=engine)
        session = Session()
        
        # Prepare batch data
        batch_data = []
        for reading in readings:
            metadata = reading.metadata.copy()
            metadata.update({
                'client': 'process_tdms',
                'transfer_time': datetime.now(timezone.utc).isoformat(),
                'source_host': DB_CONFIG['host']
            })
            
            batch_data.append({
                "ts": reading.timestamp,
                "source": "NI-DAQ",
                "sensor": reading.sensor,
                "value": float(reading.value),
                "metadata": json.dumps(metadata)
            })
        
        # Bulk insert with executemany
        session.execute(text("""
            INSERT INTO telemetry (ts, source, sensor, value, metadata)
            VALUES (:ts, :source, :sensor, :value, :metadata)
            ON CONFLICT (ts, source, sensor) DO UPDATE SET
                value = EXCLUDED.value,
                metadata = EXCLUDED.metadata,
                ingest_ts = NOW()
        """), batch_data)
        
        session.commit()
        session.close()
        
        result = {"success": len(readings), "errors": 0}
        logger.info(f"✅ Database write complete: {result['success']:,} records inserted")
        return result
        
    except Exception as e:
        logger.error(f"❌ Database operation failed: {e}")
        return {"success": 0, "errors": len(readings)}

# ============================================================================
# MAIN PROCESSING
# ============================================================================

def process_tdms_file(file_path: str, target_hz: float, max_duration_hours: float, 
                     output_csv: str = None, save_to_db: bool = False, 
                     dry_run: bool = False, downsample_method: str = 'decimation') -> dict:
    """Main processing function"""
    
    # Validate input
    path = validate_tdms_file(file_path)
    base_timestamp = datetime.fromtimestamp(path.stat().st_mtime)
    
    # Test database connection if needed
    if save_to_db and not dry_run:
        logger.info("🔍 Validating database connection...")
        if not test_database_connection():
            logger.error("❌ Database connection failed. Cannot proceed with --save-to-db option.")
            return {"success": 0, "errors": 1}
        logger.info("✅ Database connection validated")
    
    # Calculate max samples from Hz and duration
    max_samples = calculate_max_samples_from_hz(target_hz, max_duration_hours)
    logger.info(f"📊 Target: {target_hz} Hz for {max_duration_hours} hours = {max_samples:,} max samples per channel")
    
    # Setup CSV output
    csv_file = None
    csv_writer = None
    if output_csv and not dry_run:
        csv_file = open(output_csv, 'w', newline='', encoding='utf-8')
        fieldnames = ['timestamp', 'sensor', 'value', 'group', 'file']
        csv_writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        csv_writer.writeheader()
    
    total_success = 0
    total_errors = 0
    
    try:
        # Process file with memory mapping for large files
        with tempfile.TemporaryDirectory() as temp_dir:
            logger.info(f"📁 Processing {path.name} with memory mapping")
            
            # Use memory mapping for efficient processing
            tdms_file = nptdms.TdmsFile.read(str(path), memmap_dir=temp_dir)
            
            # Get all data channels
            data_channels = get_data_channels(tdms_file)
            logger.info(f"📊 Found {len(data_channels)} data channels")
            
            # Process each channel
            with tqdm(total=len(data_channels), desc="Processing channels") as pbar:
                for group_name, channel in data_channels:
                    
                    # Process this channel
                    readings = process_single_channel(
                        channel, group_name, base_timestamp, path.name,
                        target_hz, max_samples, downsample_method
                    )
                    
                    # Handle output
                    if readings and not dry_run:
                        # Write to CSV
                        if csv_writer:
                            csv_count = write_readings_to_csv(readings, csv_writer)
                            total_success += csv_count
                        
                        # Write to database
                        if save_to_db:
                            db_result = write_readings_to_database(readings)
                            total_success += db_result["success"]
                            total_errors += db_result["errors"]
                    
                    elif readings:  # dry run
                        total_success += len(readings)
                    
                    # Update progress
                    pbar.set_postfix({'channel': channel.name[:20]})
                    pbar.update(1)
        
        # Close CSV file
        if csv_file:
            csv_file.close()
        
        # Summary
        logger.info(f"✅ Processed {total_success:,} readings with {total_errors} errors")
        return {"success": total_success, "errors": total_errors}
        
    except Exception as e:
        logger.error(f"❌ Processing failed: {e}")
        if csv_file:
            csv_file.close()
        return {"success": 0, "errors": 1}

# ============================================================================
# COMMAND LINE INTERFACE
# ============================================================================

def create_argument_parser():
    """Create and configure argument parser"""
    parser = argparse.ArgumentParser(
        description="Process TDMS files with downsampling",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    
    parser.add_argument('file_path', help='Path to TDMS file')
    parser.add_argument('--hz', type=float, default=10.0, help='Target sample rate (Hz)')
    parser.add_argument('--max-duration', type=float, default=12.0, help='Maximum duration (hours)')
    parser.add_argument('--csv', help='Output CSV file path')
    parser.add_argument('--save-to-db', action='store_true', help='Save to database')
    parser.add_argument('--dry-run', action='store_true', help='Show stats only, no output')
    parser.add_argument('--method', choices=['decimation', 'averaging'], 
                       default='decimation', help='Downsampling method')
    parser.add_argument('--test-db', action='store_true', help='Test database connection and exit')
    
    return parser

def validate_arguments(args):
    """Validate command line arguments"""
    if not any([args.dry_run, args.save_to_db, args.csv]):
        raise ValueError("Must specify at least one output: --csv, --save-to-db, or --dry-run")

def main():
    """Main entry point"""
    parser = create_argument_parser()
    args = parser.parse_args()
    
    try:
        # Handle database connection test
        if args.test_db:
            logger.info("🔍 Testing database connection...")
            if test_database_connection():
                logger.info("✅ Database connection test passed!")
                sys.exit(0)
            else:
                logger.error("❌ Database connection test failed!")
                sys.exit(1)
        
        # Validate arguments
        validate_arguments(args)
        
        # Process file
        result = process_tdms_file(
            file_path=args.file_path,
            target_hz=args.hz,
            max_duration_hours=args.max_duration,
            output_csv=args.csv,
            save_to_db=args.save_to_db,
            dry_run=args.dry_run,
            downsample_method=args.method
        )
        
        # Exit with error code if processing failed
        if result['success'] == 0:
            sys.exit(1)
            
    except Exception as e:
        logger.error(f"❌ {e}")
        sys.exit(1)

if __name__ == "__main__":
    main() 