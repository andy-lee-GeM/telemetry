#!/usr/bin/env python3
"""
Telemetry utilities for MVP - simple and focused
"""

import json
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, NamedTuple
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Central Database Configuration
CENTRAL_DB_URL = "postgresql://admin:admin@localhost:5433/telemetry"

class TelemetryReading(NamedTuple):
    """Standard telemetry reading structure"""
    timestamp: datetime
    sensor: str
    value: float
    metadata: Dict[str, Any] = {}

def get_db_session():
    """Get database session"""
    engine = create_engine(CENTRAL_DB_URL)
    Session = sessionmaker(bind=engine)
    return Session()

def is_valid_reading(reading: TelemetryReading) -> bool:
    """Quick validation of a reading"""
    if reading.value is None:
        return False
    try:
        float(reading.value)
        return True
    except (ValueError, TypeError):
        return False

def insert_telemetry_batch(readings: List[TelemetryReading], source_label: str, 
                          client_name: str, logger: logging.Logger) -> Dict[str, int]:
    """Insert batch of telemetry readings"""
    if not readings:
        logger.warning("No readings to insert")
        return {"success": 0, "skipped": 0, "errors": 0}
    
    logger.info(f"🔄 Inserting {len(readings)} readings...")
    
    session = get_db_session()
    successful_inserts = 0
    skipped = 0
    errors = 0
    
    try:
        for reading in readings:
            # Skip invalid readings
            if not is_valid_reading(reading):
                skipped += 1
                continue
            
            # Add client metadata
            metadata = reading.metadata.copy()
            metadata.update({
                'client': client_name,
                'transfer_time': datetime.now(timezone.utc).isoformat()
            })
            
            try:
                # Insert with upsert
                session.execute(text("""
                    INSERT INTO telemetry (ts, source, sensor, value, metadata)
                    VALUES (:ts, :source, :sensor, :value, :metadata)
                    ON CONFLICT (ts, source, sensor) DO UPDATE SET
                        value = EXCLUDED.value,
                        metadata = EXCLUDED.metadata,
                        ingest_ts = NOW()
                """), {
                    "ts": reading.timestamp,
                    "source": source_label,
                    "sensor": reading.sensor,
                    "value": float(reading.value),
                    "metadata": json.dumps(metadata)
                })
                
                successful_inserts += 1
                
            except Exception as e:
                logger.warning(f"Failed to insert {reading.sensor}: {e}")
                errors += 1
        
        session.commit()
        
    except Exception as e:
        logger.error(f"❌ Database operation failed: {e}")
        session.rollback()
        
    finally:
        session.close()
    
    result = {"success": successful_inserts, "skipped": skipped, "errors": errors}
    logger.info(f"✅ Success: {result['success']}, ⚠️ Skipped: {result['skipped']}, ❌ Errors: {result['errors']}")
    return result

def test_central_connection(logger: logging.Logger) -> bool:
    """Test central database connectivity"""
    try:
        session = get_db_session()
        session.execute(text("SELECT 1"))
        session.close()
        return True
    except Exception as e:
        logger.warning(f"Central DB health check failed: {e}")
        return False

def get_telemetry_stats(source_filter: str, logger: logging.Logger) -> Dict[str, Any]:
    """Get basic stats for a source"""
    try:
        session = get_db_session()
        
        # Count total records
        result = session.execute(text(
            "SELECT COUNT(*) FROM telemetry WHERE source = :source"
        ), {"source": source_filter})
        total_count = result.fetchone()[0]
        
        # Get top sensors
        result = session.execute(text("""
            SELECT sensor, COUNT(*) as count 
            FROM telemetry 
            WHERE source = :source
            GROUP BY sensor 
            ORDER BY count DESC 
            LIMIT 5
        """), {"source": source_filter})
        top_sensors = result.fetchall()
        
        session.close()
        
        return {
            "total_count": total_count,
            "top_sensors": top_sensors
        }
        
    except Exception as e:
        logger.error(f"❌ Error getting stats: {e}")
        return {"total_count": 0, "top_sensors": []}