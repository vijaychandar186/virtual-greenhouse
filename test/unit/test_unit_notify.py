import io
import os
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch, MagicMock

from src.notify import send_alert, _is_configured, _twilio_env


class TestNotifyUnit(unittest.TestCase):
    def test_twilio_env_reads_from_environment(self):
        with patch.dict(os.environ, {
            "TWILIO_ACCOUNT_SID": "sid",
            "TWILIO_AUTH_TOKEN": "tok",
            "TWILIO_NUMBER": "+1111",
            "TWILIO_RECIPIENT": "+2222",
        }):
            self.assertEqual(_twilio_env(), ("sid", "tok", "+1111", "+2222"))

    def test_is_configured_false_when_any_var_missing(self):
        with patch.dict(os.environ, {
            "TWILIO_ACCOUNT_SID": "sid",
            "TWILIO_AUTH_TOKEN": "",
            "TWILIO_NUMBER": "+1111",
            "TWILIO_RECIPIENT": "+2222",
        }, clear=False):
            self.assertFalse(_is_configured())

    def test_is_configured_true_when_all_set(self):
        with patch.dict(os.environ, {
            "TWILIO_ACCOUNT_SID": "sid",
            "TWILIO_AUTH_TOKEN": "tok",
            "TWILIO_NUMBER": "+1111",
            "TWILIO_RECIPIENT": "+2222",
        }):
            self.assertTrue(_is_configured())

    def test_send_alert_skips_when_not_configured(self):
        with patch.dict(os.environ, {
            "TWILIO_ACCOUNT_SID": "",
            "TWILIO_AUTH_TOKEN": "",
            "TWILIO_NUMBER": "",
            "TWILIO_RECIPIENT": "",
        }):
            send_alert({"operator": "gt", "threshold": 30}, "temp", 35.0, "Greenhouse A")

    def test_send_alert_formats_custom_message(self):
        rule = {"operator": "gt", "threshold": 30, "message": "Temp high!"}
        with patch.dict(os.environ, {
            "TWILIO_ACCOUNT_SID": "sid",
            "TWILIO_AUTH_TOKEN": "tok",
            "TWILIO_NUMBER": "+1111",
            "TWILIO_RECIPIENT": "+2222",
        }):
            mock_client = MagicMock()
            mock_client.messages.create.return_value = MagicMock(sid="SM123")
            with patch("twilio.rest.Client", return_value=mock_client):
                send_alert(rule, "temp", 35.0, "Greenhouse A")
            call_kwargs = mock_client.messages.create.call_args
            body = call_kwargs.kwargs["body"]
            self.assertIn("Temp high!", body)
            self.assertIn("temp = 35.0", body)
            self.assertIn("Greenhouse A", body)
            self.assertEqual(call_kwargs.kwargs["from_"], "+1111")
            self.assertEqual(call_kwargs.kwargs["to"], "+2222")

    def test_send_alert_formats_default_message(self):
        rule = {"operator": "lt", "threshold": 10.0, "message": ""}
        with patch.dict(os.environ, {
            "TWILIO_ACCOUNT_SID": "sid",
            "TWILIO_AUTH_TOKEN": "tok",
            "TWILIO_NUMBER": "+1111",
            "TWILIO_RECIPIENT": "+2222",
        }):
            mock_client = MagicMock()
            mock_client.messages.create.return_value = MagicMock(sid="SM456")
            with patch("twilio.rest.Client", return_value=mock_client):
                send_alert(rule, "temp", 5.0, None)
            body = mock_client.messages.create.call_args.kwargs["body"]
            self.assertIn("unknown greenhouse", body)
            self.assertIn("below", body)
            self.assertIn("10.0", body)

    def test_send_alert_handles_twilio_exception(self):
        rule = {"operator": "gt", "threshold": 30}
        with patch.dict(os.environ, {
            "TWILIO_ACCOUNT_SID": "sid",
            "TWILIO_AUTH_TOKEN": "tok",
            "TWILIO_NUMBER": "+1111",
            "TWILIO_RECIPIENT": "+2222",
        }):
            with patch("twilio.rest.Client", side_effect=Exception("API error")):
                buf = io.StringIO()
                with redirect_stdout(buf):
                    send_alert(rule, "temp", 35.0, "GH")
                self.assertIn("Twilio error", buf.getvalue())

    def test_send_alert_operator_labels(self):
        labels = {
            "gt": "above",
            "gte": "at or above",
            "lt": "below",
            "lte": "at or below",
            "eq": "equal to",
        }
        for op, expected_label in labels.items():
            with self.subTest(op=op):
                rule = {"operator": op, "threshold": 20.0, "message": ""}
                with patch.dict(os.environ, {
                    "TWILIO_ACCOUNT_SID": "sid",
                    "TWILIO_AUTH_TOKEN": "tok",
                    "TWILIO_NUMBER": "+1111",
                    "TWILIO_RECIPIENT": "+2222",
                }):
                    mock_client = MagicMock()
                    mock_client.messages.create.return_value = MagicMock(sid="SM")
                    with patch("twilio.rest.Client", return_value=mock_client):
                        send_alert(rule, "f", 25.0, "GH")
                    body = mock_client.messages.create.call_args.kwargs["body"]
                    self.assertIn(expected_label, body)


if __name__ == "__main__":
    unittest.main()
