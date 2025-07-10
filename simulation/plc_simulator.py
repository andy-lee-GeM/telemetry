#!/usr/bin/env python3
"""
PLC Data Simulator - Unified Telemetry Schema
Simulates Beckhoff PLC data for unified telemetry system
"""

import time
import random
import math  # Add this import
import json
import psycopg2
from datetime import datetime

class PLCSimulatorReal:
    def __init__(self):
        # Database connection - UNIFIED TELEMETRY DATABASE
        self.db_config = {
            'host': 'localhost',
            'database': 'telemetry',  # Same as NI-DAQ simulator
            'user': 'admin',
            'password': 'admin',
            'port': 5432
        }
        
        # Keep your existing pressure sensor characteristics
        self.pressure_sensors = {
            'ADS.PLC1.GVL_Pressures.P_500_PT_200': {'base': 0.62981, 'range': [0.5, 0.8], 'variation': 0.05},
            'ADS.PLC1.GVL_Pressures.P_200_PT_100': {'base': 1.31194, 'range': [1.0, 1.5], 'variation': 0.08},
            'ADS.PLC1.GVL_Pressures.P_200_PT_200': {'base': 1.42369, 'range': [1.2, 1.7], 'variation': 0.06},
            'ADS.PLC1.GVL_Pressures.P_200_PT_300': {'base': 0.23103, 'range': [0.1, 0.4], 'variation': 0.03},
            'ADS.PLC1.GVL_Pressures.P_300_PT_100': {'base': 2.66895, 'range': [2.0, 3.0], 'variation': 0.15},
            'ADS.PLC1.GVL_Pressures.P_300_PT_200': {'base': 60.10863, 'range': [55.0, 65.0], 'variation': 2.0},
            'ADS.PLC1.GVL_Pressures.P_300_PT_300': {'base': 900.0, 'range': [850.0, 950.0], 'variation': 25.0},
            'ADS.PLC1.GVL_Pressures.P_300_PT_400': {'base': 0.0, 'range': [0.0, 0.1], 'variation': 0.01},
            'ADS.PLC1.GVL_Pressures.P_300_PT_500': {'base': 0.0, 'range': [0.0, 0.1], 'variation': 0.01},
            'ADS.PLC1.GVL_Pressures.P_400_PT_100': {'base': 0.0, 'range': [0.0, 0.1], 'variation': 0.01},
            'ADS.PLC1.GVL_Pressures.P_400_PT_200': {'base': 0.0, 'range': [0.0, 0.1], 'variation': 0.01},
            'ADS.PLC1.GVL_Pressures.P_400_PT_300': {'base': 0.0, 'range': [0.0, 0.1], 'variation': 0.01},
            'ADS.PLC1.GVL_Pressures.P_400_PT_400': {'base': 0.0, 'range': [0.0, 0.1], 'variation': 0.01},
            'ADS.PLC1.GVL_Pressures.P_400_PT_500': {'base': 0.0, 'range': [0.0, 0.1], 'variation': 0.01},
            'ADS.PLC1.GVL_Pressures.P_500_PT_100': {'base': 0.0, 'range': [0.0, 0.1], 'variation': 0.01},
        }
        
        # PLC sampling rate (typically 1-2 Hz for pressure systems)
        self.sample_rate = 1.0  # 1 Hz
        
        # Status quality indicators
        self.quality_states = ['good', 'warning', 'error']
        
    def generate_pressure_reading(self, sensor_name, config):
        """Generate realistic pressure reading with noise and drift"""
        base_value = config['base']
        variation = config['variation']
        min_val, max_val = config['range']
        
        # Add realistic noise and slow drift
        noise = random.uniform(-variation, variation)
        drift = 0.01 * random.uniform(-1, 1)  # Small drift
        
        # Simulate pressure fluctuations
        pressure_wave = variation * 0.3 * math.sin(time.time() * 0.1)  # Slow pressure wave
        
        value = base_value + noise + drift + pressure_wave
        
        # Clamp to realistic range
        value = max(min_val, min(max_val, value))
        
        return round(value, 5)
    
    def get_quality(self):
        """Get random quality (mostly good, occasionally warning/error)"""
        rand = random.random()
        if rand < 0.95:  # 95% good readings
            return 'good'
        elif rand < 0.98:  # 3% warnings
            return 'warning'
        else:  # 2% errors
            return 'error'
    
    def insert_readings(self, readings):
        """Insert sensor readings into unified telemetry table"""
        try:
            conn = psycopg2.connect(**self.db_config)
            cursor = conn.cursor()
            
            for reading in readings:
                cursor.execute("""
                    INSERT INTO telemetry (ts, source, sensor, value, metadata)
                    VALUES (%s, %s, %s, %s, %s)
                """, (
                    reading['timestamp'],
                    'PLC',  # Source identifier
                    reading['sensor'],
                    reading['value'],
                    json.dumps(reading['metadata'])
                ))
            
            conn.commit()
            cursor.close()
            conn.close()
            
            print(f"✅ PLC: Inserted {len(readings)} readings")
            
        except Exception as e:
            print(f"❌ PLC Database error: {e}")
    
    def run(self):
        """Main simulation loop"""
        print("🚀 Starting PLC simulation (Unified Telemetry Schema)...")
        print("📊 Pressure sensors: 15 Beckhoff channels at 1 Hz")
        
        try:
            while True:
                timestamp = datetime.utcnow()
                readings = []
                
                # Generate readings for all pressure sensors
                for sensor_name, config in self.pressure_sensors.items():
                    value = self.generate_pressure_reading(sensor_name, config)
                    quality = self.get_quality()
                    
                    # Convert long Beckhoff name to shorter sensor name for database
                    short_sensor_name = sensor_name.replace('ADS.PLC1.GVL_Pressures.', 'plc_')
                    
                    readings.append({
                        'timestamp': timestamp,
                        'sensor': short_sensor_name,
                        'value': value,
                        'metadata': {
                            'full_name': sensor_name,  # Keep full Beckhoff name in metadata
                            'unit': 'kPa',  # All pressure sensors use kPa
                            'quality': quality,
                            'sample_rate': self.sample_rate,
                            'source_type': 'beckhoff_plc',
                            'range_min': config['range'][0],
                            'range_max': config['range'][1]
                        }
                    })
                
                # Insert all readings at once
                self.insert_readings(readings)
                
                # Wait for next sample
                time.sleep(1.0 / self.sample_rate)
                
        except KeyboardInterrupt:
            print("\n🛑 PLC simulation stopped")
        except Exception as e:
            print(f"❌ PLC simulation error: {e}")

if __name__ == "__main__":
    simulator = PLCSimulatorReal()
    simulator.run()
