import json
import unittest
from unittest.mock import patch

from src.config import Config
from src.db import execute, fetch_one, fetch_all, init_sqlite

from test._helpers import make_api_app, temp_sqlite_db


class TestApiIntegration(unittest.TestCase):
    def test_ingest_auth_and_latest_roundtrip(self):
        with temp_sqlite_db() as db_path:
            app = make_api_app(db_path)
            c = app.test_client()

            r = c.post("/api/ingest", json={"device_id": "d"})
            self.assertEqual(r.status_code, 401)

            r = c.post("/api/ingest", headers={"X-API-Key": Config.SENSOR_INGEST_TOKEN}, json={})
            self.assertEqual(r.status_code, 400)

            payload = {
                "device_id": "dev-1",
                "greenhouse_id": 1,
                "schema": "climate_v1",
                "recorded_at": "2026-03-13T12:00:00Z",
                "data": {"temperature_c": 26.4, "humidity_pct": 67.2},
            }
            r = c.post("/api/ingest", headers={"X-API-Key": Config.SENSOR_INGEST_TOKEN}, json=payload)
            self.assertEqual(r.status_code, 200)
            body = r.get_json()
            self.assertEqual(body["status"], "ok")
            self.assertEqual(body["schema"], "climate_v1")

            latest = c.get("/api/latest").get_json()["latest"]
            self.assertEqual(latest["device_id"], "dev-1")
            self.assertEqual(latest["schema_name"], "climate_v1")
            self.assertEqual(latest["data"]["temperature_c"], 26.4)

            schemas = c.get("/api/schemas", headers={"X-API-Key": Config.SENSOR_INGEST_TOKEN}).get_json()["schemas"]
            names = [s["name"] for s in schemas]
            self.assertIn("climate_v1", names)

    def test_me_and_greenhouse_requires_user_key(self):
        with temp_sqlite_db() as db_path:
            Config.SQLITE_PATH = db_path
            init_sqlite()

            user_token = "user-token"
            execute(
                "INSERT INTO users (username, password, email, api_key) VALUES (?, ?, ?, ?)",
                ("u1", "pw", "u1@example.com", user_token),
            )

            app = make_api_app(db_path)
            c = app.test_client()

            r = c.get("/api/me", headers={"X-API-Key": Config.SENSOR_INGEST_TOKEN})
            self.assertEqual(r.status_code, 200)
            self.assertIn("note", r.get_json())

            r = c.get("/api/me", headers={"X-API-Key": user_token})
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.get_json()["username"], "u1")

            r = c.post(
                "/api/greenhouses",
                headers={"X-API-Key": Config.SENSOR_INGEST_TOKEN},
                json={"greenhouse_name": "A", "location": "B"},
            )
            self.assertEqual(r.status_code, 403)

            r = c.post(
                "/api/greenhouses",
                headers={"X-API-Key": user_token},
                json={"greenhouse_name": "A", "location": "B"},
            )
            self.assertEqual(r.status_code, 201)
            self.assertEqual(r.get_json()["greenhouse_name"], "A")

    def test_notification_rule_triggers_alert_on_ingest(self):
        with temp_sqlite_db() as db_path:
            app = make_api_app(db_path)
            c = app.test_client()

            # Create greenhouse row for display (optional) and a rule that will trigger.
            execute(
                "INSERT INTO users (username, password, email, api_key) VALUES (?, ?, ?, ?)",
                ("u1", "pw", "u1@example.com", "k"),
            )
            execute(
                """
                INSERT INTO greenhouses
                    (location, greenhouse_name, sensors, length, width, description, primary_schema, userid)
                VALUES (?, ?, 'custom', '', '', '', '', 1)
                """,
                ("loc", "gh1"),
            )

            # Ensure schema exists.
            execute(
                "INSERT INTO sensor_schemas (name, description, fields_json, created_at) VALUES (?, ?, ?, ?)",
                ("climate_v1", "", json.dumps([{"name": "temperature_c", "type": "number", "unit": "°C"}]), "2026-03-13T00:00:00+00:00"),
            )
            schema_id = fetch_one("SELECT id FROM sensor_schemas WHERE name = ?", ("climate_v1",))["id"]
            execute(
                """
                INSERT INTO notification_rules
                    (greenhouse_id, schema_id, field_name, operator, threshold, message, enabled, created_at)
                VALUES (?, ?, ?, ?, ?, ?, 1, ?)
                """,
                (1, schema_id, "temperature_c", "gt", 20.0, "Too hot", "2026-03-13T00:00:00+00:00"),
            )

            payload = {
                "device_id": "dev-1",
                "greenhouse_id": 1,
                "schema": "climate_v1",
                "recorded_at": "2026-03-13T12:00:00Z",
                "data": {"temperature_c": 25.0},
            }
            with patch("src.routes.api.send_alert") as send_alert:
                r = c.post("/api/ingest", headers={"X-API-Key": Config.SENSOR_INGEST_TOKEN}, json=payload)
                self.assertEqual(r.status_code, 200)
                send_alert.assert_called()

            alerts = fetch_all("SELECT * FROM notification_alerts")
            self.assertEqual(len(alerts), 1)
            self.assertEqual(alerts[0]["field_name"], "temperature_c")


if __name__ == "__main__":
    unittest.main()

