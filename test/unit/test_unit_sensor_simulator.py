import unittest
from datetime import datetime, timezone
from unittest.mock import patch, Mock

import scripts.sensor_simulator as sim


class TestSensorSimulatorUnit(unittest.TestCase):
    def test_clamp(self):
        self.assertEqual(sim._clamp(5, 10, 20), 10)
        self.assertEqual(sim._clamp(25, 10, 20), 20)
        self.assertEqual(sim._clamp(15, 10, 20), 15)

    def test_diurnal_factor_known_points(self):
        self.assertAlmostEqual(sim._diurnal_factor(6), 0.5, places=6)
        self.assertAlmostEqual(sim._diurnal_factor(12), 1.0, places=6)
        self.assertAlmostEqual(sim._diurnal_factor(0), 0.0, places=6)

    def test_generate_climate_deterministic_without_noise(self):
        now = datetime(2026, 3, 13, 12, 0, tzinfo=timezone.utc)
        with patch.object(sim.random, "uniform", return_value=0):
            reading = sim._generate_climate(now, last=None)
        self.assertIn("temperature", reading)
        self.assertIn("humidity", reading)
        self.assertIn("light", reading)
        self.assertIn("co2", reading)
        self.assertIn("soil_moisture", reading)
        self.assertTrue(10 <= reading["temperature"] <= 36)
        self.assertTrue(35 <= reading["humidity"] <= 90)
        self.assertTrue(0 <= reading["light"] <= 1200)
        self.assertTrue(350 <= reading["co2"] <= 1200)
        self.assertTrue(0.18 <= reading["soil_moisture"] <= 0.75)

    def test_field_range_keyword_and_percent_fallback(self):
        self.assertEqual(sim._field_range("temperature_c", "°C")[:2], (10, 45))
        self.assertEqual(sim._field_range("battery_soc", "%")[:2], (0, 100))
        self.assertEqual(sim._field_range("unknown", "foo%")[:2], (0, 100))

    def test_generate_dynamic_boolean_and_text(self):
        fields = [
            {"name": "ok", "type": "boolean", "unit": ""},
            {"name": "label", "type": "text", "unit": ""},
        ]
        fixed = datetime(2026, 3, 13, 12, 0, tzinfo=timezone.utc)
        with patch.object(sim, "datetime") as dt, patch.object(sim.random, "choice", return_value=True):
            dt.now.return_value = fixed
            reading = sim._generate_dynamic(fields, last=None)
        self.assertEqual(reading["ok"], True)
        self.assertEqual(reading["label"], "sensor")

    def test_fetch_schema_fields_happy_path(self):
        resp = Mock()
        resp.ok = True
        resp.json.return_value = {"schemas": [{"name": "x", "fields": [{"name": "a"}]}]}
        with patch.object(sim.requests, "get", return_value=resp):
            fields = sim._fetch_schema_fields("http://localhost:5000", "k", "x")
        self.assertEqual(fields, [{"name": "a"}])

    def test_fetch_schema_fields_not_found(self):
        resp = Mock()
        resp.ok = True
        resp.json.return_value = {"schemas": [{"name": "y", "fields": []}]}
        with patch.object(sim.requests, "get", return_value=resp):
            fields = sim._fetch_schema_fields("http://localhost:5000", "k", "x")
        self.assertIsNone(fields)


if __name__ == "__main__":
    unittest.main()

