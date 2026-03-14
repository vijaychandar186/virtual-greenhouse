import json
import unittest
from unittest.mock import patch

from src.config import Config
from src.db import execute, fetch_one, fetch_all, init_sqlite

from test._helpers import make_api_app, temp_sqlite_db


class TestApiEndpointsFull(unittest.TestCase):
    # ---- /api/schema (doc) ----

    def test_schema_doc_endpoint(self):
        with temp_sqlite_db() as db_path:
            app = make_api_app(db_path)
            c = app.test_client()
            r = c.get("/api/schema")
            self.assertEqual(r.status_code, 200)
            body = r.get_json()
            self.assertIn("required", body)
            self.assertIn("device_id", body["required"])

    # ---- /api/chart-data ----

    def test_chart_data_requires_field(self):
        with temp_sqlite_db() as db_path:
            app = make_api_app(db_path)
            c = app.test_client()
            r = c.get("/api/chart-data")
            self.assertEqual(r.status_code, 400)

    def test_chart_data_returns_values(self):
        with temp_sqlite_db() as db_path:
            app = make_api_app(db_path)
            c = app.test_client()
            h = {"X-API-Key": Config.SENSOR_INGEST_TOKEN}
            c.post("/api/ingest", headers=h, json={
                "device_id": "d1", "greenhouse_id": 1,
                "schema": "s1", "data": {"temp": 25.0},
            })
            r = c.get("/api/chart-data?field=temp")
            self.assertEqual(r.status_code, 200)
            body = r.get_json()
            self.assertEqual(body["field"], "temp")
            self.assertEqual(len(body["values"]), 1)
            self.assertEqual(body["values"][0], 25.0)

    def test_chart_data_with_filters(self):
        with temp_sqlite_db() as db_path:
            app = make_api_app(db_path)
            c = app.test_client()
            h = {"X-API-Key": Config.SENSOR_INGEST_TOKEN}
            c.post("/api/ingest", headers=h, json={
                "device_id": "d1", "greenhouse_id": 1,
                "schema": "s1", "data": {"temp": 25.0},
            })
            schema = fetch_one("SELECT id FROM sensor_schemas WHERE name = ?", ("s1",))
            r = c.get(f"/api/chart-data?field=temp&schema_id={schema['id']}&greenhouse_id=1")
            self.assertEqual(r.status_code, 200)
            self.assertEqual(len(r.get_json()["values"]), 1)

            r = c.get("/api/chart-data?field=temp&greenhouse_id=999")
            self.assertEqual(r.status_code, 200)
            self.assertEqual(len(r.get_json()["values"]), 0)

    def test_chart_data_non_numeric_value(self):
        with temp_sqlite_db() as db_path:
            app = make_api_app(db_path)
            c = app.test_client()
            h = {"X-API-Key": Config.SENSOR_INGEST_TOKEN}
            c.post("/api/ingest", headers=h, json={
                "device_id": "d1", "schema": "s1",
                "data": {"label": "hello", "temp": 20.0},
            })
            r = c.get("/api/chart-data?field=label")
            body = r.get_json()
            self.assertEqual(len(body["values"]), 1)
            self.assertIsNone(body["values"][0])

    # ---- /api/schemas POST ----

    def test_schemas_post_creates_new(self):
        with temp_sqlite_db() as db_path:
            app = make_api_app(db_path)
            c = app.test_client()
            h = {"X-API-Key": Config.SENSOR_INGEST_TOKEN}
            r = c.post("/api/schemas", headers=h, json={
                "name": "new_schema",
                "description": "test",
                "fields": [{"name": "f1", "type": "number", "unit": "°C"}],
            })
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.get_json()["name"], "new_schema")

    def test_schemas_post_missing_name(self):
        with temp_sqlite_db() as db_path:
            app = make_api_app(db_path)
            c = app.test_client()
            h = {"X-API-Key": Config.SENSOR_INGEST_TOKEN}
            r = c.post("/api/schemas", headers=h, json={})
            self.assertEqual(r.status_code, 400)

    def test_schemas_post_updates_existing(self):
        with temp_sqlite_db() as db_path:
            app = make_api_app(db_path)
            c = app.test_client()
            h = {"X-API-Key": Config.SENSOR_INGEST_TOKEN}
            c.post("/api/schemas", headers=h, json={
                "name": "s1",
                "fields": [{"name": "a", "type": "number", "unit": ""}],
            })
            r = c.post("/api/schemas", headers=h, json={
                "name": "s1",
                "fields": [{"name": "b", "type": "number", "unit": ""}],
            })
            self.assertEqual(r.status_code, 200)
            field_names = {f["name"] for f in r.get_json()["fields"]}
            self.assertEqual(field_names, {"a", "b"})

    def test_schemas_post_string_fields(self):
        with temp_sqlite_db() as db_path:
            app = make_api_app(db_path)
            c = app.test_client()
            h = {"X-API-Key": Config.SENSOR_INGEST_TOKEN}
            r = c.post("/api/schemas", headers=h, json={
                "name": "s2",
                "fields": "alpha, beta, gamma",
            })
            self.assertEqual(r.status_code, 200)
            names = {f["name"] for f in r.get_json()["fields"]}
            self.assertEqual(names, {"alpha", "beta", "gamma"})

    def test_schemas_post_list_of_strings(self):
        with temp_sqlite_db() as db_path:
            app = make_api_app(db_path)
            c = app.test_client()
            h = {"X-API-Key": Config.SENSOR_INGEST_TOKEN}
            r = c.post("/api/schemas", headers=h, json={
                "name": "s3",
                "fields": ["x", "y"],
            })
            self.assertEqual(r.status_code, 200)
            names = {f["name"] for f in r.get_json()["fields"]}
            self.assertEqual(names, {"x", "y"})

    # ---- /api/notification-rules ----

    def test_notification_rules_crud(self):
        with temp_sqlite_db() as db_path:
            app = make_api_app(db_path)
            c = app.test_client()
            h = {"X-API-Key": Config.SENSOR_INGEST_TOKEN}

            r = c.post("/api/notification-rules", headers=h, json={
                "field_name": "temp",
                "operator": "gt",
                "threshold": 30,
                "message": "Too hot",
            })
            self.assertEqual(r.status_code, 201)
            rule_id = r.get_json()["id"]

            r = c.get("/api/notification-rules", headers=h)
            self.assertEqual(r.status_code, 200)
            self.assertEqual(len(r.get_json()["rules"]), 1)

            r = c.delete(f"/api/notification-rules/{rule_id}", headers=h)
            self.assertEqual(r.status_code, 200)

            r = c.get("/api/notification-rules", headers=h)
            self.assertEqual(len(r.get_json()["rules"]), 0)

    def test_notification_rules_missing_field_name(self):
        with temp_sqlite_db() as db_path:
            app = make_api_app(db_path)
            c = app.test_client()
            h = {"X-API-Key": Config.SENSOR_INGEST_TOKEN}
            r = c.post("/api/notification-rules", headers=h, json={"operator": "gt"})
            self.assertEqual(r.status_code, 400)

    def test_notification_rules_invalid_operator(self):
        with temp_sqlite_db() as db_path:
            app = make_api_app(db_path)
            c = app.test_client()
            h = {"X-API-Key": Config.SENSOR_INGEST_TOKEN}
            r = c.post("/api/notification-rules", headers=h, json={
                "field_name": "temp", "operator": "invalid",
            })
            self.assertEqual(r.status_code, 400)

    def test_notification_rules_invalid_threshold(self):
        with temp_sqlite_db() as db_path:
            app = make_api_app(db_path)
            c = app.test_client()
            h = {"X-API-Key": Config.SENSOR_INGEST_TOKEN}
            r = c.post("/api/notification-rules", headers=h, json={
                "field_name": "temp", "operator": "gt", "threshold": "abc",
            })
            self.assertEqual(r.status_code, 400)

    def test_notification_rule_delete_not_found(self):
        with temp_sqlite_db() as db_path:
            app = make_api_app(db_path)
            c = app.test_client()
            h = {"X-API-Key": Config.SENSOR_INGEST_TOKEN}
            r = c.delete("/api/notification-rules/999", headers=h)
            self.assertEqual(r.status_code, 404)

    # ---- /api/alerts ----

    def test_alerts_list_and_ack(self):
        with temp_sqlite_db() as db_path:
            app = make_api_app(db_path)
            c = app.test_client()

            execute(
                "INSERT INTO notification_alerts (rule_id, greenhouse_id, device_id, field_name, value, triggered_at) VALUES (?, ?, ?, ?, ?, ?)",
                (1, 1, "d1", "temp", 35.0, "2026-03-13T12:00:00+00:00"),
            )

            r = c.get("/api/alerts")
            self.assertEqual(r.status_code, 200)
            alerts = r.get_json()["alerts"]
            self.assertEqual(len(alerts), 1)
            self.assertEqual(alerts[0]["acknowledged"], 0)

            r = c.post(f"/api/alerts/{alerts[0]['id']}/ack")
            self.assertEqual(r.status_code, 200)

            r = c.get("/api/alerts")
            self.assertEqual(r.get_json()["alerts"][0]["acknowledged"], 1)

    # ---- /api/greenhouses DELETE ----

    def test_greenhouses_delete(self):
        with temp_sqlite_db() as db_path:
            Config.SQLITE_PATH = db_path
            init_sqlite()

            execute(
                "INSERT INTO users (username, password, email, api_key) VALUES (?, ?, ?, ?)",
                ("u1", "pw", "u1@example.com", "user-key"),
            )
            execute(
                """INSERT INTO greenhouses
                    (location, greenhouse_name, sensors, length, width, description, primary_schema, userid)
                VALUES (?, ?, 'custom', '', '', '', '', 1)""",
                ("loc", "gh1"),
            )

            app = make_api_app(db_path)
            c = app.test_client()

            r = c.delete("/api/greenhouses/1", headers={"X-API-Key": Config.SENSOR_INGEST_TOKEN})
            self.assertEqual(r.status_code, 403)

            r = c.delete("/api/greenhouses/1", headers={"X-API-Key": "user-key"})
            self.assertEqual(r.status_code, 200)

            r = c.delete("/api/greenhouses/999", headers={"X-API-Key": "user-key"})
            self.assertEqual(r.status_code, 404)

    # ---- notification operators ----

    def test_check_notifications_all_operators(self):
        with temp_sqlite_db() as db_path:
            app = make_api_app(db_path)
            c = app.test_client()
            h = {"X-API-Key": Config.SENSOR_INGEST_TOKEN}

            execute(
                "INSERT INTO users (username, password, email, api_key) VALUES (?, ?, ?, ?)",
                ("u1", "pw", "u1@example.com", "k"),
            )
            execute(
                """INSERT INTO greenhouses
                    (location, greenhouse_name, sensors, length, width, description, primary_schema, userid)
                VALUES (?, ?, 'custom', '', '', '', '', 1)""",
                ("loc", "gh1"),
            )
            execute(
                "INSERT INTO sensor_schemas (name, description, fields_json, created_at) VALUES (?, ?, ?, ?)",
                ("s1", "", json.dumps([{"name": "val", "type": "number", "unit": ""}]), "2026-03-13T00:00:00+00:00"),
            )
            schema_id = fetch_one("SELECT id FROM sensor_schemas WHERE name = ?", ("s1",))["id"]

            for op, threshold in [("gt", 20.0), ("lt", 30.0), ("gte", 25.0), ("lte", 25.0), ("eq", 25.0)]:
                execute(
                    """INSERT INTO notification_rules
                        (greenhouse_id, schema_id, field_name, operator, threshold, message, enabled, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, 1, ?)""",
                    (1, schema_id, "val", op, threshold, f"{op} alert", "2026-03-13T00:00:00+00:00"),
                )

            with patch("src.routes.api.send_alert"):
                r = c.post("/api/ingest", headers=h, json={
                    "device_id": "d1", "greenhouse_id": 1,
                    "schema": "s1", "data": {"val": 25.0},
                })
                self.assertEqual(r.status_code, 200)

            alerts = fetch_all("SELECT * FROM notification_alerts ORDER BY id")
            self.assertEqual(len(alerts), 5)

    def test_notification_does_not_trigger_when_condition_unmet(self):
        with temp_sqlite_db() as db_path:
            app = make_api_app(db_path)
            c = app.test_client()
            h = {"X-API-Key": Config.SENSOR_INGEST_TOKEN}

            execute(
                "INSERT INTO users (username, password, email, api_key) VALUES (?, ?, ?, ?)",
                ("u1", "pw", "u1@example.com", "k"),
            )
            execute(
                """INSERT INTO greenhouses
                    (location, greenhouse_name, sensors, length, width, description, primary_schema, userid)
                VALUES (?, ?, 'custom', '', '', '', '', 1)""",
                ("loc", "gh1"),
            )
            execute(
                "INSERT INTO sensor_schemas (name, description, fields_json, created_at) VALUES (?, ?, ?, ?)",
                ("s1", "", json.dumps([{"name": "val", "type": "number", "unit": ""}]), "2026-03-13T00:00:00+00:00"),
            )
            schema_id = fetch_one("SELECT id FROM sensor_schemas WHERE name = ?", ("s1",))["id"]
            execute(
                """INSERT INTO notification_rules
                    (greenhouse_id, schema_id, field_name, operator, threshold, message, enabled, created_at)
                VALUES (?, ?, ?, ?, ?, ?, 1, ?)""",
                (1, schema_id, "val", "gt", 50.0, "Too high", "2026-03-13T00:00:00+00:00"),
            )

            with patch("src.routes.api.send_alert") as mock_send:
                c.post("/api/ingest", headers=h, json={
                    "device_id": "d1", "greenhouse_id": 1,
                    "schema": "s1", "data": {"val": 10.0},
                })
                mock_send.assert_not_called()

            alerts = fetch_all("SELECT * FROM notification_alerts")
            self.assertEqual(len(alerts), 0)

    def test_ingest_without_greenhouse_skips_notifications(self):
        with temp_sqlite_db() as db_path:
            app = make_api_app(db_path)
            c = app.test_client()
            h = {"X-API-Key": Config.SENSOR_INGEST_TOKEN}

            r = c.post("/api/ingest", headers=h, json={
                "device_id": "d1", "schema": "s1", "data": {"temp": 25.0},
            })
            self.assertEqual(r.status_code, 200)

            alerts = fetch_all("SELECT * FROM notification_alerts")
            self.assertEqual(len(alerts), 0)

    # ---- authorization ----

    def test_unauthorized_access_to_protected_endpoints(self):
        with temp_sqlite_db() as db_path:
            app = make_api_app(db_path)
            c = app.test_client()

            for endpoint in ["/api/schemas", "/api/notification-rules", "/api/greenhouses", "/api/me"]:
                with self.subTest(endpoint=endpoint):
                    r = c.get(endpoint)
                    self.assertEqual(r.status_code, 401)

    def test_greenhouses_get_list(self):
        with temp_sqlite_db() as db_path:
            Config.SQLITE_PATH = db_path
            init_sqlite()

            execute(
                "INSERT INTO users (username, password, email, api_key) VALUES (?, ?, ?, ?)",
                ("u1", "pw", "u1@example.com", "user-key"),
            )
            execute(
                """INSERT INTO greenhouses
                    (location, greenhouse_name, sensors, length, width, description, primary_schema, userid)
                VALUES (?, ?, 'custom', '', '', '', '', 1)""",
                ("loc", "gh1"),
            )

            app = make_api_app(db_path)
            c = app.test_client()

            r = c.get("/api/greenhouses", headers={"X-API-Key": "user-key"})
            self.assertEqual(r.status_code, 200)
            greenhouses = r.get_json()["greenhouses"]
            self.assertEqual(len(greenhouses), 1)
            self.assertEqual(greenhouses[0]["greenhouse_name"], "gh1")

            r = c.get("/api/greenhouses", headers={"X-API-Key": Config.SENSOR_INGEST_TOKEN})
            self.assertEqual(r.status_code, 200)
            self.assertEqual(len(r.get_json()["greenhouses"]), 1)


if __name__ == "__main__":
    unittest.main()
