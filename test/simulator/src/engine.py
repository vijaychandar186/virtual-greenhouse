"""
Sensor value generation engine.

Given a schema field definition (name, type, unit, min, max, decimals),
produces realistic random values using drift simulation.

Statistical properties come entirely from the schema field — no keyword
guessing. Set `min`, `max`, and optionally `decimals` on each field when
defining the schema.
"""
import random


def generate_value(field, prev=None):
    """Generate a single realistic value for a schema field.

    Args:
        field: dict with keys 'name', 'type', and optionally 'min', 'max', 'decimals'
        prev: previous value for drift (optional)
    """
    ftype = field.get("type", "number")
    if ftype == "boolean":
        return random.choice([True, False])
    if ftype == "text":
        return "sensor"

    lo = field.get("min", 0)
    hi = field.get("max", 100)
    decimals = field.get("decimals", 2)
    midpoint = (lo + hi) / 2

    if prev is not None:
        noise_scale = (hi - lo) * 0.05
        drift = (midpoint - prev) * 0.25
        value = prev + drift + random.gauss(0, noise_scale)
    else:
        value = midpoint + random.gauss(0, (hi - lo) * 0.1)

    return round(max(lo, min(hi, value)), decimals)


def generate_reading(schema_fields, prev_reading=None):
    """Generate one complete reading dict for all fields in a schema."""
    reading = {}
    for field in schema_fields:
        name = field.get("name", "")
        if not name:
            continue
        prev = (prev_reading or {}).get(name)
        reading[name] = generate_value(field, prev=prev)
    return reading
