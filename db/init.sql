-- 📊 Telemetry MVP - Database Schema
-- TimescaleDB setup with unified telemetry table

-- Create extension for TimescaleDB
CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;

-- Main telemetry table (from your spec)
CREATE TABLE telemetry (
  ts          TIMESTAMPTZ      NOT NULL,      -- device-provided UTC time
  source      TEXT             NOT NULL,      -- 'PLC' or 'NI-DAQ'
  sensor      TEXT             NOT NULL,      -- canonical sensor ID
  value       DOUBLE PRECISION NOT NULL,      -- measured value in SI units
  ingest_ts   TIMESTAMPTZ      NOT NULL DEFAULT now(), -- when we wrote it
  metadata    JSONB            DEFAULT '{}'   -- quality flags, sample_rate, etc.
);

-- Sensor metadata table
CREATE TABLE sensors (
  sensor      TEXT PRIMARY KEY,   -- same IDs as in telemetry.sensor
  units       TEXT,               -- e.g. 'kPa', '°C'
  team        TEXT                -- 'facilities' or 'maker'
);

-- Convert to TimescaleDB hypertable for time-series optimization
SELECT create_hypertable('telemetry', 'ts');

-- Add unique constraint to prevent duplicates (needed for PLC client UPSERT)
ALTER TABLE telemetry ADD CONSTRAINT unique_reading UNIQUE (ts, source, sensor);

-- Create indexes for performance
CREATE INDEX ON telemetry (sensor, ts DESC);
CREATE INDEX ON telemetry (source, ts DESC);
CREATE INDEX ON telemetry (ts DESC, sensor);

-- Insert sample sensor metadata
INSERT INTO sensors (sensor, units, team) VALUES
-- PLC sensors (facilities team)
('ADS.PLC1.GVL_Pressures.P_500_PT_200', 'kPa', 'facilities'),
('ADS.PLC1.GVL_Pressures.P_200_PT_100', 'kPa', 'facilities'),
('ADS.PLC1.GVL_Pressures.P_200_PT_200', 'kPa', 'facilities'),
('ADS.PLC1.GVL_Pressures.P_200_PT_300', 'kPa', 'facilities'),
('ADS.PLC1.GVL_Pressures.P_300_PT_100', 'kPa', 'facilities'),
('ADS.PLC1.GVL_Pressures.P_300_PT_200', 'kPa', 'facilities'),
('ADS.PLC1.GVL_Pressures.P_300_PT_300', 'kPa', 'facilities'),
('ADS.PLC1.GVL_Pressures.P_300_PT_400', 'kPa', 'facilities'),
('ADS.PLC1.GVL_Pressures.P_300_PT_500', 'kPa', 'facilities'),
('ADS.PLC1.GVL_Pressures.P_400_PT_100', 'kPa', 'facilities'),
('ADS.PLC1.GVL_Pressures.P_400_PT_200', 'kPa', 'facilities'),
('ADS.PLC1.GVL_Pressures.P_400_PT_300', 'kPa', 'facilities'),
('ADS.PLC1.GVL_Pressures.P_400_PT_400', 'kPa', 'facilities'),
('ADS.PLC1.GVL_Pressures.P_400_PT_500', 'kPa', 'facilities'),
('ADS.PLC1.GVL_Pressures.P_500_PT_100', 'kPa', 'facilities'),

-- NI-DAQ sensors (maker team)
('ground_accel_x', 'g', 'maker'),
('ground_accel_y', 'g', 'maker'),
('ground_accel_z', 'g', 'maker'),
('ground_accel_x_rms', 'g', 'maker'),
('ground_accel_y_rms', 'g', 'maker'),
('ground_accel_z_rms', 'g', 'maker'),
('lower_bearing_temp_1', '°C', 'maker'),
('lower_bearing_temp_2', '°C', 'maker'),
('lower_bearing_temp_3', '°C', 'maker'),
('lower_bearing_load_x', 'kgf', 'maker'),
('lower_bearing_load_y', 'kgf', 'maker'),
('lower_bearing_load_z', 'kgf', 'maker'),
('upper_bearing_load_x', 'kgf', 'maker'),
('upper_bearing_load_y', 'kgf', 'maker'),
('upper_bearing_load_z', 'kgf', 'maker'),
('stator_temp_1', '°C', 'maker'),
('stator_temp_2', '°C', 'maker'),
('lower_rotor_position_x', 'mm', 'maker'),
('lower_rotor_position_y', 'mm', 'maker'),
('upper_rotor_position_x', 'mm', 'maker'),
('upper_rotor_position_y', 'mm', 'maker'),
('upper_bearing_position_x', 'mm', 'maker'),
('upper_bearing_position_y', 'mm', 'maker'),
('tachometer', 'pulse', 'maker');

-- Verify setup
SELECT 'TimescaleDB telemetry database ready!' as status;
SELECT COUNT(*) as sensor_count FROM sensors;
