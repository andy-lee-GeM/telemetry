#!/usr/bin/env python3
"""
Simple TDMS to Database/CSV Processor
Processes TDMS files with configurable sample rate, duration, and output format
"""

import sys
import os
import argparse
import logging
import csv
import json
import nptdms
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional, Dict

# Add project root to Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from clients.telemetry_utils import TelemetryReading, insert_telemetry_batch

# ============================================================================
# CONFIGURATION
# ============================================================================

DEFAULT_HZ = 10.0
DEFAULT_MAX_DURATION_HOURS = 12.0

# ============================================================================
# LOGGING
# ============================================================================

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger('TDMSProcessor')

# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def get_sensor_name(channel_name: str) -> str:
    """Convert TDMS channel name to standardized sensor name"""
    mapping = {
        'Ground accel X': 'ground_accel_x',
        'Ground accel Y': 'ground_accel_y',
        'Ground accel Z': 'ground_accel_z',
        'Ground accel X RMS': 'ground_accel_x_rms',
        'Ground accel Y RMS': 'ground_accel_y_rms',
        'Ground accel Z RMS': 'ground_accel_z_rms',
        'Lower bearing load X': 'lower_bearing_load_x',
        'Lower bearing load Y': 'lower_bearing_load_y',
        'Lower bearing load Z': 'lower_bearing_load_z',
        'Upper bearing load X': 'upper_bearing_load_x',
        'Upper bearing load Y': 'upper_bearing_load_y',
        'Upper bearing load Z': 'upper_bearing_load_z',
        'Lower bearing temp 1': 'lower_bearing_temp_1',
        'Lower bearing temp 2': 'lower_bearing_temp_2',
        'Lower bearing temp 3': 'lower_bearing_temp_3',
        'Upper Bearing Position X': 'upper_bearing_pos_x',
        'Upper Bearing Position Y': 'upper_bearing_pos_y',
        'Lower Rotor Position X': 'lower_rotor_pos_x',
        'Lower Rotor Position Y': 'lower_rotor_pos_y',
        'Upper Rotor Position X': 'upper_rotor_pos_x',
        'Upper Rotor Position Y': 'upper_rotor_pos_y',
        'Stator temp 1': 'stator_temp_1',
        'Stator temp 2': 'stator_temp_2',
        'Tachometer': 'tachometer'
    }
    return mapping.get(channel_name, channel_name.lower().replace(' ', '_'))

def get_unit(sensor_name: str) -> str:
    """Get unit for sensor based on name"""
    if 'temp' in sensor_name:
        return '°C'
    elif 'accel' in sensor_name:
        return 'g'
    elif 'load' in sensor_name:
        return 'kgf'
    elif 'pos' in sensor_name:
        return 'mm'
    elif 'tach' in sensor_name:
        return 'rpm'
    return ''

def calculate_max_samples(target_hz: float, max_duration_hours: float) -> int:
    """Calculate maximum samples based on target rate and duration"""
    return int(target_hz * max_duration_hours * 3600)

def downsample_with_averaging(data: np.ndarray, target_samples: int) -> np.ndarray:
    """Downsample using simple averaging"""
    if len(data) <= target_samples:
        return data
    
    # Calculate block size for averaging
    block_size = len(data) // target_samples
    
    # Trim data to fit evenly into blocks
    trimmed_length = (len(data) // block_size) * block_size
    trimmed_data = data[:trimmed_length]
    
    # Reshape into blocks and average
    blocks = trimmed_data.reshape(-1, block_size)
    return np.mean(blocks, axis=1)

def process_channel(channel, group_name: str, base_timestamp: datetime, filename: str, 
                   target_hz: float, max_samples: int, stats_tracker: Dict) -> List[TelemetryReading]:
    """Process a single channel with downsampling"""
    
    # Get channel data
    try:
        data = channel[:]
    except Exception as e:
        logger.error(f"❌ Error reading channel {channel.name}: {e}")
        return []
    
    # Skip empty or non-numeric data
    if len(data) == 0 or not np.issubdtype(data.dtype, np.number):
        logger.debug(f"Skipping {channel.name}: empty or non-numeric")
        return []
    
    original_samples = len(data)
    sensor_name = get_sensor_name(channel.name)
    unit = get_unit(sensor_name)
    
    logger.info(f"   📊 {sensor_name}: {original_samples:,} samples")
    
    # Calculate statistics on original data
    data_stats = {
        'min': float(np.min(data)),
        'max': float(np.max(data)),
        'mean': float(np.mean(data)),
        'median': float(np.median(data)),
        'std': float(np.std(data))
    }
    
    # Downsample if needed
    if original_samples > max_samples:
        data = downsample_with_averaging(data, max_samples)
        logger.info(f"   📉 Downsampled: {original_samples:,} → {len(data):,} samples")
    
    # Track statistics
    stats_tracker['channels'].append({
        'channel': sensor_name,
        'original_channel': channel.name,
        'total_points': original_samples,
        'downsampled_points': len(data),
        'reduction_ratio': len(data) / original_samples if original_samples > 0 else 0,
        'unit': unit,
        'min': data_stats['min'],
        'max': data_stats['max'],
        'mean': data_stats['mean'],
        'median': data_stats['median'],
        'std': data_stats['std']
    })
    
    # Convert to TelemetryReading objects
    readings = []
    time_delta = timedelta(seconds=1.0 / target_hz)
    
    for i, value in enumerate(data):
        timestamp = base_timestamp + (i * time_delta)
        
        # Track earliest and latest timestamps
        if 'start_time' not in stats_tracker or timestamp < stats_tracker['start_time']:
            stats_tracker['start_time'] = timestamp
        if 'end_time' not in stats_tracker or timestamp > stats_tracker['end_time']:
            stats_tracker['end_time'] = timestamp
        
        metadata = {
            'source': 'ni_cdaq',
            'group': group_name,
            'original_channel': channel.name,
            'sample_rate': target_hz,
            'file': filename,
            'original_samples': original_samples,
            'downsampled_samples': len(data),
            'unit': unit
        }
        
        readings.append(TelemetryReading(
            timestamp=timestamp,
            sensor=sensor_name,
            value=float(value),
            metadata=metadata
        ))
    
    return readings

# ============================================================================
# OUTPUT FUNCTIONS
# ============================================================================

def write_to_csv(readings: List[TelemetryReading], output_file: str) -> dict:
    """Write readings to CSV file"""
    
    if not readings:
        logger.warning("⚠️ No readings to write to CSV")
        return {"success": 0, "errors": 0}
    
    logger.info(f"📝 Writing {len(readings):,} readings to CSV: {output_file}")
    
    try:
        with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = ['timestamp', 'sensor', 'value', 'unit', 'group', 'original_channel', 'sample_rate', 'file']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            
            # Write header
            writer.writeheader()
            
            # Write data rows
            for reading in readings:
                writer.writerow({
                    'timestamp': reading.timestamp.isoformat(),
                    'sensor': reading.sensor,
                    'value': reading.value,
                    'unit': reading.metadata.get('unit', ''),
                    'group': reading.metadata.get('group', ''),
                    'original_channel': reading.metadata.get('original_channel', ''),
                    'sample_rate': reading.metadata.get('sample_rate', ''),
                    'file': reading.metadata.get('file', '')
                })
        
        logger.info(f"✅ CSV file written successfully: {output_file}")
        return {"success": len(readings), "errors": 0}
        
    except Exception as e:
        logger.error(f"❌ Error writing CSV: {e}")
        return {"success": 0, "errors": 1}

def write_to_database(readings: List[TelemetryReading]) -> dict:
    """Write readings to database"""
    
    if not readings:
        logger.warning("⚠️ No readings to write to database")
        return {"success": 0, "errors": 0}
    
    logger.info(f"💾 Writing {len(readings):,} readings to database...")
    return insert_telemetry_batch(readings, "NI-DAQ", "cDAQ", logger)

def format_value(value: float, unit: str) -> str:
    """Format value with appropriate precision based on unit"""
    if unit == '°C':
        return f"{value:.2f}"
    elif unit == 'g':
        return f"{value:.4f}"
    elif unit == 'kgf':
        return f"{value:.6f}"
    elif unit == 'mm':
        return f"{value:.3f}"
    elif unit == 'rpm':
        return f"{value:.1f}"
    else:
        return f"{value:.4f}"

def print_summary_statistics(stats_tracker: Dict, target_hz: float, max_duration_hours: float):
    """Print comprehensive summary statistics"""
    
    print("\n" + "=" * 100)
    print("📊 PROCESSING SUMMARY")
    print("=" * 100)
    
    # Processing parameters
    print(f"⚙️  Processing Parameters:")
    print(f"   Target sample rate: {target_hz} Hz")
    print(f"   Max duration: {max_duration_hours} hours")
    print(f"   Max samples per channel: {calculate_max_samples(target_hz, max_duration_hours):,}")
    
    # Time information
    if 'start_time' in stats_tracker and 'end_time' in stats_tracker:
        start_time = stats_tracker['start_time']
        end_time = stats_tracker['end_time']
        duration = end_time - start_time
        
        print(f"\n⏱️  Time Information:")
        print(f"   Start time: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"   End time: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"   Total duration: {duration.total_seconds():.1f} seconds ({duration.total_seconds()/3600:.2f} hours)")
    
    if not stats_tracker['channels']:
        print("   No channels processed")
        return
    
    # Channel processing statistics
    print(f"\n📈 Channel Processing Statistics:")
    print(f"{'Channel':<25} {'Original':<10} {'Downsampled':<11} {'Reduction':<9}")
    print("-" * 60)
    
    total_original = 0
    total_downsampled = 0
    
    for channel_stats in stats_tracker['channels']:
        channel = channel_stats['channel']
        original = channel_stats['total_points']
        downsampled = channel_stats['downsampled_points']
        reduction = channel_stats['reduction_ratio']
        
        total_original += original
        total_downsampled += downsampled
        
        print(f"{channel:<25} {original:>9,} {downsampled:>10,} {reduction:>8.1%}")
    
    print("-" * 60)
    print(f"{'TOTAL':<25} {total_original:>9,} {total_downsampled:>10,} {total_downsampled/total_original:>8.1%}")
    
    # Channel data statistics
    print(f"\n📊 Channel Data Statistics:")
    print(f"{'Channel':<25} {'Unit':<5} {'Min':<12} {'Max':<12} {'Mean':<12} {'Median':<12}")
    print("-" * 85)
    
    for channel_stats in stats_tracker['channels']:
        channel = channel_stats['channel']
        unit = channel_stats['unit']
        min_val = format_value(channel_stats['min'], unit)
        max_val = format_value(channel_stats['max'], unit)
        mean_val = format_value(channel_stats['mean'], unit)
        median_val = format_value(channel_stats['median'], unit)
        
        print(f"{channel:<25} {unit:<5} {min_val:<12} {max_val:<12} {mean_val:<12} {median_val:<12}")
    
    # Overall summary
    print(f"\n📋 Overall Summary:")
    print(f"   Channels processed: {len(stats_tracker['channels'])}")
    print(f"   Total original samples: {total_original:,}")
    print(f"   Total downsampled samples: {total_downsampled:,}")
    print(f"   Overall reduction: {total_downsampled/total_original:.1%}")
    print(f"   Data compression ratio: {total_original/total_downsampled:.1f}:1")
    
    if 'start_time' in stats_tracker and 'end_time' in stats_tracker:
        duration_hours = (stats_tracker['end_time'] - stats_tracker['start_time']).total_seconds() / 3600
        print(f"   Effective sample rate: {total_downsampled / len(stats_tracker['channels']) / duration_hours:.1f} Hz per channel")

# ============================================================================
# MAIN PROCESSING
# ============================================================================

def process_tdms_file(file_path: str, target_hz: float, max_duration_hours: float, 
                     output_csv: Optional[str] = None, save_to_db: bool = False, dry_run: bool = False) -> dict:
    """Process TDMS file with specified parameters and output options"""
    
    file_path = Path(file_path)
    
    # Validate file
    if not file_path.exists():
        logger.error(f"❌ File not found: {file_path}")
        return {"success": 0, "errors": 1}
    
    if file_path.suffix.lower() != '.tdms':
        logger.error(f"❌ Not a TDMS file: {file_path}")
        return {"success": 0, "errors": 1}
    
    # Calculate limits
    max_samples = calculate_max_samples(target_hz, max_duration_hours)
    base_timestamp = datetime.fromtimestamp(file_path.stat().st_mtime)
    
    # Initialize statistics tracker
    stats_tracker = {'channels': []}
    
    logger.info(f"🔍 Processing: {file_path.name}")
    logger.info(f"📊 Target rate: {target_hz} Hz")
    logger.info(f"⏱️  Max duration: {max_duration_hours} hours")
    logger.info(f"📏 Max samples per channel: {max_samples:,}")
    
    if dry_run:
        logger.info("🔍 DRY RUN MODE - No output will be written")
    
    # === STEP 1: Extract and downsample to TelemetryReading objects ===
    all_readings = []
    
    try:
        # Process TDMS file
        with nptdms.TdmsFile.open(str(file_path)) as tdms_file:
            for group in tdms_file.groups():
                # Skip metadata groups
                if group.name in ['Test Information', 'Events_time', 'Events']:
                    continue
                
                logger.info(f"📁 Processing group: {group.name}")
                
                for channel in group.channels():
                    try:
                        readings = process_channel(
                            channel, group.name, base_timestamp, file_path.name, 
                            target_hz, max_samples, stats_tracker
                        )
                        all_readings.extend(readings)
                        
                    except Exception as e:
                        logger.error(f"❌ Error processing {channel.name}: {e}")
                        continue
        
        if not all_readings:
            logger.warning("⚠️ No data extracted from file")
            return {"success": 0, "errors": 0}
        
        logger.info(f"📊 Total readings after processing: {len(all_readings):,}")
        
        # === STEP 2: Output to requested formats ===
        total_success = 0
        total_errors = 0
        
        if dry_run:
            # In dry-run mode, just count the readings as "success"
            total_success = len(all_readings)
            logger.info(f"🔍 DRY RUN: Would process {len(all_readings):,} readings")
        else:
            # Write to CSV if requested
            if output_csv:
                csv_result = write_to_csv(all_readings, output_csv)
                total_success += csv_result["success"]
                total_errors += csv_result["errors"]
            
            # Write to database if requested
            if save_to_db:
                db_result = write_to_database(all_readings)
                total_success += db_result["success"]
                total_errors += db_result["errors"]
            elif not output_csv:
                logger.warning("⚠️ No output specified - use --csv or --save-to-db")
        
        # Print summary statistics (always shown)
        print_summary_statistics(stats_tracker, target_hz, max_duration_hours)
        
        # Log final results
        logger.info("=" * 50)
        logger.info(f"✅ Total success: {total_success:,}")
        logger.info(f"❌ Total errors: {total_errors:,}")
        logger.info("=" * 50)
        
        return {"success": total_success, "errors": total_errors}
        
    except Exception as e:
        logger.error(f"❌ Processing failed: {e}")
        return {"success": 0, "errors": 1}

# ============================================================================
# MAIN SCRIPT
# ============================================================================

def main():
    """Main script with command line arguments"""
    
    parser = argparse.ArgumentParser(
        description="Process TDMS files into CSV and/or database",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    
    parser.add_argument(
        'file_path', 
        help='Path to TDMS file to process'
    )
    
    parser.add_argument(
        '--hz', 
        type=float, 
        default=DEFAULT_HZ,
        help='Target sample rate in Hz'
    )
    
    parser.add_argument(
        '--max-duration', 
        type=float, 
        default=DEFAULT_MAX_DURATION_HOURS,
        help='Maximum duration in hours'
    )
    
    parser.add_argument(
        '--csv', 
        type=str,
        help='Output CSV file path (optional)'
    )
    
    parser.add_argument(
        '--save-to-db', 
        action='store_true',
        help='Save processed data to database'
    )

    parser.add_argument(
        '--dry-run', 
        action='store_true',
        help='Process file and show statistics without writing output'
    )
    
    parser.add_argument(
        '--verbose', '-v', 
        action='store_true',
        help='Enable verbose logging'
    )
    
    args = parser.parse_args()
    
    # Set logging level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Validate output options
    if not args.dry_run and not args.save_to_db and not args.csv:
        logger.error("❌ Must specify at least one output: --csv, --save-to-db, or --dry-run")
        sys.exit(1)
    
    # Process file
    result = process_tdms_file(
        args.file_path, 
        args.hz, 
        args.max_duration,
        output_csv=args.csv,
        save_to_db=args.save_to_db,
        dry_run=args.dry_run
    )
    
    if result['success'] == 0:
        sys.exit(1)

if __name__ == "__main__":
    main() 