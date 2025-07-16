#!/usr/bin/env python3
"""
cDAQ Client - On-demand TDMS file processing
Simple client that processes a single TDMS file when triggered
"""

import logging
import nptdms
import numpy as np
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List, Dict, Any

from clients.telemetry_utils import insert_telemetry_batch, TelemetryReading, test_central_connection, get_telemetry_stats

# ============================================================================
# LOGGING SETUP
# ============================================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('cDAQClient')

# ============================================================================
# CDAQ CLIENT CLASS
# ============================================================================

class CDAQClient:
    """Simple cDAQ client for processing TDMS files on-demand"""
    
    def __init__(self):
        # Sensor name mapping from TDMS channels to standardized names
        self.sensor_mapping = {
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
        
        logger.info("🔧 cDAQ Client initialized for on-demand TDMS processing")
    
    def process_tdms_file(self, file_path: str, max_samples_per_channel: int = 1000) -> Dict[str, int]:
        """
        Process a single TDMS file and insert data into telemetry database
        
        Args:
            file_path: Path to the TDMS file to process
            max_samples_per_channel: Maximum samples per channel to avoid memory issues
            
        Returns:
            Dictionary with success/skipped/error counts
        """
        file_path = Path(file_path)
        
        if not file_path.exists():
            logger.error(f"❌ File not found: {file_path}")
            return {"success": 0, "skipped": 0, "errors": 0}
        
        if not file_path.suffix.lower() == '.tdms':
            logger.error(f"❌ Not a TDMS file: {file_path}")
            return {"success": 0, "skipped": 0, "errors": 0}
        
        logger.info(f"🔍 Processing TDMS file: {file_path.name}")
        
        try:
            # Open TDMS file
            tdms_file = nptdms.TdmsFile(str(file_path))
            
            # Use file modification time as base timestamp
            base_timestamp = datetime.fromtimestamp(file_path.stat().st_mtime, tz=timezone.utc)
            
            # Extract readings
            readings = self._extract_readings(tdms_file, base_timestamp, file_path.name, max_samples_per_channel)
            
            if not readings:
                logger.warning("⚠️ No valid readings extracted from TDMS file")
                return {"success": 0, "skipped": 0, "errors": 0}
            
            # Insert into database
            result = insert_telemetry_batch(readings, "NI-DAQ", "cDAQ", logger)
            
            logger.info(f"✅ Processed {file_path.name}: {result['success']} readings inserted")
            return result
            
        except Exception as e:
            logger.error(f"❌ Error processing {file_path.name}: {e}")
            return {"success": 0, "skipped": 0, "errors": 0}
    
    def _extract_readings(self, tdms_file, base_timestamp: datetime, filename: str, 
                         max_samples: int) -> List[TelemetryReading]:
        """Extract readings from TDMS file"""
        readings = []
        
        for group in tdms_file.groups():
            group_name = group.name
            
            # Skip info groups, focus on data groups
            if group_name in ['Test Information', 'Events_time', 'Events']:
                continue
            
            for channel in group.channels():
                channel_name = channel.name
                
                # Skip channels without data
                if not hasattr(channel, 'data') or channel.data is None or len(channel.data) == 0:
                    continue
                
                # Get standardized sensor name
                sensor_name = self.sensor_mapping.get(channel_name, channel_name.lower().replace(' ', '_'))
                
                # Get channel data
                data = channel.data
                
                # Skip non-numeric data
                if not np.issubdtype(data.dtype, np.number):
                    logger.debug(f"Skipping non-numeric channel: {channel_name}")
                    continue
                
                # Estimate sample rate
                sample_rate = self._estimate_sample_rate(len(data))
                
                # Downsample if too many samples
                if len(data) > max_samples:
                    step = len(data) // max_samples
                    data = data[::step]
                    logger.info(f"📉 Downsampled {sensor_name}: {len(data)*step} → {len(data)} samples")
                
                # Create readings
                time_delta = timedelta(seconds=1.0/sample_rate) if sample_rate > 0 else timedelta(seconds=1)
                
                for i, value in enumerate(data):
                    timestamp = base_timestamp + (i * time_delta)
                    
                    # Create metadata
                    metadata = {
                        'source': 'ni_cdaq',
                        'group': group_name,
                        'original_channel': channel_name,
                        'sample_rate': sample_rate,
                        'file': filename,
                        'sample_index': i,
                        'unit': self._get_unit(sensor_name)
                    }
                    
                    readings.append(TelemetryReading(
                        timestamp=timestamp,
                        sensor=sensor_name,
                        value=float(value),
                        metadata=metadata
                    ))
        
        logger.info(f"📊 Extracted {len(readings)} readings from {len(list(tdms_file.groups()))} groups")
        return readings
    
    def _estimate_sample_rate(self, sample_count: int) -> float:
        """Estimate sample rate based on sample count"""
        if sample_count > 100000:
            return 10000.0  # High-frequency (10 kHz)
        elif sample_count > 10000:
            return 1000.0   # Medium-high (1 kHz)
        elif sample_count > 1000:
            return 100.0    # Medium (100 Hz)
        else:
            return 10.0     # Low-frequency (10 Hz)
    
    def _get_unit(self, sensor_name: str) -> str:
        """Get unit for a sensor based on its name"""
        if 'accel' in sensor_name:
            return 'g'
        elif 'load' in sensor_name:
            return 'kgf'
        elif 'temp' in sensor_name:
            return '°C'
        elif 'pos' in sensor_name:
            return 'mm'
        elif 'tach' in sensor_name:
            return 'rpm'
        else:
            return ''
    
    def health_check(self) -> bool:
        """Check if client can connect to database"""
        return test_central_connection(logger)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get telemetry stats for NI-DAQ source"""
        return get_telemetry_stats("NI-DAQ", logger)

# ============================================================================
# COMMAND LINE INTERFACE
# ============================================================================

def main():
    """Main function for command line usage"""
    import sys
    
    if len(sys.argv) != 2:
        print("Usage: python cdaq_client.py <tdms_file_path>")
        sys.exit(1)
    
    tdms_file_path = sys.argv[1]
    
    # Create client and process file
    client = CDAQClient()
    
    # Health check
    if not client.health_check():
        logger.error("❌ Database connection failed")
        sys.exit(1)
    
    # Process file
    result = client.process_tdms_file(tdms_file_path)
    
    # Show results
    if result['success'] > 0:
        print(f"🎉 Successfully processed {tdms_file_path}")
        print(f"📊 Inserted {result['success']} readings")
        
        # Show stats
        stats = client.get_stats()
        print(f"📈 Total NI-DAQ records: {stats['total_count']}")
        if stats['top_sensors']:
            print("🔝 Top sensors:")
            for sensor, count in stats['top_sensors'][:5]:
                print(f"   {sensor}: {count} readings")
    else:
        print(f"❌ Failed to process {tdms_file_path}")
        sys.exit(1)

if __name__ == "__main__":
    main() 