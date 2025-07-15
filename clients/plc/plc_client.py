#!/usr/bin/env python3
"""
PLC Edge Client - Simple Single-File Version
Runs on NUC1, polls local PLC database, forwards to central TimescaleDB

Dependencies: pip install sqlalchemy psycopg2-binary
"""

import time
import json
import logging
from datetime import datetime, timedelta, timezone
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# ============================================================================
# CONFIGURATION - UPDATE THESE FOR YOUR ENVIRONMENT
# ============================================================================

# Database connections
PLC_DB_URL = "postgresql://plc_user:plc_pass@localhost:5432/plc_data"
CENTRAL_DB_URL = "postgresql://admin:admin@192.168.1.100:5432/telemetry"

# Processing settings
POLL_INTERVAL = 5.0      # Check for new data every 5 seconds
LOOKBACK_SECONDS = 30    # Always get last 30 seconds of data

# ============================================================================
# PLC CLIENT CODE
# ============================================================================

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('PLCClient')

class PLCClient:
    def __init__(self):
        # Database connections
        self.plc_engine = create_engine(PLC_DB_URL)
        self.central_engine = create_engine(CENTRAL_DB_URL)
        
        # Create sessions
        self.PLCSession = sessionmaker(bind=self.plc_engine)
        self.CentralSession = sessionmaker(bind=self.central_engine)
    
    def get_new_plc_data(self):
        """Get recent sensor readings from PLC database"""
        since_time = datetime.now(timezone.utc) - timedelta(seconds=LOOKBACK_SECONDS)
        
        try:
            with self.PLCSession() as session:
                # Query with JOIN to get sensor names from symbol table
                result = session.execute(text("""
                    SELECT 
                        r.updated as timestamp,
                        s.symbol as sensor_name,
                        r.value
                    FROM record1 r
                    JOIN symbol1 s ON r.symbolid = s.id
                    WHERE r.updated > :since_time
                    ORDER BY r.updated ASC
                """), {"since_time": since_time})
                
                readings = result.fetchall()
                
                if readings:
                    logger.info(f"📊 Found {len(readings)} readings from PLC")
                
                return readings
                
        except Exception as e:
            logger.error(f"❌ Error querying PLC database: {e}")
            return []
    
    def forward_to_central(self, plc_readings):
        """Transform and forward to central database"""
        if not plc_readings:
            return True
        
        try:
            with self.CentralSession() as session:
                successful_inserts = 0
                
                for timestamp, sensor_name, value in plc_readings:
                    # Create metadata WITHOUT units (they're in sensors table)
                    metadata = {
                        'source': 'beckhoff_plc'
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
                            "source": "PLC",
                            "sensor": sensor_name,
                            "value": float(value),
                            "metadata": json.dumps(metadata)
                        })
                        
                        successful_inserts += 1
                        
                    except Exception as e:
                        logger.warning(f"Failed to insert reading for {sensor_name}: {e}")
                        continue
                
                session.commit()
                logger.info(f"✅ Forwarded {successful_inserts}/{len(plc_readings)} readings")
                return True
                
        except Exception as e:
            logger.error(f"❌ Error forwarding to central database: {e}")
            return False
    
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
    
    def run(self):
        """Main processing loop"""
        logger.info("🚀 PLC Edge Client starting...")
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
                plc_data = self.get_new_plc_data()
                
                # Forward to central database
                if plc_data:
                    success = self.forward_to_central(plc_data)
                    if not success:
                        logger.warning("Failed to forward data")
                
                # Wait for next poll
                time.sleep(POLL_INTERVAL)
                
            except KeyboardInterrupt:
                logger.info("🛑 PLC Client stopped by user")
                break
            except Exception as e:
                logger.error(f"❌ Unexpected error: {e}")
                time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    client = PLCClient()
    client.run() 