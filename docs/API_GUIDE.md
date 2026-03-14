# Virtual Greenhouse — API Guide

Complete reference for the REST API. All endpoints return JSON.

---

## Table of Contents

1. [Getting Started](#1-getting-started)
2. [Authentication](#2-authentication)
3. [Ingesting Sensor Data](#3-ingesting-sensor-data)
4. [Schemas](#4-schemas)
5. [Greenhouses](#5-greenhouses)
6. [Querying Data](#6-querying-data)
7. [Notifications & Alerts](#7-notifications--alerts)
8. [Identity](#8-identity)
9. [Error Handling](#9-error-handling)
10. [Quick-Start Walkthrough](#10-quick-start-walkthrough)
11. [Environment Variables](#11-environment-variables)

---

## 1. Getting Started

### Base URL

```
http://localhost:5000
```

### Running the server

```bash
git clone https://github.com/vijaychandar186/virtual-greenhouse && cd virtual-greenhouse
uv sync          # or: pip install -r requirements.txt
cp src/.env.example .env
python -m src.app
```

The database is created automatically on first run.

### Content type

All POST requests expect `Content-Type: application/json`.

---

## 2. Authentication

Most API endpoints require an API key. Pass it in one of two ways:

```bash
# Header (recommended)
curl -H "X-API-Key: <your-key>" http://localhost:5000/api/...

# Query parameter
curl http://localhost:5000/api/...?api_key=<your-key>
```

### Key types

| Type           | How to get it                        | Capabilities                                          |
|----------------|--------------------------------------|-------------------------------------------------------|
| Personal key   | Register an account, find it in Settings (`/settings`) | Readings linked to your user; can create/delete greenhouses |
| Global token   | `SENSOR_INGEST_TOKEN` env var (default: `dev-sensor-token`) | Shared ingest access; readings not linked to any user; cannot create greenhouses |

### Unauthenticated endpoints

These endpoints do not require an API key:

- `GET /api/schema` — API documentation
- `GET /api/latest` — most recent reading
- `GET /api/chart-data` — time-series data
- `GET /api/alerts` — recent alerts
- `POST /api/alerts/<id>/ack` — acknowledge an alert

---

## 3. Ingesting Sensor Data

The primary endpoint for sending sensor readings into the system.

### `POST /api/ingest`

**Auth:** Required

#### Request body

```json
{
  "device_id": "sensor-01",
  "greenhouse_id": 1,
  "schema": "climate_v1",
  "recorded_at": "2026-03-13T18:45:00Z",
  "source": "sensor",
  "label": "Main sensor",
  "data": {
    "temperature_c": 26.4,
    "humidity_pct": 67.2,
    "co2_ppm": 520
  }
}
```

#### Fields

| Field          | Type    | Required | Description                                          |
|----------------|---------|----------|------------------------------------------------------|
| `device_id`    | string  | **Yes**  | Unique identifier for the sensor device              |
| `greenhouse_id`| integer | No       | ID of the greenhouse this reading belongs to         |
| `schema`       | string  | No       | Schema name; auto-created if it doesn't exist (default: `"default"`) |
| `recorded_at`  | string/number | No | ISO 8601 string, Unix timestamp (seconds), or omit for current UTC time |
| `source`       | string  | No       | Label like `"sensor"`, `"simulator"`, etc. (default: `"sensor"`) |
| `label`        | string  | No       | Human-friendly name for the device                   |
| `data`         | object  | No       | Object containing sensor field key-value pairs       |

#### Flat payload alternative

Instead of wrapping values in a `data` object, you can put them at the top
level. Reserved keys (`device_id`, `greenhouse_id`, `recorded_at`, `timestamp`,
`source`, `schema`, `schema_name`, `data`, `label`) are automatically excluded.

```json
{
  "device_id": "sensor-01",
  "schema": "climate_v1",
  "temperature_c": 26.4,
  "humidity_pct": 67.2,
  "co2_ppm": 520
}
```

#### Response `200 OK`

```json
{
  "status": "ok",
  "recorded_at": "2026-03-13T18:45:00+00:00",
  "schema": "climate_v1"
}
```

#### Side effects

1. **Schema auto-creation** — if the named schema doesn't exist, it's created
   with fields inferred from the data keys. If it exists but the data has new
   keys, those fields are added to the schema.
2. **Device tracking** — the device is upserted in the `sensor_devices` table
   with `last_seen_at` updated.
3. **Notification evaluation** — if `greenhouse_id` is provided, all enabled
   notification rules are evaluated against the data. Triggered rules create
   alerts and optionally send SMS.

#### Example

```bash
curl -X POST http://localhost:5000/api/ingest \
  -H "X-API-Key: dev-sensor-token" \
  -H "Content-Type: application/json" \
  -d '{
    "device_id": "rpi-greenhouse-01",
    "greenhouse_id": 1,
    "schema": "climate_v1",
    "data": {
      "temperature_c": 24.5,
      "humidity_pct": 62.0,
      "co2_ppm": 480,
      "light_lux": 850
    }
  }'
```

#### Python example

```python
import requests

resp = requests.post(
    "http://localhost:5000/api/ingest",
    json={
        "device_id": "rpi-greenhouse-01",
        "greenhouse_id": 1,
        "schema": "climate_v1",
        "data": {
            "temperature_c": 25.3,
            "humidity_pct": 58.7,
            "co2_ppm": 510,
        },
    },
    headers={"X-API-Key": "your-api-key"},
)
print(resp.json())
```

---

## 4. Schemas

Schemas define the structure of sensor data — field names, types, and units.

### `GET /api/schemas`

**Auth:** Required

List all schemas.

#### Response

```json
{
  "schemas": [
    {
      "id": 1,
      "name": "climate_v1",
      "description": "Basic climate sensors",
      "fields": [
        { "name": "temperature_c", "type": "number", "unit": "°C" },
        { "name": "humidity_pct",  "type": "number", "unit": "%"  },
        { "name": "co2_ppm",      "type": "number", "unit": "ppm" }
      ],
      "created_at": "2026-03-13T12:00:00+00:00"
    }
  ]
}
```

---

### `POST /api/schemas`

**Auth:** Required

Create a new schema or update an existing one (matched by `name`). If a schema
with the same name exists, new fields are **merged** — existing fields are
preserved and new ones are added.

#### Request body

```json
{
  "name": "climate_v1",
  "description": "Basic climate sensors",
  "fields": ["temperature_c", "humidity_pct", "co2_ppm"]
}
```

Fields can be strings (shorthand) or objects (explicit type/unit):

```json
{
  "name": "climate_v1",
  "description": "Basic climate sensors",
  "fields": [
    { "name": "temperature_c", "type": "number", "unit": "°C" },
    { "name": "humidity_pct",  "type": "number", "unit": "%"  }
  ]
}
```

Fields can also be a comma-separated string: `"temperature_c, humidity_pct"`.

| Field         | Type          | Required | Description                          |
|---------------|---------------|----------|--------------------------------------|
| `name`        | string        | **Yes**  | Schema identifier (must be unique)   |
| `description` | string        | No       | Human-readable description           |
| `fields`      | array/string  | No       | Field definitions (see above)        |

#### Response

```json
{
  "status": "ok",
  "name": "climate_v1",
  "fields": [
    { "name": "temperature_c", "type": "number", "unit": "°C" },
    { "name": "humidity_pct",  "type": "number", "unit": "%"  }
  ]
}
```

---

## 5. Greenhouses

### `GET /api/greenhouses`

**Auth:** Required

List greenhouses. With a personal API key, returns only your greenhouses. With
the global token, returns all greenhouses.

#### Response

```json
{
  "greenhouses": [
    {
      "id": 1,
      "greenhouse_name": "Main Greenhouse",
      "location": "Building A, Rooftop",
      "description": "Primary growing area"
    }
  ]
}
```

---

### `POST /api/greenhouses`

**Auth:** Required (personal API key only — global token returns `403`)

Create a new greenhouse.

#### Request body

```json
{
  "greenhouse_name": "Main Greenhouse",
  "location": "Building A, Rooftop",
  "description": "Primary growing area",
  "primary_schema": "climate_v1"
}
```

| Field            | Type   | Required | Description                          |
|------------------|--------|----------|--------------------------------------|
| `greenhouse_name`| string | **Yes**  | Name (also accepts `name`)           |
| `location`       | string | **Yes**  | Physical location                    |
| `description`    | string | No       | Notes about this greenhouse          |
| `primary_schema` | string | No       | Associated schema name               |

#### Response `201 Created`

```json
{
  "status": "ok",
  "id": 1,
  "greenhouse_name": "Main Greenhouse",
  "location": "Building A, Rooftop"
}
```

---

### `DELETE /api/greenhouses/<id>`

**Auth:** Required (personal API key only)

Delete a greenhouse you own.

#### Response

```json
{ "status": "ok" }
```

#### Errors

- `403` — global token used (personal key required)
- `404` — greenhouse not found or not owned by you

---

## 6. Querying Data

### `GET /api/latest`

**Auth:** Not required

Returns the most recent sensor reading across all greenhouses.

#### Response

```json
{
  "latest": {
    "id": 42,
    "greenhouse_id": 1,
    "device_id": "sensor-01",
    "source": "sensor",
    "data": {
      "temperature_c": 24.5,
      "humidity_pct": 62.0
    },
    "recorded_at": "2026-03-13T18:45:00+00:00",
    "schema_name": "climate_v1"
  }
}
```

Returns `{ "latest": null }` if no readings exist.

---

### `GET /api/chart-data`

**Auth:** Not required

Returns time-series data for a single field, suitable for charting.

#### Query parameters

| Parameter      | Type    | Required | Description                                  |
|----------------|---------|----------|----------------------------------------------|
| `field`        | string  | **Yes**  | The schema field name to extract              |
| `schema_id`    | integer | No       | Filter by schema ID                          |
| `greenhouse_id`| integer | No       | Filter by greenhouse ID                      |
| `limit`        | integer | No       | Max data points (default: `200`)             |

#### Example

```bash
curl "http://localhost:5000/api/chart-data?field=temperature_c&schema_id=1&greenhouse_id=1&limit=100"
```

#### Response

```json
{
  "labels": ["2026-03-13 17:30", "2026-03-13 17:45", "2026-03-13 18:00"],
  "values": [23.8, 24.1, 24.5],
  "field": "temperature_c"
}
```

---

### `GET /api/schema`

**Auth:** Not required

Returns documentation about the ingest payload format.

#### Response

```json
{
  "required": ["device_id"],
  "optional": ["greenhouse_id", "recorded_at", "source", "schema", "data"],
  "example": {
    "device_id": "gh-1-main",
    "greenhouse_id": 1,
    "recorded_at": "2026-03-13T18:45:00Z",
    "schema": "climate_v1",
    "data": {
      "temperature_c": 26.4,
      "humidity_pct": 67.2,
      "light_lux": 740,
      "co2_ppm": 520,
      "soil_moisture": 0.42
    }
  },
  "auth": "Send X-API-Key header with your SENSOR_INGEST_TOKEN.",
  "note": "Any extra top-level keys outside 'data' become data fields automatically."
}
```

---

## 7. Notifications & Alerts

### `GET /api/notification-rules`

**Auth:** Required

List all notification rules.

#### Response

```json
{
  "rules": [
    {
      "id": 1,
      "field_name": "temperature_c",
      "operator": "gt",
      "threshold": 35.0,
      "message": "Temperature too high!",
      "enabled": 1,
      "greenhouse_name": "Main Greenhouse",
      "schema_name": "climate_v1"
    }
  ]
}
```

---

### `POST /api/notification-rules`

**Auth:** Required

Create a notification rule.

#### Request body

```json
{
  "field_name": "temperature_c",
  "operator": "gt",
  "threshold": 35.0,
  "greenhouse_id": 1,
  "schema_id": 1,
  "message": "Temperature too high!"
}
```

| Field          | Type    | Required | Description                                      |
|----------------|---------|----------|--------------------------------------------------|
| `field_name`   | string  | **Yes**  | Sensor field to monitor                          |
| `operator`     | string  | **Yes**  | One of: `gt`, `gte`, `lt`, `lte`, `eq`          |
| `threshold`    | number  | **Yes**  | Value to compare against                         |
| `greenhouse_id`| integer | No       | Scope to a greenhouse (null = all greenhouses)   |
| `schema_id`    | integer | No       | Scope to a schema                                |
| `message`      | string  | No       | Custom alert text                                |

#### Operators

| Operator | Meaning          | Example                      |
|----------|------------------|------------------------------|
| `gt`     | greater than     | temperature_c > 35           |
| `gte`    | greater or equal | humidity_pct >= 90           |
| `lt`     | less than        | soil_moisture_pct < 20       |
| `lte`    | less or equal    | water_level_cm <= 5          |
| `eq`     | equal to         | valve_open = 0               |

#### Response `201 Created`

```json
{ "status": "ok", "id": 1 }
```

---

### `DELETE /api/notification-rules/<id>`

**Auth:** Required

Delete a notification rule.

#### Response

```json
{ "status": "ok" }
```

---

### `GET /api/alerts`

**Auth:** Not required

List recent alerts.

#### Query parameters

| Parameter | Type    | Required | Default | Description            |
|-----------|---------|----------|---------|------------------------|
| `limit`   | integer | No       | `20`    | Max number of alerts   |

#### Example

```bash
curl "http://localhost:5000/api/alerts?limit=10"
```

#### Response

```json
{
  "alerts": [
    {
      "id": 1,
      "field_name": "temperature_c",
      "value": 37.2,
      "triggered_at": "2026-03-13T18:50:00+00:00",
      "acknowledged": 0,
      "message": "Temperature too high!",
      "operator": "gt",
      "threshold": 35.0,
      "greenhouse_name": "Main Greenhouse"
    }
  ]
}
```

---

### `POST /api/alerts/<id>/ack`

**Auth:** Not required

Acknowledge (dismiss) an alert.

#### Response

```json
{ "status": "ok" }
```

---

## 8. Identity

### `GET /api/me`

**Auth:** Required

Returns information about the authenticated user.

#### With a personal API key

```json
{
  "userid": 1,
  "username": "alice"
}
```

#### With the global ingest token

```json
{
  "note": "Using global ingest token"
}
```

---

## 9. Error Handling

All errors return a JSON object with an `error` key:

```json
{ "error": "device_id is required" }
```

### HTTP status codes

| Code | Meaning                                                   |
|------|-----------------------------------------------------------|
| 200  | Success                                                   |
| 201  | Resource created (greenhouses, notification rules)        |
| 400  | Bad request — missing or invalid parameters               |
| 401  | Unauthorized — missing or invalid API key                 |
| 403  | Forbidden — action requires a personal key, not the global token |
| 404  | Not found — resource doesn't exist or isn't owned by you  |

---

## 10. Quick-Start Walkthrough

End-to-end flow from zero to charting data using only the API:

```bash
# Use the default global token (or register and use your personal key)
API_KEY="dev-sensor-token"

# 1. Check connectivity
curl -H "X-API-Key: $API_KEY" http://localhost:5000/api/me

# 2. View the ingest schema documentation
curl http://localhost:5000/api/schema

# 3. Create a schema
curl -X POST http://localhost:5000/api/schemas \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "my_sensors",
    "description": "Test schema",
    "fields": [
      {"name": "temperature_c", "type": "number", "unit": "°C"},
      {"name": "humidity_pct",  "type": "number", "unit": "%"}
    ]
  }'

# 4. Create a greenhouse (requires a personal API key)
#    Register at http://localhost:5000/register first,
#    then find your key at http://localhost:5000/settings
PERSONAL_KEY="your-personal-key"

curl -X POST http://localhost:5000/api/greenhouses \
  -H "X-API-Key: $PERSONAL_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "greenhouse_name": "Test Greenhouse",
    "location": "Lab"
  }'

# 5. Send sensor readings
for temp in 22.1 23.4 24.8 25.2 26.0; do
  curl -s -X POST http://localhost:5000/api/ingest \
    -H "X-API-Key: $API_KEY" \
    -H "Content-Type: application/json" \
    -d "{
      \"device_id\": \"dev-01\",
      \"greenhouse_id\": 1,
      \"schema\": \"my_sensors\",
      \"data\": {
        \"temperature_c\": $temp,
        \"humidity_pct\": 55.0
      }
    }"
  sleep 1
done

# 6. Query the latest reading
curl http://localhost:5000/api/latest

# 7. Get chart data
curl "http://localhost:5000/api/chart-data?field=temperature_c&schema_id=1"

# 8. Set up an alert
curl -X POST http://localhost:5000/api/notification-rules \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "field_name": "temperature_c",
    "operator": "gt",
    "threshold": 25.0,
    "message": "Getting warm!"
  }'

# 9. Send a reading that triggers the alert
curl -X POST http://localhost:5000/api/ingest \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "device_id": "dev-01",
    "greenhouse_id": 1,
    "schema": "my_sensors",
    "data": {"temperature_c": 30.0, "humidity_pct": 70.0}
  }'

# 10. Check the triggered alerts
curl http://localhost:5000/api/alerts

# 11. Acknowledge the alert
curl -X POST http://localhost:5000/api/alerts/1/ack

# 12. List all schemas (now includes auto-discovered fields)
curl -H "X-API-Key: $API_KEY" http://localhost:5000/api/schemas

# 13. List your greenhouses
curl -H "X-API-Key: $PERSONAL_KEY" http://localhost:5000/api/greenhouses
```

---

## 11. Environment Variables

| Variable              | Default              | Description                              |
|-----------------------|----------------------|------------------------------------------|
| `SECRET_KEY`          | `dev-secret-key`     | Flask session secret — change in production |
| `SENSOR_INGEST_TOKEN` | `dev-sensor-token`   | Global API token for data ingestion      |
| `TWILIO_ACCOUNT_SID`  | *(unset)*            | Twilio account SID for SMS alerts        |
| `TWILIO_AUTH_TOKEN`    | *(unset)*            | Twilio auth token                        |
| `TWILIO_NUMBER`        | *(unset)*            | Twilio sender phone number (e.g. `+15551234567`) |
| `TWILIO_RECIPIENT`     | *(unset)*            | Phone number to receive alert SMS        |

The SQLite database is stored at `instance/virtual_greenhouse.db` relative to
the project root and is created automatically on first run.

---

## Endpoint Summary

| Method | Endpoint                              | Auth     | Description                    |
|--------|--------------------------------------|----------|--------------------------------|
| GET    | `/api/me`                            | Required | Authenticated user info        |
| GET    | `/api/schema`                        | None     | Ingest payload documentation   |
| GET    | `/api/greenhouses`                   | Required | List greenhouses               |
| POST   | `/api/greenhouses`                   | Personal | Create greenhouse              |
| DELETE | `/api/greenhouses/<id>`              | Personal | Delete greenhouse              |
| GET    | `/api/schemas`                       | Required | List schemas                   |
| POST   | `/api/schemas`                       | Required | Create/update schema           |
| POST   | `/api/ingest`                        | Required | Ingest sensor reading          |
| GET    | `/api/latest`                        | None     | Most recent reading            |
| GET    | `/api/chart-data`                    | None     | Time-series data               |
| GET    | `/api/notification-rules`            | Required | List notification rules        |
| POST   | `/api/notification-rules`            | Required | Create notification rule       |
| DELETE | `/api/notification-rules/<id>`       | Required | Delete notification rule       |
| GET    | `/api/alerts`                        | None     | List recent alerts             |
| POST   | `/api/alerts/<id>/ack`               | None     | Acknowledge alert              |
