"""
Twilio notification plugin.

Called by api.py's _check_notifications whenever a rule is triggered.
Env vars needed (all optional — if unset, SMS is skipped silently):
    TWILIO_ACCOUNT_SID
    TWILIO_AUTH_TOKEN
    TWILIO_NUMBER       e.g. +15551234567  (your Twilio number)
    TWILIO_RECIPIENT    e.g. +15559876543  (destination number)
"""
import os

_TWILIO_READY = None  # None = unchecked, True/False after first call


def _twilio_env():
    return (
        os.getenv("TWILIO_ACCOUNT_SID", ""),
        os.getenv("TWILIO_AUTH_TOKEN", ""),
        os.getenv("TWILIO_NUMBER", ""),
        os.getenv("TWILIO_RECIPIENT", ""),
    )


def _is_configured():
    return all(_twilio_env())


def send_alert(rule: dict, field: str, value: float, greenhouse_name: str | None) -> None:
    """Send a Twilio SMS for a triggered notification rule.

    Args:
        rule: row from notification_rules (has 'message', 'operator', 'threshold', 'field_name')
        field: the field that triggered (same as rule['field_name'])
        value: the actual sensor value
        greenhouse_name: display name of the greenhouse (may be None)
    """
    if not _is_configured():
        return

    account_sid, auth_token, twilio_number, recipient_number = _twilio_env()

    location = greenhouse_name or "unknown greenhouse"
    operator_labels = {
        "gt": "above", "gte": "at or above",
        "lt": "below", "lte": "at or below",
        "eq": "equal to",
    }
    op_label = operator_labels.get(rule.get("operator", ""), rule.get("operator", ""))

    custom_message = (rule.get("message") or "").strip()
    if custom_message:
        body = f"{location} - {custom_message} ({field} = {value})"
    else:
        body = (
            f"{location} - Alert: {field} is {op_label} "
            f"{rule.get('threshold')} (current: {value})"
        )

    try:
        from twilio.rest import Client
        client = Client(account_sid, auth_token)
        msg = client.messages.create(body=body, from_=twilio_number, to=recipient_number)
        print(f"[notify] Twilio SMS sent SID={msg.sid} — {body}")
    except ImportError:
        print("[notify] twilio package not installed. pip install twilio")
    except Exception as exc:
        print(f"[notify] Twilio error: {exc}")
