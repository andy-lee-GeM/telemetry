#!/usr/bin/env python3
"""
TDMS Processor - MVP for processing large TDMS files into database
Simple command-line tool that does everything
"""

import sys
import logging
import nptdms
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict

# Import existing utilities
from clients.telemetry_utils import TelemetryReading, insert_telemetry_batch

# ============================================================================
# CONFIGURATION
# ============================================================================

TARGET_SAMPLE_RATE = 10.0  # Hz (0.1s intervals)
MAX_SAMPLES_PER_CHANNEL = 36000  # 1 hour at 10 Hz

# ============================================================================
# LOGGING
# ============================================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('TDMSProcessor')

# ============================================================================
# MAIN PROCESSOR
# ============================================================================

def process_tdms_file(file_path: str) -> Dict:
    """
    Process TDMS file: downsample and insert into database
    
    Returns:
        Dict with success/error counts
    """
    file_path = Path(file_path)
    
    if not file_path.exists():
        logger.error(f"❌ File not found: {file_path}")
        return {"success": 0, "errors": 1}
    
    logger.info(f"🔍 Processing: {file_path.name}")
    logger.info(f"�� Target sample rate: {TARGET_SAMPLE_RATE} Hz")
    
    try:
        # Step 1: Downsample and convert
        readings = downsample_and_convert(file_path)
        
        if not readings:
            logger.warning("⚠️ No data extracted from file")
            return {"success": 0, "errors": 0}
        
        # Step 2: Insert into database
        logger.info(f"📈 Inserting {len(readings)} readings into database...")
        result = insert_telemetry_batch(readings, "NI-DAQ", "cDAQ", logger)
        
        logger.info(f"✅ Processing complete!")
        logger.info(f"   �� Readings inserted: {result['success']}")
        logger.info(f"   ⚠️  Skipped: {result['skipped']}")
        logger.info(f"   ❌ Errors: {result['errors']}")
        
        return result
        
    except Exception as e:
        logger.error(f"❌ Processing failed: {e}")
        return {"success": 0, "errors": 1}

def downsample_and_convert(file_path: Path) -> List[TelemetryReading]:
    """Downsample TDMS file and convert to telemetry readings"""
    
    readings = []
    
    try:
        with nptdms.TdmsFile.open(str(file_path)) as tdms_file:
            # Use file modification time as base timestamp
            base_timestamp = datetime.fromtimestamp(file_path.stat().st_mtime)
            
            # Process each group
            for group in tdms_file.groups():
                logger.info(f"📁 Processing group: {group.name}")
                
                for channel in group.channels():
                    try:
                        channel_readings = process_channel(
                            channel, group.name, base_timestamp, file_path.name
                        )
                        readings.extend(channel_readings)
                        
                    except Exception as e:
                        logger.error(f"❌ Error processing {channel.name}: {e}")
                        continue
    
    except Exception as e:
        logger.error(f"❌ Error opening TDMS file: {e}")
    
    return readings

def process_channel(channel, group_name: str, base_timestamp: datetime, filename: str) -> List[TelemetryReading]:
    """Process a single channel with downsampling"""
    
    # Get channel data length
    total_samples = len(channel[:])
    if total_samples == 0:
        return []
    
    logger.info(f"   📊 {channel.name}: {total_samples:,} samples")
    
    # Calculate downsampling
    target_samples = min(total_samples, MAX_SAMPLES_PER_CHANNEL)
    step = max(1, total_samples // target_samples)
    
    # Downsample using streaming
    downsampled_data = []
    chunk_count = 0
    
    for chunk in channel.data_chunks():
        chunk_data = chunk[:]
        
        if len(chunk_data) == 0:
            continue
        
        # Take every Nth sample from this chunk
        sampled = chunk_data[::step]
        downsampled_data.extend(sampled)
        
        chunk_count += 1
        
        # Limit to target samples
        if len(downsampled_data) >= target_samples:
            break
    
    # Trim to target size
    if len(downsampled_data) > target_samples:
        downsampled_data = downsampled_data[:target_samples]
    
    logger.info(f"   📉 Downsampled: {total_samples:,} → {len(downsampled_data):,} samples")
    
    # Convert to telemetry readings
    readings = []
    time_delta = timedelta(seconds=1.0 / TARGET_SAMPLE_RATE)
    
    # Get sensor name
    sensor_name = channel.name.lower().replace(' ', '_')
    
    # Get unit
    unit = get_unit(sensor_name)
    
    for i, value in enumerate(downsampled_data):
        timestamp = base_timestamp + (i * time_delta)
        
        metadata = {
            'source': 'ni_cdaq',
            'group': group_name,
            'original_channel': channel.name,
            'sample_rate': TARGET_SAMPLE_RATE,
            'file': filename,
            'original_samples': total_samples,
            'downsampled_samples': len(downsampled_data),
            'unit': unit
        }
        
        readings.append(TelemetryReading(
            timestamp=timestamp,
            sensor=sensor_name,
            value=float(value),
            metadata=metadata
        ))
    
    return readings

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
    else:
        return ''

# ============================================================================
# COMMAND LINE INTERFACE
# ============================================================================

def main():
    """Simple command-line interface"""
    
    if len(sys.argv) != 2:
        print("🔧 TDMS Processor - MVP")
        print("")
        print("Usage: python process_tdms.py <tdms_file_path>")
        print("")
        print("Example:")
        print("  python process_tdms.py data/experiment.tdms")
        print("  python process_tdms.py '/path/with spaces/file.tdms'")
        print("")
        print("This will:")
        print("  📉 Downsample to 10 Hz (0.1s intervals)")
        print("  📊 Convert to telemetry format")
        print("  💾 Insert into database")
        print("  📈 Show progress and results")
        sys.exit(1)
    
    file_path = sys.argv[1]
    
    print("🚀 Starting TDMS processing...")
    print("=" * 50)
    
    result = process_tdms_file(file_path)
    
    print("=" * 50)
    if result['success'] > 0:
        print(f"✅ Success! {result['success']} readings inserted")
    else:
        print("❌ Processing failed")
        sys.exit(1)

if __name__ == "__main__":
    main() 