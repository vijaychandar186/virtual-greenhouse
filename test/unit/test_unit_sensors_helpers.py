import unittest
from unittest.mock import patch

from src.routes import sensors as sensors_mod


class TestSensorsHelpersUnit(unittest.TestCase):
    def test_simulate_field_value_boolean_and_text(self):
        with patch.object(sensors_mod.random, "choice", return_value=False):
            self.assertEqual(
                sensors_mod._simulate_field_value({"name": "ok", "type": "boolean", "unit": ""}),
                False,
            )
        self.assertEqual(
            sensors_mod._simulate_field_value({"name": "label", "type": "text", "unit": ""}),
            "sensor",
        )

    def test_simulate_field_value_temperature_hint(self):
        with patch.object(sensors_mod.random, "uniform", return_value=20.0):
            v = sensors_mod._simulate_field_value({"name": "temperature_c", "type": "number", "unit": "°C"})
        self.assertEqual(v, 20.0)

    def test_simulate_all_numeric_branches(self):
        cases = [
            ({"name": "humidity", "type": "number", "unit": "%rh"}, 65.0, 65.0),
            ({"name": "co2_level", "type": "number", "unit": "ppm"}, 800.0, 800.0),
            ({"name": "light_lux", "type": "number", "unit": "lux"}, 600.0, 600.0),
            ({"name": "ph_level", "type": "number", "unit": ""}, 6.5, 6.5),
            ({"name": "soil_moisture", "type": "number", "unit": ""}, 0.5, 0.5),
            ({"name": "pressure", "type": "number", "unit": "hpa"}, 1010.0, 1010.0),
            ({"name": "flow_rate", "type": "number", "unit": "l/min"}, 50.0, 50.0),
            ({"name": "voltage", "type": "number", "unit": "V"}, 3.0, 3.0),
            ({"name": "power_watt", "type": "number", "unit": "W"}, 250.0, 250.0),
            ({"name": "level", "type": "number", "unit": "%"}, 50.0, 50.0),
            ({"name": "unknown_xyz", "type": "number", "unit": "xyz"}, 50.0, 50.0),
        ]
        for field, mock_val, expected in cases:
            with self.subTest(field=field["name"]):
                with patch.object(sensors_mod.random, "uniform", return_value=mock_val):
                    v = sensors_mod._simulate_field_value(field)
                self.assertEqual(v, expected)

    def test_simulate_unit_variant_celsius(self):
        with patch.object(sensors_mod.random, "uniform", return_value=25.0):
            v = sensors_mod._simulate_field_value({"name": "sensor_a", "type": "number", "unit": "celsius"})
        self.assertEqual(v, 25.0)

    def test_simulate_unit_exact_match_v_and_w(self):
        with patch.object(sensors_mod.random, "uniform", return_value=2.5):
            v = sensors_mod._simulate_field_value({"name": "x", "type": "number", "unit": "v"})
        self.assertEqual(v, 2.5)
        with patch.object(sensors_mod.random, "uniform", return_value=100.0):
            v = sensors_mod._simulate_field_value({"name": "x", "type": "number", "unit": "w"})
        self.assertEqual(v, 100.0)


if __name__ == "__main__":
    unittest.main()

