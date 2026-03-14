"""
CLI sensor simulator - pushes readings to /api/ingest for any schema.

Usage examples:
  # Simulate built-in climate data (backward compat):
  python scripts/sensor_simulator.py

  # Simulate any schema defined in the app (fetches field defs from API):
  python scripts/sensor_simulator.py --schema my_schema --auto

  # Simulate a specific schema with explicit fields:
  python scripts/sensor_simulator.py --schema hydro_v1 \
      --fields temperature_c:number:°C humidity_pct:number:% ph:number

For a full web-based simulator with a UI, run: python simulator/server.py
"""
import argparse
import math
import random
import sys
import time
from datetime import datetime, timezone

import requests


# ---------------------------------------------------------------------------
# Built-in climate generator (backward-compatible)
# ---------------------------------------------------------------------------

def _clamp(value, low, high):
    return max(low, min(high, value))


def _diurnal_factor(hour):
    return (math.sin((hour - 6) / 24 * 2 * math.pi) + 1) / 2


def _generate_climate(now, last=None):
    hour = now.hour + now.minute / 60
    day = _diurnal_factor(hour)
    target = {
        "temperature": 18 + 12 * day,
        "humidity": 68 - 18 * day,
        "light": 80 + 820 * day,
        "co2": 520 - 90 * day,
        "soil_moisture": 0.46 - 0.09 * day,
    }
    if last:
        reading = {}
        for key, val in target.items():
            prev = last.get(key, val)
            drift = (val - prev) * 0.35
            noise = random.uniform(-0.6, 0.6)
            if key == "light":
                noise *= 6
            if key == "soil_moisture":
                noise *= 0.02
            reading[key] = prev + drift + noise
    else:
        reading = {
            "temperature": target["temperature"] + random.uniform(-0.8, 0.8),
            "humidity": target["humidity"] + random.uniform(-1.2, 1.2),
            "light": target["light"] + random.uniform(-25, 25),
            "co2": target["co2"] + random.uniform(-18, 18),
            "soil_moisture": target["soil_moisture"] + random.uniform(-0.02, 0.02),
        }
    reading["temperature"] = round(_clamp(reading["temperature"], 10, 36), 1)
    reading["humidity"] = round(_clamp(reading["humidity"], 35, 90), 1)
    reading["light"] = round(_clamp(reading["light"], 0, 1200), 0)
    reading["co2"] = round(_clamp(reading["co2"], 350, 1200), 0)
    reading["soil_moisture"] = round(_clamp(reading["soil_moisture"], 0.18, 0.75), 3)
    return reading


# ---------------------------------------------------------------------------
# Dynamic value generator (for any schema field)
# ---------------------------------------------------------------------------

_RANGES = [
    (["temp"],                  ["°c", "celsius", "degc"], 10,   45,  1),
    (["humid", "rh"],           ["%rh"],                   20,   95,  1),
    (["co2"],                   ["ppm"],                  350, 2000,  0),
    (["light", "lux", "par"],   ["lux"],                    0, 1200,  0),
    (["ph"],                    [],                         4.5,  8.5, 2),
    (["moisture", "soil"],      ["vwc"],                    0.1,  0.9, 3),
    (["pressure"],              ["hpa", "mbar"],          980, 1040,  1),
    (["flow"],                  ["l/min", "lpm"],            0,  200,  1),
    (["voltage", "volt"],       ["v"],                       0,    5,  2),
    (["power", "watt"],         ["w"],                       0,  500,  1),
    (["ec", "conductiv"],       ["ms/cm"],                   0,    5,  2),
    (["battery", "soc"],        ["%"],                       0,  100,  1),
]


def _field_range(name, unit):
    n = name.lower()
    u = unit.lower()
    for nk, uk, lo, hi, dec in _RANGES:
        if any(k in n for k in nk) or any(k in u for k in uk):
            return lo, hi, dec
    if "%" in u:
        return 0, 100, 1
    return 0, 100, 2


def _generate_dynamic(fields, last=None):
    now = datetime.now(timezone.utc)
    hour = now.hour + now.minute / 60
    day = _diurnal_factor(hour)
    reading = {}
    for f in fields:
        name = f["name"]
        ftype = f.get("type", "number")
        unit = f.get("unit", "")
        if ftype == "boolean":
            reading[name] = random.choice([True, False])
            continue
        if ftype == "text":
            reading[name] = "sensor"
            continue
        lo, hi, dec = _field_range(name, unit)
        mid = (lo + hi) / 2
        noise_scale = (hi - lo) * 0.05
        if last and name in last:
            drift = (mid - last[name]) * 0.25
            val = last[name] + drift + random.gauss(0, noise_scale)
        else:
            val = mid + random.gauss(0, (hi - lo) * 0.1)
        reading[name] = round(max(lo, min(hi, val)), dec)
    return reading


def _fetch_schema_fields(base_url, api_key, schema_name):
    """Fetch field definitions for a named schema from the main app."""
    try:
        resp = requests.get(
            f"{base_url}/api/schemas",
            headers={"X-API-Key": api_key},
            timeout=5,
        )
        if not resp.ok:
            return None
        for s in resp.json().get("schemas", []):
            if s["name"] == schema_name:
                return s.get("fields", [])
    except Exception as exc:
        print(f"Warning: could not fetch schema: {exc}", file=sys.stderr)
    return None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Simulate sensor readings for any schema.")
    parser.add_argument("--url", default="http://localhost:5000/api/ingest")
    parser.add_argument("--api-key", default="dev-sensor-token")
    parser.add_argument("--device-id", default="sim-gh-1-main")
    parser.add_argument("--greenhouse-id", type=int, default=1)
    parser.add_argument("--interval", type=float, default=10.0)
    parser.add_argument("--count", type=int, default=0, help="0 = run forever")
    parser.add_argument("--schema", default="climate_v1",
                        help="Schema name to use when sending data.")
    parser.add_argument("--auto", action="store_true",
                        help="Fetch schema field definitions from the app API and simulate accordingly.")
    parser.add_argument("--fields", nargs="*", default=[],
                        help="Explicit field specs as name:type:unit (e.g. temperature_c:number:°C).")
    args = parser.parse_args()

    base_url = args.url.rsplit("/api/", 1)[0]

    # Determine which generator to use
    explicit_fields = []
    for spec in args.fields:
        parts = spec.split(":")
        name = parts[0]
        ftype = parts[1] if len(parts) > 1 else "number"
        unit = parts[2] if len(parts) > 2 else ""
        explicit_fields.append({"name": name, "type": ftype, "unit": unit})

    if explicit_fields:
        fields = explicit_fields
        use_dynamic = True
    elif args.auto:
        fields = _fetch_schema_fields(base_url, args.api_key, args.schema)
        if fields is None:
            print(f"Schema '{args.schema}' not found in app. Falling back to climate_v1.", file=sys.stderr)
            fields = None
        use_dynamic = fields is not None
    elif args.schema != "climate_v1":
        # Non-default schema but no explicit fields - still try auto-fetch
        fields = _fetch_schema_fields(base_url, args.api_key, args.schema)
        use_dynamic = fields is not None
    else:
        fields = None
        use_dynamic = False

    if use_dynamic and not fields:
        print("No fields available - using climate_v1 defaults.", file=sys.stderr)
        use_dynamic = False

    last = None
    sent = 0
    print(f"Simulating schema='{args.schema}', device='{args.device_id}', interval={args.interval}s")
    if use_dynamic:
        print(f"Fields: {[f['name'] for f in fields]}")
    else:
        print("Fields: temperature, humidity, light, co2, soil_moisture (built-in climate)")

    while True:
        now = datetime.now(timezone.utc)
        if use_dynamic:
            reading = _generate_dynamic(fields, last=last)
        else:
            reading = _generate_climate(now, last=last)

        payload = {
            "device_id": args.device_id,
            "greenhouse_id": args.greenhouse_id,
            "recorded_at": now.isoformat(),
            "schema": args.schema,
            "data": reading,
        }
        resp = requests.post(
            args.url,
            json=payload,
            headers={"X-API-Key": args.api_key},
            timeout=10,
        )
        if resp.status_code >= 400:
            print(f"Error {resp.status_code}: {resp.text}")
        else:
            vals = ", ".join(f"{k}={v}" for k, v in list(reading.items())[:4])
            print(f"[{now.strftime('%H:%M:%S')}] Sent #{sent + 1}  {vals}{'...' if len(reading) > 4 else ''}")

        last = reading
        sent += 1
        if args.count and sent >= args.count:
            break
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
