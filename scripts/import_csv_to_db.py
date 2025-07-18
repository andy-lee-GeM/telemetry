#!/usr/bin/env python3
"""
Fast CSV Import using PostgreSQL COPY
Imports CSV with format: timestamp,sensor,value,group,file
"""
import psycopg2
import logging
import sys
import os
from datetime import datetime
from pathlib import Path

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger('FastCSVImport')

# Database configuration
DB_CONFIG = {
    'host': '169.254.77.77',
    'port': 5433,
    'database': 'telemetry',
    'user': 'admin',
    'password': 'admin'
}

def validate_csv_file(csv_path: str) -> Path:
    """Validate CSV file exists and check format"""
    path = Path(csv_path)
    
    if not path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")
    
    # Check file size
    file_size = path.stat().st_size
    logger.info(f"📁 File: {path.name}")
    logger.info(f"📊 Size: {file_size / (1024*1024*1024):.2f} GB")
    
    # Check header format
    with open(path, 'r') as f:
        header = f.readline().strip()
        expected_header = "timestamp,sensor,value,group,file"
        
        if header != expected_header:
            logger.warning(f"⚠️  Header mismatch!")
            logger.warning(f"   Expected: {expected_header}")
            logger.warning(f"   Found:    {header}")
            
            # Ask user if they want to continue
            response = input("Continue anyway? (y/n): ")
            if response.lower() != 'y':
                raise ValueError("Header format mismatch - aborting")
    
    return path

def test_database_connection():
    """Test database connection"""
    try:
        logger.info(f"🔍 Testing database connection to {DB_CONFIG['host']}:{DB_CONFIG['port']}")
        
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        cursor.execute("SELECT 1")
        result = cursor.fetchone()[0]
        
        cursor.close()
        conn.close()
        
        if result == 1:
            logger.info("✅ Database connection successful!")
            return True
        else:
            logger.error("❌ Unexpected database test result")
            return False
            
    except Exception as e:
        logger.error(f"❌ Database connection failed: {e}")
        return False

def import_csv_with_copy(csv_path: str):
    """Import CSV using PostgreSQL COPY command for maximum speed"""
    
    logger.info(f"🚀 Starting fast CSV import using COPY method")
    
    try:
        # Connect to database
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        # Create temporary table matching CSV structure
        logger.info("📋 Creating temporary table...")
        cursor.execute("""
            CREATE TEMP TABLE csv_temp (
                timestamp timestamp,
                sensor text,
                value numeric,
                group_name text,
                file_name text
            )
        """)
        
        # Import CSV using COPY (fastest method)
        logger.info("📁 Importing CSV data with COPY command...")
        start_time = datetime.now()
        
        with open(csv_path, 'r') as f:
            # Skip header line
            next(f)
            cursor.copy_from(
                f, 
                'csv_temp', 
                sep=',', 
                columns=('timestamp', 'sensor', 'value', 'group_name', 'file_name')
            )
        
        import_time = (datetime.now() - start_time).total_seconds()
        
        # Check import count
        cursor.execute("SELECT COUNT(*) FROM csv_temp")
        csv_count = cursor.fetchone()[0]
        logger.info(f"📊 CSV imported: {csv_count:,} rows in {import_time:.1f} seconds")
        logger.info(f"⚡ Import rate: {csv_count/import_time:,.0f} rows/second")
        
        # Insert into main telemetry table with metadata
        logger.info("🔄 Inserting into main telemetry table...")
        insert_start = datetime.now()
        
        cursor.execute("""
            INSERT INTO telemetry (ts, source, sensor, value, metadata)
            SELECT 
                timestamp,
                'CSV-BULK-IMPORT',
                sensor,
                value,
                json_build_object(
                    'group', group_name,
                    'file', file_name,
                    'import_method', 'python_copy',
                    'import_time', %s,
                    'original_csv_rows', %s
                )::jsonb
            FROM csv_temp
        """, (datetime.now().isoformat(), csv_count))
        
        insert_time = (datetime.now() - insert_start).total_seconds()
        
        # Get final count
        cursor.execute("SELECT COUNT(*) FROM telemetry WHERE source = 'CSV-BULK-IMPORT'")
        final_count = cursor.fetchone()[0]
        
        # Commit transaction
        conn.commit()
        cursor.close()
        conn.close()
        
        total_time = (datetime.now() - start_time).total_seconds()
        
        logger.info(f"✅ Import complete!")
        logger.info(f"📊 Total rows imported: {final_count:,}")
        logger.info(f"⏱️  Total time: {total_time:.1f} seconds")
        logger.info(f"⚡ Overall rate: {final_count/total_time:,.0f} rows/second")
        
        return {"success": final_count, "errors": 0}
        
    except Exception as e:
        logger.error(f"❌ Import failed: {e}")
        return {"success": 0, "errors": 1}

def check_existing_data():
    """Check if there's already imported data"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM telemetry WHERE source = 'CSV-BULK-IMPORT'")
        existing_count = cursor.fetchone()[0]
        
        cursor.close()
        conn.close()
        
        if existing_count > 0:
            logger.warning(f"⚠️  Found {existing_count:,} existing CSV-BULK-IMPORT records")
            response = input("Continue and add more data? (y/n): ")
            if response.lower() != 'y':
                logger.info("Import cancelled by user")
                return False
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Error checking existing data: {e}")
        return False

def main():
    """Main import function"""
    if len(sys.argv) != 2:
        print("Usage: python import_csv_fast.py /path/to/your/data.csv")
        print("Example: python import_csv_fast.py output2.csv")
        sys.exit(1)
    
    csv_path = sys.argv[1]
    
    try:
        # Validate CSV file
        validated_path = validate_csv_file(csv_path)
        
        # Test database connection
        if not test_database_connection():
            logger.error("❌ Cannot connect to database - aborting")
            sys.exit(1)
        
        # Check for existing data
        if not check_existing_data():
            sys.exit(1)
        
        # Import CSV
        result = import_csv_with_copy(str(validated_path))
        
        if result["success"] > 0:
            logger.info("🎉 CSV import completed successfully!")
            
            # Show some sample data
            logger.info("📋 Sample of imported data:")
            conn = psycopg2.connect(**DB_CONFIG)
            cursor = conn.cursor()
            cursor.execute("""
                SELECT ts, sensor, value, metadata->>'group' as group_name 
                FROM telemetry 
                WHERE source = 'CSV-BULK-IMPORT' 
                ORDER BY ts 
                LIMIT 5
            """)
            
            for row in cursor.fetchall():
                logger.info(f"   {row[0]} | {row[1]} | {row[2]} | {row[3]}")
            
            cursor.close()
            conn.close()
            
        else:
            logger.error("❌ Import failed")
            sys.exit(1)
            
    except Exception as e:
        logger.error(f"❌ {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
