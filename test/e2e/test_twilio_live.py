"""
Live Twilio SMS integration tests.

These tests send REAL SMS messages via Twilio and require valid credentials
set in the .env file. They verify the full notification pipeline end-to-end.

NOTE: The Twilio from-number must be verified (toll-free verification or
a standard local number) for SMS to actually be delivered to the recipient.
Error 30032 means the toll-free number is not yet carrier-verified.
"""
import io
import json
import os
import time
import unittest
from contextlib import redirect_stdout

from src.config import Config
from src.db import execute, fetch_one, fetch_all

from src.notify import send_alert, _is_configured
from test._helpers import make_api_app, temp_sqlite_db


def _skip_if_not_configured():
    if not _is_configured():
        raise unittest.SkipTest("Twilio env vars not set in .env")


class TestTwilioLive(unittest.TestCase):
    def setUp(self):
        _skip_if_not_configured()

    def test_send_real_sms(self):
        """Directly call send_alert and verify Twilio accepts the message."""
        rule = {
            "operator": "gt",
            "threshold": 30.0,
            "message": "Test alert from VG test suite",
        }
        buf = io.StringIO()
        with redirect_stdout(buf):
            send_alert(rule, "temperature_c", 35.5, "Test Greenhouse")
        output = buf.getvalue()
        self.assertIn("Twilio SMS sent", output)
        self.assertIn("SID=SM", output)

    def test_send_real_sms_delivery_status(self):
        """Send an SMS and poll Twilio to confirm delivery status."""
        from twilio.rest import Client

        sid = os.environ["TWILIO_ACCOUNT_SID"]
        token = os.environ["TWILIO_AUTH_TOKEN"]
        from_number = os.environ["TWILIO_NUMBER"]
        to_number = os.environ["TWILIO_RECIPIENT"]

        client = Client(sid, token)
        msg = client.messages.create(
            body="VG test: delivery check",
            from_=from_number,
            to=to_number,
        )
        self.assertTrue(msg.sid.startswith("SM"))

        time.sleep(5)
        updated = client.messages(msg.sid).fetch()
        print(f"[twilio-live] SID={msg.sid} status={updated.status} error_code={updated.error_code}")

        if updated.status == "undelivered" and updated.error_code == 30032:
            self.skipTest(
                "Toll-free number not verified (error 30032). "
                "Complete toll-free verification in Twilio Console, "
                "or switch to a local number."
            )
        self.assertIn(updated.status, ("queued", "sent", "delivered"))

    def test_full_pipeline_ingest_triggers_real_sms(self):
        """End-to-end: ingest sensor data -> trigger notification rule -> send SMS via Twilio."""
        with temp_sqlite_db() as db_path:
            app = make_api_app(db_path)
            c = app.test_client()

            execute(
                "INSERT INTO users (username, password, email, api_key) VALUES (?, ?, ?, ?)",
                ("u1", "pw", "u1@example.com", "k"),
            )
            execute(
                """INSERT INTO greenhouses
                    (location, greenhouse_name, sensors, length, width, description, primary_schema, userid)
                VALUES (?, ?, 'custom', '', '', '', '', 1)""",
                ("Test Location", "Live Test Greenhouse"),
            )
            execute(
                "INSERT INTO sensor_schemas (name, description, fields_json, created_at) VALUES (?, ?, ?, ?)",
                ("climate_v1", "", json.dumps([{"name": "temperature_c", "type": "number", "unit": "°C"}]), "2026-03-13T00:00:00+00:00"),
            )
            schema_id = fetch_one("SELECT id FROM sensor_schemas WHERE name = ?", ("climate_v1",))["id"]
            execute(
                """INSERT INTO notification_rules
                    (greenhouse_id, schema_id, field_name, operator, threshold, message, enabled, created_at)
                VALUES (?, ?, ?, ?, ?, ?, 1, ?)""",
                (1, schema_id, "temperature_c", "gt", 30.0, "Live test: temperature too high!", "2026-03-13T00:00:00+00:00"),
            )

            buf = io.StringIO()
            with redirect_stdout(buf):
                r = c.post(
                    "/api/ingest",
                    headers={"X-API-Key": Config.SENSOR_INGEST_TOKEN},
                    json={
                        "device_id": "live-test-1",
                        "greenhouse_id": 1,
                        "schema": "climate_v1",
                        "data": {"temperature_c": 38.5},
                    },
                )

            self.assertEqual(r.status_code, 200)
            self.assertIn("Twilio SMS sent", buf.getvalue())

            alerts = fetch_all("SELECT * FROM notification_alerts")
            self.assertEqual(len(alerts), 1)
            self.assertEqual(alerts[0]["field_name"], "temperature_c")
            self.assertEqual(alerts[0]["value"], 38.5)


if __name__ == "__main__":
    unittest.main()
