import json
from datetime import datetime, timezone
from flask import Blueprint, jsonify, request
from ..lib.config import Config
from ..lib.db import fetch_all, fetch_one, execute
from ..lib.notify import send_alert

bp = Blueprint("api", __name__)


def _is_authorized(req):
    """Accept the global ingest token (simulator/admin) or any user's api_key."""
    token = req.headers.get("X-API-Key") or req.args.get("api_key")
    if not token:
        return False
    if token == Config.SENSOR_INGEST_TOKEN:
        return True
    user = fetch_one("SELECT userid FROM users WHERE api_key = ?", (token,))
    return user is not None


def _user_from_token(req):
    """Return the user dict for a per-user API key, or None for global token."""
    token = req.headers.get("X-API-Key") or req.args.get("api_key")
    if not token or token == Config.SENSOR_INGEST_TOKEN:
        return None
    return fetch_one("SELECT userid, username FROM users WHERE api_key = ?", (token,))


def _parse_timestamp(value):
    if value is None:
        return datetime.now(timezone.utc)
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc)
    try:
        if isinstance(value, str) and value.endswith("Z"):
            value = value[:-1] + "+00:00"
        return datetime.fromisoformat(value)
    except Exception:
        return datetime.now(timezone.utc)


def _normalize_schema_name(payload):
    return payload.get("schema") or payload.get("schema_name") or "default"


def _extract_data(payload):
    if isinstance(payload.get("data"), dict):
        return payload["data"]
    reserved = {
        "device_id", "greenhouse_id", "recorded_at", "timestamp",
        "source", "schema", "schema_name", "data", "label",
    }
    return {k: v for k, v in payload.items() if k not in reserved}


def _ensure_schema(schema_name, fields, greenhouse_id=None):
    """Find or create a sensor schema scoped to a greenhouse.

    If greenhouse_id is provided, look up by (greenhouse_id, name).
    If no greenhouse_id, fall back to a global template (greenhouse_id IS NULL).
    Auto-merges new fields into existing schema definitions.
    """
    if greenhouse_id is not None:
        schema = fetch_one(
            "SELECT id, fields_json FROM sensor_schemas WHERE greenhouse_id = ? AND name = ?",
            (greenhouse_id, schema_name),
        )
    else:
        schema = fetch_one(
            "SELECT id, fields_json FROM sensor_schemas WHERE greenhouse_id IS NULL AND name = ?",
            (schema_name,),
        )

    if schema:
        current_raw = json.loads(schema["fields_json"] or "[]")
        current_names = set(f["name"] if isinstance(f, dict) else f for f in current_raw)
        incoming = set(fields)
        if incoming - current_names:
            merged_names = sorted(current_names | incoming)
            merged = [{"name": n, "type": "number", "unit": ""} for n in merged_names]
            execute(
                "UPDATE sensor_schemas SET fields_json = ? WHERE id = ?",
                (json.dumps(merged), schema["id"]),
            )
        return schema["id"]

    # Create new schema
    created_at = datetime.now(timezone.utc).isoformat()
    fields_obj = [{"name": f, "type": "number", "unit": ""} for f in fields]
    execute(
        "INSERT INTO sensor_schemas (greenhouse_id, name, description, fields_json, created_at) VALUES (?, ?, ?, ?, ?)",
        (greenhouse_id, schema_name, "", json.dumps(fields_obj), created_at),
    )
    if greenhouse_id is not None:
        row = fetch_one(
            "SELECT id FROM sensor_schemas WHERE greenhouse_id = ? AND name = ?",
            (greenhouse_id, schema_name),
        )
    else:
        row = fetch_one(
            "SELECT id FROM sensor_schemas WHERE greenhouse_id IS NULL AND name = ?",
            (schema_name,),
        )
    return row["id"] if row else None


def _check_notifications(greenhouse_id, data, device_id, recorded_at):
    """Check enabled notification rules and insert alerts for any triggered conditions."""
    conditions = "enabled = 1 AND (greenhouse_id = ? OR greenhouse_id IS NULL)"
    rules = fetch_all(
        f"""SELECT nr.id, nr.field_name, nr.operator, nr.threshold, nr.message,
                   g.greenhouse_name
            FROM notification_rules nr
            LEFT JOIN greenhouses g ON g.id = nr.greenhouse_id
            WHERE {conditions}""",
        (greenhouse_id,),
    )
    op_map = {
        "gt": lambda v, t: v > t,
        "lt": lambda v, t: v < t,
        "gte": lambda v, t: v >= t,
        "lte": lambda v, t: v <= t,
        "eq": lambda v, t: v == t,
    }
    for rule in rules:
        field = rule["field_name"]
        if field not in data:
            continue
        try:
            value = float(data[field])
        except (TypeError, ValueError):
            continue
        check = op_map.get(rule["operator"])
        if check and check(value, rule["threshold"]):
            execute(
                """
                INSERT INTO notification_alerts
                    (rule_id, greenhouse_id, device_id, field_name, value, triggered_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (rule["id"], greenhouse_id, device_id, field, value, recorded_at.isoformat()),
            )
            send_alert(rule, field, value, rule.get("greenhouse_name"))


@bp.route("/api/me", methods=["GET"])
def api_me():
    """Returns info about the authenticated user for a given API key."""
    if not _is_authorized(request):
        return jsonify({"error": "Unauthorized"}), 401
    user = _user_from_token(request)
    if user:
        return jsonify({"userid": user["userid"], "username": user["username"]})
    return jsonify({"note": "Using global ingest token"})


@bp.route("/api/schema", methods=["GET"])
def schema():
    return jsonify(
        {
            "required": ["device_id"],
            "optional": ["greenhouse_id", "recorded_at", "source", "schema", "data"],
            "example": {
                "device_id": "gh-1-main",
                "greenhouse_id": 1,
                "recorded_at": "2026-03-13T18:45:00Z",
                "schema": "climate_v1",
                "data": {
                    "temperature_c": 26.4,
                    "humidity_pct": 67.2,
                    "light_lux": 740,
                    "co2_ppm": 520,
                    "soil_moisture": 0.42,
                },
            },
            "auth": "Send X-API-Key header with your SENSOR_INGEST_TOKEN.",
            "note": "Any extra top-level keys outside 'data' become data fields automatically.",
        }
    )


@bp.route("/api/greenhouses", methods=["GET", "POST"])
def list_greenhouses():
    if not _is_authorized(request):
        return jsonify({"error": "Unauthorized"}), 401
    user = _user_from_token(request)

    if request.method == "POST":
        if not user:
            return jsonify({"error": "A user API key is required to create a greenhouse"}), 403
        payload = request.get_json(silent=True) or {}
        name = (payload.get("greenhouse_name") or payload.get("name") or "").strip()
        location = (payload.get("location") or "").strip()
        if not name or not location:
            return jsonify({"error": "greenhouse_name and location are required"}), 400
        description = payload.get("description", "")
        from ..lib.db import execute_lastrowid
        new_id = execute_lastrowid(
            """
            INSERT INTO greenhouses
                (location, greenhouse_name, description, sensors, length, width, userid)
            VALUES (?, ?, ?, 'custom', '', '', ?)
            """,
            (location, name, description, user["userid"]),
        )
        return jsonify({"status": "ok", "id": new_id, "greenhouse_name": name, "location": location}), 201

    if user:
        rows = fetch_all(
            "SELECT id, greenhouse_name, location, description FROM greenhouses WHERE userid = ? ORDER BY id",
            (user["userid"],),
        )
    else:
        rows = fetch_all("SELECT id, greenhouse_name, location, description FROM greenhouses ORDER BY id")
    return jsonify({"greenhouses": rows})


@bp.route("/api/greenhouses/<int:greenhouse_id>", methods=["DELETE"])
def delete_greenhouse(greenhouse_id):
    if not _is_authorized(request):
        return jsonify({"error": "Unauthorized"}), 401
    user = _user_from_token(request)
    if not user:
        return jsonify({"error": "A user API key is required"}), 403
    row = fetch_one(
        "SELECT id FROM greenhouses WHERE id = ? AND userid = ?",
        (greenhouse_id, user["userid"]),
    )
    if not row:
        return jsonify({"error": "Not found"}), 404
    execute("DELETE FROM greenhouses WHERE id = ?", (greenhouse_id,))
    return jsonify({"status": "ok"})


@bp.route("/api/latest", methods=["GET"])
def latest():
    row = fetch_one(
        """
        SELECT r.id, r.greenhouse_id, r.device_id, r.source, r.data_json,
               r.recorded_at, s.name as schema_name
        FROM sensor_readings_custom r
        LEFT JOIN sensor_schemas s ON s.id = r.schema_id
        ORDER BY r.recorded_at DESC, r.id DESC
        LIMIT 1
        """
    )
    if row and row.get("data_json"):
        row["data"] = json.loads(row.pop("data_json") or "{}")
    return jsonify({"latest": row})


@bp.route("/api/schemas", methods=["GET", "POST"])
def schemas():
    if not _is_authorized(request):
        return jsonify({"error": "Unauthorized"}), 401
    user = _user_from_token(request)

    if request.method == "GET":
        greenhouse_id = request.args.get("greenhouse_id", type=int)
        if greenhouse_id:
            rows = fetch_all(
                "SELECT id, greenhouse_id, name, description, fields_json, created_at FROM sensor_schemas WHERE greenhouse_id = ? ORDER BY name",
                (greenhouse_id,),
            )
        elif user:
            rows = fetch_all(
                """
                SELECT ss.id, ss.greenhouse_id, ss.name, ss.description, ss.fields_json, ss.created_at
                FROM sensor_schemas ss
                JOIN greenhouses g ON g.id = ss.greenhouse_id
                WHERE g.userid = ?
                ORDER BY g.greenhouse_name, ss.name
                """,
                (user["userid"],),
            )
        else:
            rows = fetch_all(
                "SELECT id, greenhouse_id, name, description, fields_json, created_at FROM sensor_schemas ORDER BY id DESC"
            )
        for row in rows:
            raw = json.loads(row.pop("fields_json") or "[]")
            row["fields"] = [
                {**f, "type": f.get("type", "number"), "unit": f.get("unit", "")}
                if isinstance(f, dict) else {"name": f, "type": "number", "unit": ""}
                for f in raw
            ]
        return jsonify({"schemas": rows})

    # POST: create/update a schema for a specific greenhouse
    payload = request.get_json(silent=True) or {}
    name = payload.get("name")
    if not name:
        return jsonify({"error": "name is required"}), 400
    greenhouse_id = payload.get("greenhouse_id") or None
    fields = payload.get("fields") or []
    if isinstance(fields, str):
        fields = [f.strip() for f in fields.split(",") if f.strip()]
    fields_obj = []
    for f in fields:
        if isinstance(f, str):
            fields_obj.append({"name": f, "type": "number", "unit": ""})
        else:
            fields_obj.append(f)
    created_at = datetime.now(timezone.utc).isoformat()
    if greenhouse_id:
        existing = fetch_one("SELECT id, fields_json FROM sensor_schemas WHERE greenhouse_id = ? AND name = ?", (greenhouse_id, name))
    else:
        existing = fetch_one("SELECT id, fields_json FROM sensor_schemas WHERE greenhouse_id IS NULL AND name = ?", (name,))
    if existing:
        current_raw = json.loads(existing["fields_json"] or "[]")
        current_names = {f["name"] if isinstance(f, dict) else f for f in current_raw}
        merged = list(current_raw)
        merged_names = set(current_names)
        for f in fields_obj:
            if f["name"] not in merged_names:
                merged.append(f)
                merged_names.add(f["name"])
        execute(
            "UPDATE sensor_schemas SET description = ?, fields_json = ? WHERE id = ?",
            (payload.get("description") or "", json.dumps(merged), existing["id"]),
        )
        return jsonify({"status": "ok", "name": name, "fields": merged})
    execute(
        "INSERT INTO sensor_schemas (greenhouse_id, name, description, fields_json, created_at) VALUES (?, ?, ?, ?, ?)",
        (greenhouse_id, name, payload.get("description") or "", json.dumps(fields_obj), created_at),
    )
    return jsonify({"status": "ok", "name": name, "fields": fields_obj})


@bp.route("/api/ingest", methods=["POST"])
def ingest():
    if not _is_authorized(request):
        return jsonify({"error": "Unauthorized"}), 401

    payload = request.get_json(silent=True) or {}
    device_id = payload.get("device_id")
    if not device_id:
        return jsonify({"error": "device_id is required"}), 400

    recorded_at = _parse_timestamp(payload.get("recorded_at") or payload.get("timestamp"))
    greenhouse_id = payload.get("greenhouse_id")
    source = payload.get("source") or "sensor"
    schema_name = _normalize_schema_name(payload)
    data = _extract_data(payload)
    schema_id = _ensure_schema(schema_name, data.keys(), greenhouse_id)

    user = _user_from_token(request)
    userid = user["userid"] if user else None

    execute(
        """
        INSERT INTO sensor_readings_custom
            (greenhouse_id, device_id, schema_id, source, data_json, recorded_at, userid)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (greenhouse_id, device_id, schema_id, source, json.dumps(data), recorded_at.isoformat(), userid),
    )

    execute(
        """
        INSERT INTO sensor_devices (greenhouse_id, device_id, label, last_seen_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(device_id) DO UPDATE SET
            greenhouse_id=excluded.greenhouse_id,
            last_seen_at=excluded.last_seen_at
        """,
        (greenhouse_id, device_id, payload.get("label"), recorded_at.isoformat()),
    )

    # Check notification rules
    if greenhouse_id and data:
        _check_notifications(greenhouse_id, data, device_id, recorded_at)

    return jsonify({"status": "ok", "recorded_at": recorded_at.isoformat(), "schema": schema_name})


@bp.route("/api/chart-data", methods=["GET"])
def chart_data():
    schema_id = request.args.get("schema_id", type=int)
    field = request.args.get("field", "").strip()
    greenhouse_id = request.args.get("greenhouse_id", type=int)
    limit = request.args.get("limit", 200, type=int)

    if not field:
        return jsonify({"error": "field is required"}), 400

    conditions = []
    params = []
    if schema_id:
        conditions.append("r.schema_id = ?")
        params.append(schema_id)
    if greenhouse_id:
        conditions.append("r.greenhouse_id = ?")
        params.append(greenhouse_id)

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    rows = fetch_all(
        f"""
        SELECT r.data_json, r.recorded_at
        FROM sensor_readings_custom r
        {where}
        ORDER BY r.recorded_at ASC
        LIMIT ?
        """,
        tuple(params) + (limit,),
    )

    labels = []
    values = []
    for row in rows:
        data = json.loads(row["data_json"] or "{}")
        if field in data:
            ts = row["recorded_at"][:16].replace("T", " ")
            labels.append(ts)
            try:
                values.append(float(data[field]))
            except (TypeError, ValueError):
                values.append(None)

    return jsonify({"labels": labels, "values": values, "field": field})


@bp.route("/api/notification-rules", methods=["GET", "POST"])
def notification_rules():
    if not _is_authorized(request):
        return jsonify({"error": "Unauthorized"}), 401

    if request.method == "POST":
        payload = request.get_json(silent=True) or {}
        field_name = (payload.get("field_name") or "").strip()
        if not field_name:
            return jsonify({"error": "field_name is required"}), 400
        operator = payload.get("operator", "gt")
        if operator not in ("gt", "gte", "lt", "lte", "eq"):
            return jsonify({"error": "operator must be one of gt, gte, lt, lte, eq"}), 400
        try:
            threshold = float(payload.get("threshold", 0))
        except (TypeError, ValueError):
            return jsonify({"error": "threshold must be a number"}), 400
        greenhouse_id = payload.get("greenhouse_id") or None
        schema_id = payload.get("schema_id") or None
        message = payload.get("message", "")
        created_at = datetime.now(timezone.utc).isoformat()
        from ..lib.db import execute_lastrowid
        new_id = execute_lastrowid(
            """
            INSERT INTO notification_rules
                (greenhouse_id, schema_id, field_name, operator, threshold, message, enabled, created_at)
            VALUES (?, ?, ?, ?, ?, ?, 1, ?)
            """,
            (greenhouse_id, schema_id, field_name, operator, threshold, message, created_at),
        )
        return jsonify({"status": "ok", "id": new_id}), 201

    rows = fetch_all(
        """
        SELECT nr.id, nr.field_name, nr.operator, nr.threshold, nr.message, nr.enabled,
               g.greenhouse_name, s.name as schema_name
        FROM notification_rules nr
        LEFT JOIN greenhouses g ON g.id = nr.greenhouse_id
        LEFT JOIN sensor_schemas s ON s.id = nr.schema_id
        ORDER BY nr.id DESC
        """
    )
    return jsonify({"rules": rows})


@bp.route("/api/notification-rules/<int:rule_id>", methods=["DELETE"])
def delete_notification_rule_api(rule_id):
    if not _is_authorized(request):
        return jsonify({"error": "Unauthorized"}), 401
    row = fetch_one("SELECT id FROM notification_rules WHERE id = ?", (rule_id,))
    if not row:
        return jsonify({"error": "Not found"}), 404
    execute("DELETE FROM notification_rules WHERE id = ?", (rule_id,))
    return jsonify({"status": "ok"})


@bp.route("/api/alerts", methods=["GET"])
def alerts():
    limit = request.args.get("limit", 20, type=int)
    rows = fetch_all(
        """
        SELECT a.id, a.field_name, a.value, a.triggered_at, a.acknowledged,
               r.message, r.operator, r.threshold,
               g.greenhouse_name
        FROM notification_alerts a
        LEFT JOIN notification_rules r ON r.id = a.rule_id
        LEFT JOIN greenhouses g ON g.id = a.greenhouse_id
        ORDER BY a.triggered_at DESC
        LIMIT ?
        """,
        (limit,),
    )
    return jsonify({"alerts": rows})


@bp.route("/api/alerts/<int:alert_id>/ack", methods=["POST"])
def ack_alert(alert_id):
    execute("UPDATE notification_alerts SET acknowledged = 1 WHERE id = ?", (alert_id,))
    return jsonify({"status": "ok"})
