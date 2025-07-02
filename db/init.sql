-- 📊 Simple Pressure Sensor System - Proof of Concept
-- 10 pressure sensors logging every minute for 1 day

-- 📊 Simple pressure readings table
CREATE TABLE IF NOT EXISTS pressure_readings (
    id SERIAL PRIMARY KEY,
    sensor_name VARCHAR(50) NOT NULL,       -- 'sensor_01', 'sensor_02', etc.
    pressure_value DECIMAL(10, 6) NOT NULL, -- Pressure in Torr (vacuum pressures)
    unit VARCHAR(10) DEFAULT 'Torr',
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    status VARCHAR(20) DEFAULT 'active'
);

-- 📊 Index for time-series queries (important for Grafana)
CREATE INDEX IF NOT EXISTS idx_pressure_timestamp ON pressure_readings(timestamp);
CREATE INDEX IF NOT EXISTS idx_pressure_sensor ON pressure_readings(sensor_name);

-- 🌱 Insert a couple test records to verify setup
INSERT INTO pressure_readings (sensor_name, pressure_value) VALUES
    ('sensor_01', 0.23845),
    ('sensor_02', 1.76421),
    ('sensor_03', 5.63614);

-- ✅ Confirm setup
SELECT 'Simple pressure sensor database ready!' as status;
SELECT COUNT(*) as test_records FROM pressure_readings;