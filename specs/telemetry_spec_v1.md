## 1. Introduction  
We need a lightweight, on-premise telemetry platform that brings together real-time data from two independent acquisition systems—Beckhoff PLC (“facilities”) and NI-DAQ (“engineering”)—into a single time-series database and dashboard.  In under two weeks and for fewer than ten DAQs, this system will let engineers visualize, correlate, and alert on pressure, temperature, vibration and other key sensors during experiments, while laying groundwork to scale or swap components later.

## 2. Current System

### 2.1 Facilities (NUC 1)  
- **Hardware:** Beckhoff PLC running TwinCAT  
- **Data store:** PostgreSQL + TimescaleDB on NUC1  
- **Data model:** per-sensor tables of `(timestamp, sensor_name, value)`  
- **Access:** engineers query directly via SQL or ad-hoc scripts  

### 2.2 Engineering (NUC 2)  
- **Hardware:** NI-cDAQ chassis with FlexLogger  
- **Data store:** Local TDMS files dumped post-run  
- **Data model:** per-channel waveform segments in binary hierarchy  
- **Access:** export to CSV or read via NI tools for offline analysis  

---

## 3. System Architecture
           +----------------------+           +----------------------+
           |    NUC1 (PLC)        |           |   NUC2 (NI-DAQ)      |
           |  Postgres+Timescale  |           |   TDMS files         |
           +----------+-----------+           +----------+-----------+
                      |                                |
        Edge Client #1 |                                | Edge Client #2
      (polls Postgres, |                                | (reads TDMS via
      normalizes rows) |                                |  nptdms, JSONifies)
                      +------------+-------------------+
                                   |
                                   | writes normalized records
                                   v
                             +-----------+
                             | Central   |
                             | Timescale |
                             |   DB      |
                             +-----+-----+
                                   |
                                   | SQL / HTTP queries
                                   v
                             +-----------+
                             | Grafana   |
                             | Dashboard |
                             +-----------+

### Database schema
CREATE TABLE telemetry (
  ts          TIMESTAMPTZ      NOT NULL,      -- device‐provided UTC time
  source      TEXT             NOT NULL,      -- 'PLC' or 'NIC-DAQ'
  sensor      TEXT             NOT NULL,      -- canonical sensor ID
  value       DOUBLE PRECISION NOT NULL,      -- measured value in SI units
  ingest_ts   TIMESTAMPTZ      NOT NULL DEFAULT now(), -- when we wrote it
  metadata    JSONB                        DEFAULT '{}'  -- quality flags, sample_rate, etc.
);

CREATE TABLE sensors (
  sensor      TEXT PRIMARY KEY,   -- same IDs as in telemetry.sensor
  description TEXT,               -- human‐friendly name
  units       TEXT,               -- e.g. 'kPa', '°C'
  location    TEXT                -- e.g. 'NUC1 shelf', 'motor bearing'
);
