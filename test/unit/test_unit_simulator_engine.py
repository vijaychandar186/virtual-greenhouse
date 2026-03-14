import unittest
from unittest.mock import patch

from test.simulator.src import engine


class TestSimulatorEngineUnit(unittest.TestCase):
    def test_generate_value_boolean_and_text(self):
        self.assertIn(engine.generate_value({"name": "ok", "type": "boolean"}), [True, False])
        self.assertEqual(engine.generate_value({"name": "label", "type": "text"}), "sensor")

    def test_generate_value_uses_schema_min_max(self):
        field = {"name": "temperature_c", "type": "number", "unit": "°C", "min": 10, "max": 45, "decimals": 1}
        with patch.object(engine.random, "gauss", return_value=0):
            v = engine.generate_value(field, prev=None)
        self.assertIsInstance(v, float)
        self.assertTrue(10 <= v <= 45)
        self.assertAlmostEqual(v, round(v, 1))

    def test_generate_value_falls_back_to_0_100(self):
        field = {"name": "unknown_sensor", "type": "number", "unit": ""}
        with patch.object(engine.random, "gauss", return_value=0):
            v = engine.generate_value(field, prev=None)
        self.assertTrue(0 <= v <= 100)

    def test_generate_reading_uses_prev_for_drift(self):
        schema_fields = [{"name": "humidity_pct", "type": "number", "unit": "%", "min": 20, "max": 95}]
        with patch.object(engine.random, "gauss", return_value=0):
            r1 = engine.generate_reading(schema_fields, prev_reading=None)
            r2 = engine.generate_reading(schema_fields, prev_reading=r1)
        self.assertIn("humidity_pct", r1)
        self.assertIn("humidity_pct", r2)


if __name__ == "__main__":
    unittest.main()
