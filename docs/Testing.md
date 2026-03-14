# Testing the Simulator

The simulator fetches a schema from `/api/schemas`, then generates values for each field using only what the schema says — no hardcoded guesses.

## 0. Start the app first

From the `virtual-greenhouse/` directory:
```bash
bash start.sh
# or
python -m src.app
```
The API runs on port 5000. Everything below requires it to be running.

**Each field drives its own stats:**
```json
{ "name": "temperature_c", "type": "number", "unit": "°C", "min": 10, "max": 45, "decimals": 1 }
```
If `min`/`max` are omitted the engine falls back to `0–100`.

---

## 1. Create a schema with ranges

```bash
curl -s -X POST http://localhost:5000/api/schemas \
  -H "X-API-Key: dev-sensor-token" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "climate_v2",
    "description": "Greenhouse climate sensor",
    "fields": [
      { "name": "temperature_c", "type": "number", "unit": "°C",  "min": 10,  "max": 45,   "decimals": 1 },
      { "name": "humidity_pct",  "type": "number", "unit": "%",   "min": 20,  "max": 95,   "decimals": 1 },
      { "name": "co2_ppm",       "type": "number", "unit": "ppm", "min": 350, "max": 2000, "decimals": 0 },
      { "name": "light_lux",     "type": "number", "unit": "lux", "min": 0,   "max": 1200, "decimals": 0 },
      { "name": "fan_on",        "type": "boolean" },
      { "name": "status",        "type": "text" }
    ]
  }' | python3 -m json.tool
```

## 2. Verify the schema was saved with ranges

```bash
curl -s http://localhost:5000/api/schemas \
  -H "X-API-Key: dev-sensor-token" | python3 -m json.tool
```

Each field should include `min`, `max`, `decimals` in the response.

## 3. Run the CLI simulator against that schema

```bash
cd test/simulator
python sensor_simulator.py \
  --schema climate_v2 \
  --device-id test-device-01 \
  --interval 5 \
  --count 10
```

Or run it forever:
```bash
python sensor_simulator.py --schema climate_v2 --device-id test-device-01
```

## 4. Check ingested readings

```bash
curl -s http://localhost:5000/api/latest \
  -H "X-API-Key: dev-sensor-token" | python3 -m json.tool
```

## 5. Use the simulator web UI

Start the simulator server separately:
```bash
cd test/simulator
python server.py
```
Open [http://localhost:5001](http://localhost:5001), pick `climate_v2` from the schema dropdown, set a device ID and interval, click **Start Simulation**.

The schema fields preview shows exactly what will be generated. Values stay within the `min`/`max` you defined.

## 6. Run unit tests

```bash
cd virtual-greenhouse
python -m pytest test/unit/test_unit_simulator_engine.py -v
```

## 7. Custom / arbitrary schemas

The simulator handles any schema — field names don't need to match any preset keywords. As long as `min` and `max` are set on the field, generation is realistic:

```bash
curl -s -X POST http://localhost:5000/api/schemas \
  -H "X-API-Key: dev-sensor-token" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "custom_sensor",
    "fields": [
      { "name": "ambient_reading", "type": "number", "unit": "°C", "min": 15, "max": 40, "decimals": 1 },
      { "name": "canopy_vpd",      "type": "number", "unit": "kPa","min": 0,  "max": 3,  "decimals": 2 }
    ]
  }'
```

Without `min`/`max`, values fall back to `0–100`.
