#!/usr/bin/env python3
"""
🏭 Simple Pressure Sensor Simulator - Proof of Concept
10 pressure sensors, 1 day of data, logged every minute
Total: 14,400 data points (10 sensors × 1440 minutes)
"""

import psycopg2
import random
from datetime import datetime, timedelta

# 🗄️ Database connection
DB_CONFIG = {
    'host': 'localhost',
    'database': 'telemetry',
    'user': 'admin',
    'password': 'admin',
    'port': 5432
}

# 📊 10 Simple pressure sensors with different baseline pressures (Torr)
SENSORS = [
    {'name': 'sensor_01', 'base_pressure': 0.5},    # Medium vacuum
    {'name': 'sensor_02', 'base_pressure': 0.001},  # High vacuum  
    {'name': 'sensor_03', 'base_pressure': 2.0},    # Low vacuum
    {'name': 'sensor_04', 'base_pressure': 0.1},    # Good vacuum
    {'name': 'sensor_05', 'base_pressure': 5.0},    # Rough vacuum
    {'name': 'sensor_06', 'base_pressure': 0.05},   # Very good vacuum
    {'name': 'sensor_07', 'base_pressure': 1.0},    # Medium vacuum
    {'name': 'sensor_08', 'base_pressure': 0.005},  # High vacuum
    {'name': 'sensor_09', 'base_pressure': 3.0},    # Low vacuum
    {'name': 'sensor_10', 'base_pressure': 0.2}     # Good vacuum
]

def generate_pressure_reading(base_pressure, timestamp):
    """
    Generate realistic vacuum pressure reading in Torr
    - Adds realistic noise/variation
    - Simulates typical vacuum system behavior
    """
    # Random variation (±20% of base pressure)
    variation = random.uniform(-0.2, 0.2) * base_pressure
    
    # Small random noise
    noise = random.uniform(-0.01, 0.01)
    
    # Calculate pressure (keep above 0.0001 Torr minimum)
    pressure = base_pressure + variation + noise
    pressure = max(0.0001, pressure)  # Vacuum systems can't go below this
    
    # Round to 6 decimal places (realistic for vacuum gauges)
    return round(pressure, 6)

def connect_to_database():
    """Connect to PostgreSQL"""
    try:
        print("🔌 Connecting to database...")
        conn = psycopg2.connect(**DB_CONFIG)
        print("✅ Connected!")
        return conn
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        print("💡 Make sure database is running: docker-compose up db")
        return None

def generate_one_day_data(conn):
    """
    Generate 1 day of pressure data, logged every minute
    - 1440 minutes in a day
    - 10 sensors
    - Total: 14,400 data points
    """
    print("📊 Generating 1 day of pressure sensor data...")
    print("   • 10 sensors")
    print("   • 1440 minutes (24 hours)")
    print("   • Logged every minute")
    print("   • Total records: 14,400")
    
    cursor = conn.cursor()
    
    # Start time: 24 hours ago
    start_time = datetime.now() - timedelta(days=1)
    
    # Batch insert for efficiency
    all_data = []
    
    # Generate data for each minute of the day
    for minute in range(1440):  # 24 hours × 60 minutes
        timestamp = start_time + timedelta(minutes=minute)
        
        # Each sensor reports at this timestamp
        for sensor in SENSORS:
            pressure = generate_pressure_reading(sensor['base_pressure'], timestamp)
            
            all_data.append((
                sensor['name'],
                pressure,
                'Torr',
                timestamp,
                'active'
            ))
    
    # Insert all data at once (efficient!)
    print("💾 Inserting data into database...")
    insert_query = """
        INSERT INTO pressure_readings (sensor_name, pressure_value, unit, timestamp, status)
        VALUES (%s, %s, %s, %s, %s)
    """
    
    cursor.executemany(insert_query, all_data)
    conn.commit()
    cursor.close()
    
    print(f"✅ Successfully inserted {len(all_data):,} pressure readings!")

def show_summary(conn):
    """Show what was created"""
    cursor = conn.cursor()
    
    print("\n" + "="*50)
    print("📈 DATA SUMMARY")
    print("="*50)
    
    # Total records
    cursor.execute("SELECT COUNT(*) FROM pressure_readings")
    total = cursor.fetchone()[0]
    print(f"📊 Total readings: {total:,}")
    
    # Date range
    cursor.execute("SELECT MIN(timestamp), MAX(timestamp) FROM pressure_readings")
    min_time, max_time = cursor.fetchone()
    print(f"📅 Time range: {min_time.strftime('%Y-%m-%d %H:%M')} to {max_time.strftime('%Y-%m-%d %H:%M')}")
    
    # Per sensor summary
    cursor.execute("""
        SELECT sensor_name, 
               COUNT(*) as readings,
               AVG(pressure_value) as avg_pressure,
               MIN(pressure_value) as min_pressure,
               MAX(pressure_value) as max_pressure
        FROM pressure_readings 
        GROUP BY sensor_name 
        ORDER BY sensor_name
    """)
    
    print("\n📡 Per-sensor summary:")
    print("   Sensor    │ Readings │ Avg Torr │ Min Torr │ Max Torr")
    print("   ──────────┼──────────┼──────────┼──────────┼─────────")
    
    for row in cursor.fetchall():
        sensor, count, avg, min_val, max_val = row
        print(f"   {sensor:<9}│ {count:>8}│ {avg:>8.4f}│ {min_val:>8.4f}│ {max_val:>8.4f}")
    
    cursor.close()
    print("="*50)

def main():
    """Main function"""
    print("🚀 SIMPLE PRESSURE SENSOR SIMULATION")
    print("Proof of concept: 10 sensors, 1 day, every minute")
    print("="*50)
    
    # Connect to database
    conn = connect_to_database()
    if not conn:
        return
    
    try:
        # Generate the data
        generate_one_day_data(conn)
        
        # Show summary
        show_summary(conn)
        
        print("\n🎉 SUCCESS!")
        print("💡 Next step: Set up Grafana to visualize this data")
        print("   Your database now has 14,400 pressure readings ready for charting!")
        
    except Exception as e:
        print(f"❌ Error: {e}")
    
    finally:
        conn.close()
        print("🔚 Database connection closed")

if __name__ == "__main__":
    main() 