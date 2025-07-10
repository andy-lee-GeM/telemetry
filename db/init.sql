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
  description TEXT,               -- human-friendly name
  units       TEXT,               -- e.g. 'kPa', '°C'
  location    TEXT                -- e.g. 'NUC1 shelf', 'motor bearing'
);

-- Convert to TimescaleDB hypertable for time-series optimization
SELECT create_hypertable('telemetry', 'ts');

-- Create indexes for performance
CREATE INDEX ON telemetry (sensor, ts DESC);
CREATE INDEX ON telemetry (source, ts DESC);
CREATE INDEX ON telemetry (ts DESC, sensor);

-- Insert sample sensor metadata
INSERT INTO sensors (sensor, description, units, location) VALUES
-- PLC sensors
('pressure_tank_01', 'Main Tank Pressure', 'kPa', 'NUC1 - Tank Area'),
('pressure_tank_02', 'Secondary Tank Pressure', 'kPa', 'NUC1 - Tank Area'),
('temp_ambient', 'Ambient Temperature', '°C', 'NUC1 - Control Room'),
('temp_coolant', 'Coolant Temperature', '°C', 'NUC1 - Cooling Loop'),
('flow_rate_01', 'Primary Flow Rate', 'L/min', 'NUC1 - Main Line'),
('valve_position_01', 'Control Valve Position', '%', 'NUC1 - Control Valve'),
('pump_speed', 'Pump Speed', 'RPM', 'NUC1 - Pump Station'),
('system_voltage', 'System Voltage', 'V', 'NUC1 - Power Panel'),

-- NI-DAQ sensors (based on your TDMS data)
('ground_accel_x', 'Ground Acceleration X-axis', 'g', 'NUC2 - Base Mount'),
('ground_accel_y', 'Ground Acceleration Y-axis', 'g', 'NUC2 - Base Mount'),
('ground_accel_z', 'Ground Acceleration Z-axis', 'g', 'NUC2 - Base Mount'),
('ground_accel_x_rms', 'Ground Acceleration X-axis RMS', 'g', 'NUC2 - Base Mount'),
('ground_accel_y_rms', 'Ground Acceleration Y-axis RMS', 'g', 'NUC2 - Base Mount'),
('ground_accel_z_rms', 'Ground Acceleration Z-axis RMS', 'g', 'NUC2 - Base Mount'),
('lower_bearing_temp_1', 'Lower Bearing Temperature 1', '°C', 'NUC2 - Lower Bearing'),
('lower_bearing_temp_2', 'Lower Bearing Temperature 2', '°C', 'NUC2 - Lower Bearing'),
('lower_bearing_temp_3', 'Lower Bearing Temperature 3', '°C', 'NUC2 - Lower Bearing'),
('lower_bearing_load_x', 'Lower Bearing Load X', 'N', 'NUC2 - Lower Bearing'),
('lower_bearing_load_y', 'Lower Bearing Load Y', 'N', 'NUC2 - Lower Bearing'),
('lower_bearing_load_z', 'Lower Bearing Load Z', 'N', 'NUC2 - Lower Bearing'),
('upper_bearing_load_x', 'Upper Bearing Load X', 'N', 'NUC2 - Upper Bearing'),
('upper_bearing_load_y', 'Upper Bearing Load Y', 'N', 'NUC2 - Upper Bearing'),
('upper_bearing_load_z', 'Upper Bearing Load Z', 'N', 'NUC2 - Upper Bearing'),
('stator_temp_1', 'Stator Temperature 1', '°C', 'NUC2 - Motor Stator'),
('stator_temp_2', 'Stator Temperature 2', '°C', 'NUC2 - Motor Stator'),
('lower_rotor_position_x', 'Lower Rotor Position X', 'mm', 'NUC2 - Lower Rotor'),
('lower_rotor_position_y', 'Lower Rotor Position Y', 'mm', 'NUC2 - Lower Rotor'),
('upper_rotor_position_x', 'Upper Rotor Position X', 'mm', 'NUC2 - Upper Rotor'),
('upper_rotor_position_y', 'Upper Rotor Position Y', 'mm', 'NUC2 - Upper Rotor'),
('tachometer', 'Tachometer RPM', 'RPM', 'NUC2 - Motor Shaft');

-- Verify setup
SELECT 'TimescaleDB telemetry database ready!' as status;
SELECT COUNT(*) as sensor_count FROM sensors;
