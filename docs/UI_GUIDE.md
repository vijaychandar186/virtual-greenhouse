# Virtual Greenhouse — UI Guide

A complete walkthrough of every page and feature in the web interface.

---

## Table of Contents

1. [Getting Started](#1-getting-started)
2. [Registration & Login](#2-registration--login)
3. [Dashboard](#3-dashboard)
4. [Greenhouses](#4-greenhouses)
5. [Sensor Schemas](#5-sensor-schemas)
6. [Data Feed](#6-data-feed)
7. [Charts & Overview](#7-charts--overview)
8. [Notifications & Alerts](#8-notifications--alerts)
9. [Settings](#9-settings)
10. [Simulator](#10-simulator)
11. [Quick-Start Walkthrough](#11-quick-start-walkthrough)

---

## 1. Getting Started

### Prerequisites

- Python 3.14+
- [uv](https://docs.astral.sh/uv/) (recommended) or pip

### Installation

```bash
git clone https://github.com/vijaychandar186/virtual-greenhouse && cd virtual-greenhouse
uv sync          # or: pip install -r requirements.txt
cp src/.env.example .env
```

### Running the server

```bash
python -m src.app
```

The app starts on **http://localhost:5000**. A SQLite database is created
automatically at `instance/virtual_greenhouse.db` on first run — no database
setup is required.

---

## 2. Registration & Login

### Creating an account

1. Navigate to **http://localhost:5000/register**.
2. Fill in the form:

| Field    | Rules                              |
|----------|------------------------------------|
| Username | Letters and numbers only, must be unique |
| Password | Any non-empty string               |
| Email    | Must match `name@domain.tld` format |

3. Click **Register**.
4. An API key is automatically generated for your account (you can view it
   later on the Settings page).
5. You are redirected to the login page.

### Logging in

1. Navigate to **http://localhost:5000/login**.
2. Enter your username and password.
3. Click **Login**.
4. On success, you land on the **Dashboard**.

### Logging out

1. In the sidebar, click your **username** at the bottom.
2. Click **Logout**.
3. Your session is cleared and browser cache is invalidated so no stale pages
   are shown.

---

## 3. Dashboard

**Sidebar:** Dashboard
**URL:** `/dashboard`

The dashboard is the home page after login. It provides a high-level snapshot
of your system.

### Summary cards

Four cards across the top show:

| Card            | What it shows                        |
|-----------------|--------------------------------------|
| Greenhouses     | Total number of greenhouses you own  |
| Schemas         | Total number of sensor schemas       |
| Sensor Readings | Total readings across all greenhouses |
| Devices         | Number of unique sensor device IDs   |

### Unacknowledged alerts

If any notification rules have triggered, the unacknowledged alerts are shown
here as a list. Each alert shows:

- The greenhouse name
- The field and value that triggered it
- The rule condition (e.g. "temperature_c > 35")
- A timestamp
- An **Acknowledge** button to dismiss the alert

### Greenhouse status cards

Each greenhouse is displayed as a card showing:

- Greenhouse name and location
- The most recent reading (timestamp and data values)
- Number of devices reporting to this greenhouse
- Total number of readings

### Onboarding checklist

If you have no schemas or greenhouses yet, a helpful checklist appears guiding
you through the setup:

1. Create a sensor schema
2. Create a greenhouse
3. Send your first reading (or use the simulator)
4. Set up alerts

---

## 4. Greenhouses

A greenhouse is a logical grouping for your sensor devices and readings.

### Creating a greenhouse

**Sidebar:** Greenhouses → Create
**URL:** `/create_greenhouse`

1. Fill in the form:

| Field           | Required | Description                                  |
|-----------------|----------|----------------------------------------------|
| Name            | Yes      | A descriptive name (e.g. "Main Greenhouse")  |
| Location        | Yes      | Physical location (e.g. "Building A, Rooftop") |
| Description     | No       | Notes about this greenhouse                  |
| Primary Schema  | No       | Select an existing schema to associate        |

2. Click **Create Greenhouse**.
3. You are redirected with a confirmation message.

### Viewing your greenhouses

**Sidebar:** Greenhouses → Existing
**URL:** `/existing_greenhouse`

This page shows all your greenhouses as cards. Each card displays:

- **Name** and **location**
- **Latest reading** — timestamp and data values from the most recent ingest
- **Devices** — count of unique sensor devices reporting to this greenhouse
- **Readings** — total number of sensor readings stored

---

## 5. Sensor Schemas

Schemas define the structure of your sensor data — what fields exist, their
data types, and units of measurement.

**Sidebar:** Schemas
**URL:** `/schemas`

### Choosing a template

The top of the page shows template cards. Click one to pre-fill the schema
editor:

| Template          | Fields                                                         |
|-------------------|----------------------------------------------------------------|
| Climate Monitor   | temperature_c, humidity_pct, co2_ppm, light_lux, pressure_hpa |
| Hydroponics       | ph, ec_ms_cm, water_temp_c, dissolved_o2_ppm, water_level_cm  |
| Soil Monitoring   | soil_moisture_pct, soil_temp_c, soil_ph, soil_ec_ds_m         |
| Energy Monitor    | voltage_v, current_a, power_w, energy_kwh, power_factor       |
| Irrigation        | flow_rate_lpm, pressure_hpa, valve_open, tank_level_pct       |
| Weather Station   | temperature_c, humidity_pct, wind_speed_ms, rain_mm, uv_index, solar_rad_wm2 |
| CO₂ Enrichment    | co2_ppm, setpoint_ppm, injection_active, tank_pressure_bar, flow_lpm |
| Custom            | Empty — define your own fields from scratch                    |

### Editing fields

After selecting a template (or Custom), the editor panel opens. For each
field you can:

- **Edit the name** — type directly in the field name input
- **Edit the unit** — e.g. "°C", "%", "ppm"
- **Change the type** — dropdown: `number`, `boolean`, or `text`
- **Reorder** — click the **↑** button to move a field up
- **Remove** — click the **✕** button
- **Add** — click **+ Add Field** to append a new blank field

### Saving

1. Enter a **Schema Name** (e.g. `climate_v1`, `hydro_sensors`). This is the
   identifier used when sending data.
2. Optionally add a **Description**.
3. Click **Save Schema**.

### Saved schemas

Below the editor, all your saved schemas are listed. Each shows:

- Schema name and description
- Number of fields, displayed as pills (field name, type, and unit)
- Creation date
- **Delete** button (with confirmation). Deleting a schema does **not** delete
  existing readings — only the schema definition is removed.

### API example

Each saved schema has an expandable **"Show API example"** section with a
ready-to-use `curl` command for ingesting data using that schema.

---

## 6. Data Feed

**Sidebar:** Data Feed
**URL:** `/sensor_status`

The data feed shows the **last 100 sensor readings** across all greenhouses in
a table.

### Table columns

| Column     | Description                                    |
|------------|------------------------------------------------|
| Timestamp  | When the reading was recorded                  |
| Schema     | Name of the sensor schema                      |
| Device     | Device ID that sent the reading                |
| Greenhouse | Greenhouse name (if associated)                |
| Data       | Sensor values displayed as labeled pills       |

### Simulate Readings button

At the top of the page, click **Simulate Readings** to generate one fake
reading per saved schema. This is useful for testing without real hardware.
See [Simulator](#10-simulator) for details.

---

## 7. Charts & Overview

**Sidebar:** Overview
**URL:** `/overview`

The overview page is your custom charting dashboard.

### Adding a chart

1. In the **Add Chart** panel, fill in:

| Field      | Required | Description                                |
|------------|----------|--------------------------------------------|
| Chart Name | Yes      | A label for the chart                      |
| Type       | Yes      | **Line**, **Bar**, or **Gauge**            |
| Schema     | Yes      | Which sensor schema to pull data from      |
| Field      | Yes      | Which field to plot (e.g. `temperature_c`) |
| Greenhouse | No       | Filter data to a specific greenhouse       |
| Color      | No       | Hex color for the chart (default: green)   |

2. Click **Add Chart**.

### Chart types

| Type  | Description                                                  |
|-------|--------------------------------------------------------------|
| Line  | Time-series line chart of historical values                  |
| Bar   | Time-series bar chart of historical values                   |
| Gauge | Displays only the most recent value; **auto-refreshes every 30 seconds** |

### Managing charts

- Charts are displayed in a responsive grid.
- Click **Delete** on any chart card to remove it.
- Charts are saved per-user and persist across sessions.

---

## 8. Notifications & Alerts

**Sidebar:** Alerts
**URL:** `/notifications`

Set up threshold-based rules that trigger alerts when sensor values cross
defined limits.

### Creating a rule

1. In the **Create Rule** panel, fill in:

| Field          | Required | Description                                      |
|----------------|----------|--------------------------------------------------|
| Field Name     | Yes      | Sensor field to monitor (e.g. `temperature_c`)   |
| Operator       | Yes      | `>` , `>=` , `<` , `<=` , or `=`                 |
| Threshold      | Yes      | Numeric value to compare against                 |
| Greenhouse     | No       | Scope the rule to one greenhouse (or leave blank for all) |
| Schema         | No       | Scope the rule to one schema                     |
| Custom Message | No       | Override the default alert text                  |

2. Click **Create Rule**.

### How rules are evaluated

Every time sensor data arrives via the ingest endpoint:

1. All **enabled** rules are checked — both rules scoped to the specific
   greenhouse and global rules (no greenhouse specified).
2. If the monitored field exists in the reading and the condition is true, an
   **alert** is created.
3. If [Twilio SMS is configured](#twilio-sms-optional), a text message is sent
   immediately.

### Managing rules

On the Alerts page, each rule shows:

- The field, operator, and threshold
- The associated greenhouse and schema (if scoped)
- A **toggle switch** to enable or disable the rule without deleting it
- A **Delete** button to permanently remove it

### Viewing alerts

Alerts appear in two places in the UI:

1. **Dashboard** — unacknowledged alerts shown prominently at the top
2. **Alerts page** — full chronological list in the right sidebar

Each alert shows:
- Greenhouse name
- The field, its value, and the rule that was triggered
- Timestamp
- **Acknowledge** button to mark it as read

### Twilio SMS (optional)

To receive SMS alerts, set these environment variables before starting the
server:

```bash
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=your_auth_token
TWILIO_NUMBER=+15551234567       # Your Twilio phone number
TWILIO_RECIPIENT=+15559876543    # Phone number to receive alerts
```

All four must be set. If any are missing, SMS is silently skipped and alerts
are still saved to the database.

SMS examples:

```
[Main Greenhouse] Alert: temperature_c is above 35.0 (current: 37.2)
[Main Greenhouse] Temperature too high! (temperature_c = 37.2)
```

---

## 9. Settings

**Sidebar:** Username → Settings
**URL:** `/settings`

### Profile information

Displays your username and email address.

### API key management

- Your personal API key is shown (masked by default).
- Click the **eye icon** to reveal the full key.
- Click **Copy** to copy it to your clipboard.
- Click **Rotate Key** to generate a new key. The old key is **immediately
  invalidated** — update any scripts, devices, or integrations that use it.

### Code examples

The Settings page includes ready-to-use code snippets showing how to use your
API key with `curl` and with the simulator.

---

## 10. Simulator

The built-in simulator generates realistic fake sensor readings for every saved
schema, so you can test the full system without real hardware.

### How to use it

1. Go to **Data Feed** (`/sensor_status`).
2. Click the **Simulate Readings** button.
3. One reading per schema is generated instantly.

### What it generates

Each simulated reading uses a device named `sim-<schema_name>` and produces
realistic values based on the field name and unit:

| Field pattern       | Simulated range   |
|---------------------|-------------------|
| temperature         | 18 – 32 °C       |
| humidity            | 40 – 85 %        |
| co2                 | 350 – 1200 ppm   |
| light / lux         | 100 – 1500 lux   |
| soil_moisture       | 20 – 80 %        |
| ph                  | 5.0 – 8.0        |
| pressure            | 980 – 1040 hPa   |
| flow                | 0.5 – 15 L/min   |
| boolean fields      | true or false     |
| other number fields | 0 – 100           |

Simulated readings have their `source` set to `"simulator"` so you can
distinguish them from real sensor data.

---

## 11. Quick-Start Walkthrough

A step-by-step guide to go from zero to charting data using only the UI:

1. **Start the server**
   ```bash
   python -m src.app
   ```

2. **Register** — go to http://localhost:5000/register and create an account.

3. **Log in** — go to http://localhost:5000/login.

4. **Create a schema** — go to **Schemas** in the sidebar. Pick a template
   (e.g. "Climate Monitor") and click **Save Schema**.

5. **Create a greenhouse** — go to **Greenhouses → Create**. Enter a name and
   location, optionally select your new schema as the primary, and click
   **Create Greenhouse**.

6. **Generate test data** — go to **Data Feed** and click **Simulate Readings**
   a few times. Each click generates one reading per schema.

7. **View your data** — the Data Feed table now shows your simulated readings.

8. **Create a chart** — go to **Overview**. Select your schema, pick a field
   (e.g. `temperature_c`), choose "Line" as the type, and click **Add Chart**.

9. **Set up an alert** — go to **Alerts**. Create a rule like
   "temperature_c > 30". Next time a reading exceeds 30°C, you'll see an alert
   on the Dashboard.

10. **Check the dashboard** — go to **Dashboard** to see your summary cards,
    greenhouse status, and any triggered alerts.
