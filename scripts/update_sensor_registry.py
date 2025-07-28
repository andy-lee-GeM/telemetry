#!/usr/bin/env python3
"""
Update Sensor Registry - Automatically registers new sensors found in TDMS files
"""

import psycopg2
from psycopg2.extras import execute_values
import logging
from typing import Dict, List, Tuple

# Database configuration
DB_CONFIG = {
    'host': '169.254.77.77',
    'port': 5433,
    'database': 'telemetry',
    'user': 'admin',
    'password': 'admin'
}

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('SensorRegistry')


def extract_unit_from_metadata(channel_properties: Dict) -> str:
    """Extract unit from TDMS channel properties"""
    # Direct unit_string property
    if 'unit_string' in channel_properties:
        return channel_properties['unit_string']
    
    # For calculated channels without units
    return ''


def determine_team_from_sensor(sensor_name: str, group_name: str) -> str:
    """Determine team ownership based on sensor naming patterns"""
    sensor_lower = sensor_name.lower()
    
    # Facilities team patterns
    if any(pattern in sensor_lower for pattern in ['vacuum', 'pressure', 'flow']):
        return 'facilities'
    
    # Maker team patterns (NI-DAQ sensors)
    if any(pattern in sensor_lower for pattern in ['temp_', 'lc_', 'accel_', 'position_']):
        return 'maker'
    
    # Default based on group
    return 'maker' if group_name == 'Log' else 'facilities'


def update_sensor_registry(new_sensors: List[Tuple[str, str, str]]) -> int:
    """Update sensors table with new sensor metadata"""
    
    if not new_sensors:
        logger.info("No new sensors to register")
        return 0
    
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        # Insert new sensors, ignoring conflicts
        execute_values(
            cursor,
            """
            INSERT INTO sensors (sensor, units, team)
            VALUES %s
            ON CONFLICT (sensor) DO UPDATE SET
                units = COALESCE(EXCLUDED.units, sensors.units),
                team = COALESCE(EXCLUDED.team, sensors.team)
            """,
            new_sensors,
            template="(%s, %s, %s)"
        )
        
        records_affected = cursor.rowcount
        conn.commit()
        
        logger.info(f"✅ Updated sensor registry: {records_affected} sensors")
        return records_affected
        
    except Exception as e:
        logger.error(f"Failed to update sensor registry: {e}")
        return 0
    finally:
        if 'conn' in locals():
            conn.close()


def check_unregistered_sensors() -> List[str]:
    """Find sensors in telemetry table that aren't in sensors table"""
    
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT DISTINCT t.sensor
            FROM telemetry t
            LEFT JOIN sensors s ON t.sensor = s.sensor
            WHERE s.sensor IS NULL
            ORDER BY t.sensor
        """)
        
        unregistered = [row[0] for row in cursor.fetchall()]
        
        if unregistered:
            logger.warning(f"Found {len(unregistered)} unregistered sensors:")
            for sensor in unregistered:
                logger.warning(f"  - {sensor}")
        
        return unregistered
        
    except Exception as e:
        logger.error(f"Failed to check unregistered sensors: {e}")
        return []
    finally:
        if 'conn' in locals():
            conn.close()


if __name__ == "__main__":
    # Check for unregistered sensors
    unregistered = check_unregistered_sensors()
    
    if unregistered:
        # For now, register them with empty units and 'maker' team
        # In production, you'd parse these from TDMS metadata
        new_sensors = [(sensor, '', 'maker') for sensor in unregistered]
        update_sensor_registry(new_sensors)