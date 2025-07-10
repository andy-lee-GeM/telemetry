#!/usr/bin/env python3
"""
NI-DAQ Data Simulator - Edge Client #2 Mock
Simulates realistic NI-DAQ TDMS data based on actual sensor characteristics
"""

import time
import json
import psycopg2
import numpy as np
from datetime import datetime, timedelta

class NIDAQSimulator:
    def __init__(self):
        # Database connection
        self.db_config = {
            'host': 'localhost',
            'database': 'telemetry',
            'user': 'admin',
            'password': 'admin',
            'port': 5432
        }
        
        # Real sensor characteristics from TDMS inspection
        self.sensors = {
            # Ground Acceleration (100 Hz sampling)
            'ground_accel_x': {
                'mean': 0.165252, 'std': 0.056391, 'min': 0.005467, 'max': 0.411111,
                'unit': 'g', 'type': 'vibration', 'sample_rate': 100.0
            },
            'ground_accel_y': {
                'mean': 0.148292, 'std': 0.060923, 'min': -0.043687, 'max': 0.360048,
                'unit': 'g', 'type': 'vibration', 'sample_rate': 100.0
            },
            'ground_accel_z': {
                'mean': 1.125886, 'std': 0.060597, 'min': 0.892158, 'max': 1.342661,
                'unit': 'g', 'type': 'vibration', 'sample_rate': 100.0
            },
            
            # Ground Acceleration RMS (10 Hz sampling)
            'ground_accel_x_rms': {
                'mean': 0.172003, 'std': 0.030053, 'min': 0.106182, 'max': 0.245068,
                'unit': 'g', 'type': 'rms', 'sample_rate': 10.0
            },
            'ground_accel_y_rms': {
                'mean': 0.157142, 'std': 0.031758, 'min': 0.083664, 'max': 0.235038,
                'unit': 'g', 'type': 'rms', 'sample_rate': 10.0
            },
            'ground_accel_z_rms': {
                'mean': 1.126997, 'std': 0.034191, 'min': 1.046116, 'max': 1.198234,
                'unit': 'g', 'type': 'rms', 'sample_rate': 10.0
            },
            
            # Bearing Loads (10 kHz sampling)
            'lower_bearing_load_x': {
                'mean': -0.000104, 'std': 0.001812, 'min': -0.007171, 'max': 0.007807,
                'unit': 'kgf', 'type': 'load_hf', 'sample_rate': 10000.0
            },
            'lower_bearing_load_y': {
                'mean': 0.098377, 'std': 0.006045, 'min': 0.066109, 'max': 0.125054,
                'unit': 'kgf', 'type': 'load_hf', 'sample_rate': 10000.0
            },
            'lower_bearing_load_z': {
                'mean': -0.000326, 'std': 0.002580, 'min': -0.010553, 'max': 0.014410,
                'unit': 'kgf', 'type': 'load_hf', 'sample_rate': 10000.0
            },
            'upper_bearing_load_x': {
                'mean': 0.000205, 'std': 0.003484, 'min': -0.013935, 'max': 0.017953,
                'unit': 'kgf', 'type': 'load_hf', 'sample_rate': 10000.0
            },
            'upper_bearing_load_y': {
                'mean': 0.000958, 'std': 0.002729, 'min': -0.011121, 'max': 0.013363,
                'unit': 'kgf', 'type': 'load_hf', 'sample_rate': 10000.0
            },
            'upper_bearing_load_z': {
                'mean': -0.003796, 'std': 0.006401, 'min': -0.036805, 'max': 0.022946,
                'unit': 'kgf', 'type': 'load_hf', 'sample_rate': 10000.0
            },
            
            # Bearing Temperatures (100 Hz sampling)
            'lower_bearing_temp_1': {
                'mean': 0.060069, 'std': 0.006467, 'min': 0.030197, 'max': 0.075965,
                'unit': '°C', 'type': 'temperature', 'sample_rate': 100.0
            },
            'lower_bearing_temp_2': {
                'mean': 0.067545, 'std': 0.005365, 'min': 0.040511, 'max': 0.086118,
                'unit': '°C', 'type': 'temperature', 'sample_rate': 100.0
            },
            'lower_bearing_temp_3': {
                'mean': 0.053287, 'std': 0.006816, 'min': 0.031808, 'max': 0.077738,
                'unit': '°C', 'type': 'temperature', 'sample_rate': 100.0
            },
            
            # Rotor Positions (10 kHz sampling)
            'lower_rotor_position_x': {
                'mean': 25.088989, 'std': 0.017910, 'min': 25.008408, 'max': 25.167872,
                'unit': 'mm', 'type': 'position_hf', 'sample_rate': 10000.0
            },
            'lower_rotor_position_y': {
                'mean': 101.566885, 'std': 0.022370, 'min': 101.477369, 'max': 101.668251,
                'unit': 'mm', 'type': 'position_hf', 'sample_rate': 10000.0
            },
            'upper_rotor_position_x': {
                'mean': 25.095984, 'std': 0.020004, 'min': 25.020489, 'max': 25.170288,
                'unit': 'mm', 'type': 'position_hf', 'sample_rate': 10000.0
            },
            'upper_rotor_position_y': {
                'mean': 25.085303, 'std': 0.022188, 'min': 24.996327, 'max': 25.175120,
                'unit': 'mm', 'type': 'position_hf', 'sample_rate': 10000.0
            },
            
            # Bearing Positions (10 kHz sampling)
            'upper_bearing_position_x': {
                'mean': 32.361419, 'std': 0.012699, 'min': 32.312233, 'max': 32.408866,
                'unit': 'mm', 'type': 'position_hf', 'sample_rate': 10000.0
            },
            'upper_bearing_position_y': {
                'mean': 30.907695, 'std': 0.012332, 'min': 30.854687, 'max': 30.955347,
                'unit': 'mm', 'type': 'position_hf', 'sample_rate': 10000.0
            },
            
            # Stator Temperatures (100 Hz sampling)
            'stator_temp_1': {
                'mean': 23.150182, 'std': 0.199499, 'min': 22.431428, 'max': 23.785557,
                'unit': '°C', 'type': 'temperature', 'sample_rate': 100.0
            },
            'stator_temp_2': {
                'mean': 0.090627, 'std': 0.007418, 'min': 0.057271, 'max': 0.109324,
                'unit': '°C', 'type': 'temperature', 'sample_rate': 100.0
            },
            
            # Tachometer (6.25 kHz sampling, but all zeros in real data)
            'tachometer': {
                'mean': 0.0, 'std': 0.0, 'min': 0.0, 'max': 0.0,
                'unit': 'pulse', 'type': 'rpm', 'sample_rate': 6250.0
            }
        }
        
        # Batch settings - simulate different sampling rates
        self.batch_duration = 0.1  # 100ms batches
        
    def generate_sensor_value(self, sensor_name, config, t):
        """Generate realistic sensor value based on real characteristics"""
        mean = config['mean']
        std = config['std']
        sensor_type = config['type']
        
        if sensor_type == 'vibration':
            # Vibration with multiple frequency components
            freq1 = 50   # 50 Hz component
            freq2 = 120  # 120 Hz component
            freq3 = 200  # 200 Hz component
            
            vibration = (
                std * 0.3 * np.sin(2 * np.pi * freq1 * t) +
                std * 0.2 * np.sin(2 * np.pi * freq2 * t) +
                std * 0.1 * np.sin(2 * np.pi * freq3 * t)
            )
            noise = np.random.normal(0, std * 0.5)
            value = mean + vibration + noise
            
        elif sensor_type == 'rms':
            # RMS values change more slowly
            slow_variation = std * 0.5 * np.sin(2 * np.pi * 0.1 * t)  # 0.1 Hz
            noise = np.random.normal(0, std * 0.3)
            value = mean + slow_variation + noise
            
        elif sensor_type == 'load_hf':
            # High frequency load with some periodic components
            freq = 25  # 25 Hz load variation
            load_variation = std * 0.4 * np.sin(2 * np.pi * freq * t)
            noise = np.random.normal(0, std * 0.6)
            value = mean + load_variation + noise
            
        elif sensor_type == 'temperature':
            # Temperature changes slowly
            thermal_drift = std * 0.3 * np.sin(2 * np.pi * 0.01 * t)  # Very slow
            noise = np.random.normal(0, std * 0.4)
            value = mean + thermal_drift + noise
            
        elif sensor_type == 'position_hf':
            # Position has small high-frequency variations
            freq = 10  # 10 Hz position variation
            position_variation = std * 0.5 * np.sin(2 * np.pi * freq * t)
            noise = np.random.normal(0, std * 0.5)
            value = mean + position_variation + noise
            
        else:  # rpm or default
            # Tachometer (currently zero in real data)
            value = mean + np.random.normal(0, std if std > 0 else 0.01)
        
        # Clamp to realistic bounds
        value = np.clip(value, config['min'], config['max'])
        return value
    
    def generate_batch(self):
        """Generate batch of sensor data with realistic sampling rates"""
        start_time = datetime.utcnow()
        readings = []
        
        # Group sensors by sampling rate for efficiency
        sample_rates = {}
        for sensor_name, config in self.sensors.items():
            rate = config['sample_rate']
            if rate not in sample_rates:
                sample_rates[rate] = []
            sample_rates[rate].append((sensor_name, config))
        
        # Generate data for each sampling rate
        for sample_rate, sensor_list in sample_rates.items():
            # Limit high-frequency sensors to avoid overwhelming the database
            if sample_rate >= 1000:
                # For high-freq sensors, downsample to 100 Hz for simulation
                effective_rate = 100.0
                downsample_factor = int(sample_rate / effective_rate)
            else:
                effective_rate = sample_rate
                downsample_factor = 1
            
            samples = max(1, int(self.batch_duration * effective_rate))
            
            for i in range(samples):
                t = i / effective_rate
                timestamp = start_time + timedelta(seconds=t)
                
                for sensor_name, config in sensor_list:
                    value = self.generate_sensor_value(sensor_name, config, t)
                    
                    readings.append({
                        'timestamp': timestamp,
                        'sensor': sensor_name,
                        'value': round(float(value), 6),
                        'metadata': {
                            'sample_rate': sample_rate,
                            'effective_rate': effective_rate,
                            'downsample_factor': downsample_factor,
                            'unit': config['unit'],
                            'quality': 'good',
                            'source_type': 'nidaq'
                        }
                    })
        
        return readings
    
    def insert_readings(self, readings):
        """Insert sensor readings into database"""
        try:
            conn = psycopg2.connect(**self.db_config)
            cursor = conn.cursor()
            
            for reading in readings:
                cursor.execute("""
                    INSERT INTO telemetry (ts, source, sensor, value, metadata)
                    VALUES (%s, %s, %s, %s, %s)
                """, (
                    reading['timestamp'],
                    'NI-DAQ',
                    reading['sensor'],
                    reading['value'],
                    json.dumps(reading['metadata'])
                ))
            
            conn.commit()
            cursor.close()
            conn.close()
            
            print(f"✅ NI-DAQ: Inserted {len(readings)} readings")
            
        except Exception as e:
            print(f"❌ NI-DAQ Database error: {e}")
    
    def run(self):
        """Main simulation loop"""
        print("🚀 Starting NI-DAQ simulation with realistic sensor characteristics...")
        print("📊 Sensors: 26 channels with varying sample rates (10Hz to 10kHz)")
        
        try:
            while True:
                # Generate batch of data
                readings = self.generate_batch()
                
                # Insert to database
                self.insert_readings(readings)
                
                # Wait for next batch
                time.sleep(self.batch_duration)
                
        except KeyboardInterrupt:
            print("\n🛑 NI-DAQ simulation stopped")
        except Exception as e:
            print(f"❌ NI-DAQ simulation error: {e}")

if __name__ == "__main__":
    simulator = NIDAQSimulator()
    simulator.run()
