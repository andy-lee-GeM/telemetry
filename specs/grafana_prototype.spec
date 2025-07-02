# 📊 Telemetry MVP: Pressure Sensor Dashboard

## 🎯 Goal

Build a simple, real-time telemetry system that:
- Displays a dashboard of **10 pressure sensors** over time
- Uses **Grafana** to visualize data from a **PostgreSQL** database
- Runs entirely using **Docker**, with a single-line setup
- Helps the engineer (you!) **learn how Docker, Postgres, and Grafana work together**

---

## 🧱 Stack Overview

| Layer        | Tool         | Purpose                               |
|--------------|--------------|----------------------------------------|
| Dashboard UI | Grafana      | Visualize sensor data over time        |
| Database     | PostgreSQL   | Store timestamped sensor readings      |
| Backend Script | Python     | Simulate & insert fake sensor data     |
| Runtime Env  | Docker       | Run Postgres + Grafana without installs|

---

## 🧪 Scope

- ✅ 1 dashboard with 10 pressure sensor plots
- ✅ Sensor values simulated and logged in Postgres
- ✅ Docker setup so teammates can launch it easily
- 🚧 Build everything **incrementally**, to learn as you go

---

## 🧭 Step-by-Step Milestones

### 🔹 Milestone 1: Project Setup

**Goal:** Scaffold file and folder structure for the system.

- [ ] Create a root folder: `telemetry-mvp/`
- [ ] Inside it, create folders:
  - `db/` → holds Postgres setup & Python seed script
  - `grafana/provisioning/` → holds Grafana configs
  - `grafana/dashboards/` → holds the saved dashboard JSON
- [ ] Create `docker-compose.yml` in the root

---

### 🔹 Milestone 2: Run PostgreSQL with Docker

**Goal:** Understand how to run a database container locally.

- [ ] Define Postgres service in `docker-compose.yml`
- [ ] Write `db/init.sql` to define a `telemetry` table
- [ ] Run `docker-compose up` to start the database
- [ ] Confirm it's working by connecting via:
  - Python (later step)
  - or Postgres GUI (e.g., DBeaver or pgAdmin)

---

### 🔹 Milestone 3: Simulate Pressure Sensor Data

**Goal:** Learn how to connect Python to Postgres and insert data.

- [ ] Write `db/seed.py` to simulate 10 sensors over time
- [ ] Use `psycopg2` to connect and insert rows
- [ ] Run the script to populate the DB
- [ ] Inspect DB to verify values were inserted

---

### 🔹 Milestone 4: Run Grafana with Docker

**Goal:** Understand how Grafana runs inside Docker and connects to the DB.

- [ ] Add Grafana service to `docker-compose.yml`
- [ ] Expose port 3000 to access Grafana UI
- [ ] Visit [http://localhost:3000](http://localhost:3000) and log in

---

### 🔹 Milestone 5: Connect Grafana to Postgres

**Goal:** Learn how Grafana pulls time-series data from Postgres.

- [ ] In Grafana UI, add a new PostgreSQL data source
- [ ] Use:
  - Host: `db:5432`
  - Database: `telemetry`
  - User: `admin`, Password: `admin`
- [ ] Test connection and save

---

### 🔹 Milestone 6: Build and Test Your First Dashboard

**Goal:** Learn Grafana basics by building a dashboard panel.

- [ ] Create a new dashboard
- [ ] Add a Time Series panel
- [ ] Use SQL to plot one pressure sensor:
  ```sql
  SELECT timestamp AS "time", value
  FROM telemetry
  WHERE sensor_name = 'pressure_1'
  ORDER BY timestamp ASC

# Final folder structure
telemetry-mvp/
├── docker-compose.yml
├── db/
│   ├── init.sql
│   └── seed.py
├── grafana/
│   ├── provisioning/
│   │   └── dashboards.yaml
│   └── dashboards/
│       └── pressure_dashboard.json
└── README.md

# Learning notes
┌─────────────────────────────────────┐
│           Your Laptop               │
│                                     │
│  ┌─────────────┐  ┌──────────────┐  │
│  │ PostgreSQL  │  │   Grafana    │  │
│  │ Container   │◄─│  Container   │  │
│  │ (db:5432)   │  │ (localhost:  │  │
│  │             │  │  3000)       │  │
│  └─────────────┘  └──────────────┘  │
│         ▲                ▲         │
│         │                │         │
│    (internal       (web browser    │
│     network)        access)        │
└─────────────────────────────────────┘