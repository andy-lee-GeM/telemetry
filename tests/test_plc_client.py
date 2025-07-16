#!/usr/bin/env python3
"""
Test Script - Uses PLCClient for one-time data retrieval
"""

import logging
import sys
import os

# Add project root to Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

print(f"Added to Python path: {project_root}")

from clients.plc.plc_client import PLCClient

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger('PLCTest')

def main():
    logger.info("🚀 Starting PLC client test...")
    
    # Create client
    client = PLCClient()
    
    # Test 1: Health check
    logger.info("🏥 Testing database connections...")
    if not client.health_check():
        logger.error("❌ Health check failed - stopping")
        return
    
    # Test 2: Get recent data
    logger.info("📊 Fetching 1000 most recent records...")
    readings = client.get_recent_plc_data(limit=1000)
    
    if not readings:
        logger.error("❌ No data retrieved - stopping")
        return
    
    # Test 3: Transform and insert
    logger.info("🔄 Transforming and inserting data...")
    results = client.transform_and_forward(readings, source_label="PLC_TEST")
    
    # Test 4: Verify results
    logger.info("🔍 Checking telemetry database...")
    stats = client.get_telemetry_stats(source_filter="PLC_TEST")
    
    logger.info(f"📊 Total test records: {stats['total_count']}")
    logger.info("🔍 Top sensors:")
    for sensor, count in stats['top_sensors']:
        logger.info(f"   {sensor}: {count} records")
    
    logger.info("🎉 Test completed successfully!")

if __name__ == "__main__":
    main()
