#!/usr/bin/env python3
"""
PLC Edge Client - Modular Version
Supports both continuous polling and one-time data retrieval
"""

import time
import json
import logging
from datetime import datetime, timedelta, timezone
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# ============================================================================
# CONFIGURATION
# ============================================================================

# PLC Database Configuration
PLC_HOST = "169.254.77.77"
PLC_PORT = 5432
PLC_USER = "postgres"
PLC_PASSWORD = "1"
PLC_DATABASE = "XenonData"

# Central Database Configuration
CENTRAL_HOST = "localhost"
CENTRAL_PORT = 5433
CENTRAL_USER = "admin"
CENTRAL_PASSWORD = "admin"
CENTRAL_DATABASE = "telemetry"

# Build connection strings
PLC_DB_URL = f"postgresql://{PLC_USER}:{PLC_PASSWORD}@{PLC_HOST}:{PLC_PORT}/{PLC_DATABASE}"
CENTRAL_DB_URL = f"postgresql://{CENTRAL_USER}:{CENTRAL_PASSWORD}@{CENTRAL_HOST}:{CENTRAL_PORT}/{CENTRAL_DATABASE}"

# Processing settings
POLL_INTERVAL = 5.0      # Check for new data every 5 seconds
LOOKBACK_SECONDS = 30    # Always get last 30 seconds of data

# ============================================================================
# LOGGING SETUP
# ============================================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('PLCClient')

# ============================================================================
# PLC CLIENT CLASS
# ============================================================================

class PLCClient:
    def __init__(self):
        logger.info(f"🔗 PLC Connection: {PLC_HOST}:{PLC_PORT}/{PLC_DATABASE} as {PLC_USER}")
        logger.info(f"🔗 Central Connection: {CENTRAL_HOST}:{CENTRAL_PORT}/{CENTRAL_DATABASE} as {CENTRAL_USER}")
        
        # Database connections
        self.plc_engine = create_engine(PLC_DB_URL)
        self.central_engine = create_engine(CENTRAL_DB_URL)
        
        # Create sessions
        self.PLCSession = sessionmaker(bind=self.plc_engine)
        self.CentralSession = sessionmaker(bind=self.central_engine)
        
        # State tracking
        self.last_processed_time = None
    
    def get_plc_data_by_time(self, since_time=None, limit=None):
        """Get PLC data since a specific time"""
        if since_time is None:
            since_time = datetime.now(timezone.utc) - timedelta(seconds=LOOKBACK_SECONDS)
        
        try:
            with self.PLCSession() as session:
                # Build query
                query = """
                    SELECT 
                        r.updated as timestamp,
                        s.symbol as sensor_name,
                        r.value
                    FROM record_1 r
                    JOIN symboldata_1 s ON r.symbolid = s.id
                    WHERE r.updated > :since_time
                    AND r.value IS NOT NULL
                    ORDER BY r.updated ASC
                """
                
                params = {"since_time": since_time}
                
                # Add limit if specified
                if limit:
                    query += " LIMIT :limit"
                    params["limit"] = limit
                
                result = session.execute(text(query), params)
                readings = result.fetchall()
                
                if readings:
                    logger.info(f"📊 Found {len(readings)} readings from PLC")
                    logger.info(f"📅 Date range: {readings[0][0]} to {readings[-1][0]}")
                
                return readings
                
        except Exception as e:
            logger.error(f"❌ Error querying PLC database: {e}")
            return []
    
    def get_recent_plc_data(self, limit=1000):
        """Get the most recent PLC data"""
        try:
            with self.PLCSession() as session:
                logger.info(f"📊 Fetching {limit} most recent PLC readings...")
                
                result = session.execute(text("""
                    SELECT 
                        r.updated as timestamp,
                        s.symbol as sensor_name,
                        r.value
                    FROM record_1 r
                    JOIN symboldata_1 s ON r.symbolid = s.id
                    WHERE r.value IS NOT NULL
                    ORDER BY r.updated DESC
                    LIMIT :limit
                """), {"limit": limit})
                
                readings = result.fetchall()
                
                if readings:
                    logger.info(f"✅ Found {len(readings)} readings")
                    logger.info(f"📅 Date range: {readings[-1][0]} to {readings[0][0]}")
                    
                    # Show sample of sensor types
                    sensors = set(reading[1] for reading in readings[:10])
                    logger.info(f"📋 Sample sensors: {list(sensors)[:5]}")
                
                return readings
                
        except Exception as e:
            logger.error(f"❌ Error querying PLC database: {e}")
            return []
    
    def transform_and_forward(self, plc_readings, source_label="PLC"):
        """Transform PLC data and forward to central database"""
        if not plc_readings:
            logger.warning("No data to transform")
            return {"success": 0, "skipped": 0, "errors": 0}
        
        try:
            with self.CentralSession() as session:
                successful_inserts = 0
                skipped_nulls = 0
                errors = 0
                
                logger.info(f"🔄 Transforming and inserting {len(plc_readings)} readings...")
                
                for timestamp, sensor_name, value in plc_readings:
                    # Skip NULL values
                    if value is None:
                        skipped_nulls += 1
                        continue
                    
                    # Try to convert to float
                    try:
                        float_value = float(value)
                    except (ValueError, TypeError):
                        skipped_nulls += 1
                        continue
                    
                    # Create metadata
                    metadata = {
                        'source': 'beckhoff_plc',
                        'transfer_time': datetime.now(timezone.utc).isoformat()
                    }
                    
                    try:
                        # UPSERT: Insert or update if duplicate
                        session.execute(text("""
                            INSERT INTO telemetry (ts, source, sensor, value, metadata)
                            VALUES (:ts, :source, :sensor, :value, :metadata)
                            ON CONFLICT (ts, source, sensor) DO UPDATE SET
                                value = EXCLUDED.value,
                                metadata = EXCLUDED.metadata,
                                ingest_ts = NOW()
                        """), {
                            "ts": timestamp,
                            "source": source_label,
                            "sensor": sensor_name,
                            "value": float_value,
                            "metadata": json.dumps(metadata)
                        })
                        
                        successful_inserts += 1
                        
                    except Exception as e:
                        logger.warning(f"Failed to insert {sensor_name}: {e}")
                        errors += 1
                        continue
                
                session.commit()
                
                # Update last processed time if we have data
                if plc_readings and successful_inserts > 0:
                    self.last_processed_time = max(reading[0] for reading in plc_readings)
                
                results = {
                    "success": successful_inserts,
                    "skipped": skipped_nulls,
                    "errors": errors
                }
                
                logger.info(f"✅ Successfully inserted: {successful_inserts}")
                logger.info(f"⚠️  Skipped nulls: {skipped_nulls}")
                logger.info(f"❌ Errors: {errors}")
                
                return results
                
        except Exception as e:
            logger.error(f"❌ Error during transform/insert: {e}")
            return {"success": 0, "skipped": 0, "errors": 0}
    
    def health_check(self):
        """Test connectivity to both databases"""
        try:
            # Test PLC connection
            with self.PLCSession() as session:
                session.execute(text("SELECT 1"))
            
            # Test central connection
            with self.CentralSession() as session:
                session.execute(text("SELECT 1"))
            
            return True
            
        except Exception as e:
            logger.warning(f"Health check failed: {e}")
            return False
    
    def get_telemetry_stats(self, source_filter=None):
        """Get statistics from telemetry database"""
        try:
            with self.central_engine.connect() as conn:
                # Count total records
                if source_filter:
                    result = conn.execute(text(
                        "SELECT COUNT(*) FROM telemetry WHERE source = :source"
                    ), {"source": source_filter})
                else:
                    result = conn.execute(text("SELECT COUNT(*) FROM telemetry"))
                
                total_count = result.fetchone()[0]
                
                # Get unique sensors
                if source_filter:
                    result = conn.execute(text("""
                        SELECT sensor, COUNT(*) as count 
                        FROM telemetry 
                        WHERE source = :source
                        GROUP BY sensor 
                        ORDER BY count DESC 
                        LIMIT 10
                    """), {"source": source_filter})
                else:
                    result = conn.execute(text("""
                        SELECT sensor, COUNT(*) as count 
                        FROM telemetry 
                        GROUP BY sensor 
                        ORDER BY count DESC 
                        LIMIT 10
                    """))
                
                top_sensors = result.fetchall()
                
                return {
                    "total_count": total_count,
                    "top_sensors": top_sensors
                }
                
        except Exception as e:
            logger.error(f"❌ Error getting telemetry stats: {e}")
            return {"total_count": 0, "top_sensors": []}
    
    def run_continuous_polling(self):
        """Main continuous polling loop"""
        logger.info("🚀 PLC Edge Client starting continuous polling...")
        logger.info(f"📡 Poll interval: {POLL_INTERVAL}s")
        logger.info(f"📊 Lookback window: {LOOKBACK_SECONDS}s")
        
        consecutive_failures = 0
        max_failures = 3
        
        while True:
            try:
                # Health check
                if not self.health_check():
                    consecutive_failures += 1
                    if consecutive_failures >= max_failures:
                        logger.error("Too many consecutive health check failures - stopping")
                        break
                    
                    logger.warning(f"Health check failed ({consecutive_failures}/{max_failures})")
                    time.sleep(POLL_INTERVAL * 2)
                    continue
                
                # Reset failure counter
                consecutive_failures = 0
                
                # Get new data from PLC
                plc_data = self.get_plc_data_by_time(limit=1000)
                
                # Forward to central database
                if plc_data:
                    self.transform_and_forward(plc_data)
                
                # Wait for next poll
                time.sleep(POLL_INTERVAL)
                
            except KeyboardInterrupt:
                logger.info("🛑 PLC Client stopped by user")
                break
            except Exception as e:
                logger.error(f"❌ Unexpected error: {e}")
                time.sleep(POLL_INTERVAL)

# ============================================================================
# MAIN EXECUTION
# ============================================================================

if __name__ == "__main__":
    client = PLCClient()
    client.run_continuous_polling() 