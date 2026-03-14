import unittest
import io
from contextlib import redirect_stdout, redirect_stderr
from types import SimpleNamespace
from urllib.parse import urlparse
from unittest.mock import patch

import scripts.sensor_simulator as sim
from src.config import Config

from test._helpers import make_api_app, temp_sqlite_db


class TestE2ESimulatorToApi(unittest.TestCase):
    def test_cli_simulator_sends_to_ingest_endpoint(self):
        with temp_sqlite_db() as db_path:
            app = make_api_app(db_path)
            client = app.test_client()

            def fake_post(url, json=None, headers=None, timeout=None):
                path = urlparse(url).path
                r = client.post(path, json=json, headers=headers)
                return SimpleNamespace(status_code=r.status_code, text=r.get_data(as_text=True))

            with (
                patch.object(sim.requests, "post", side_effect=fake_post),
                patch.object(sim.time, "sleep", return_value=None),
                patch.object(
                    sim.sys,
                    "argv",
                    [
                        "sensor_simulator.py",
                        "--url",
                        "http://localhost:5000/api/ingest",
                        "--api-key",
                        Config.SENSOR_INGEST_TOKEN,
                        "--device-id",
                        "sim-1",
                        "--greenhouse-id",
                        "1",
                        "--interval",
                        "0",
                        "--count",
                        "1",
                        "--schema",
                        "climate_v1",
                    ],
                ),
            ):
                buf = io.StringIO()
                with redirect_stdout(buf), redirect_stderr(buf):
                    sim.main()

            latest = client.get("/api/latest").get_json()["latest"]
            self.assertEqual(latest["device_id"], "sim-1")
            self.assertEqual(latest["schema_name"], "climate_v1")


if __name__ == "__main__":
    unittest.main()
