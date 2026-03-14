import json
from datetime import datetime, timezone
from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify
from ..lib.db import fetch_all, fetch_one, execute
from ..lib.auth_utils import login_required
from .api import _check_notifications

bp = Blueprint('sensors', __name__)


def _html_safe_json(obj) -> str:
    """JSON-serialize obj with HTML-unsafe characters escaped as \\uXXXX.
    This prevents </script> or <!-- in data from breaking embedded script tags.
    """
    s = json.dumps(obj)
    s = s.replace('&', r'\u0026').replace('<', r'\u003c').replace('>', r'\u003e')
    return s


def _parse_schema_fields(fields_json):
    fields = json.loads(fields_json or "[]")
    result = []
    for f in fields:
        if isinstance(f, str):
            result.append({"name": f, "type": "number", "unit": ""})
        else:
            result.append({
                "name": f.get("name", ""),
                "type": f.get("type", "number"),
                "unit": f.get("unit", ""),
            })
    return result


@bp.route('/sensor_status')
@login_required
def sensor_status():
    userid = session.get('userid')
    greenhouse_id = request.args.get('greenhouse_id', type=int)

    conditions = []
    params = []
    if greenhouse_id:
        conditions.append("r.greenhouse_id = ?")
        params.append(greenhouse_id)
    else:
        # Show readings in user's greenhouses OR sent by this user without a greenhouse_id
        conditions.append(
            "(r.greenhouse_id IN (SELECT id FROM greenhouses WHERE userid = ?) OR r.userid = ?)"
        )
        params.extend([userid, userid])

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    try:
        rows = fetch_all(
            f"""
            SELECT r.id, r.recorded_at, r.source, r.device_id, r.data_json,
                   g.greenhouse_name, s.name as schema_name
            FROM sensor_readings_custom r
            LEFT JOIN greenhouses g ON g.id = r.greenhouse_id
            LEFT JOIN sensor_schemas s ON s.id = r.schema_id
            {where}
            ORDER BY r.recorded_at DESC, r.id DESC
            LIMIT 100
            """,
            tuple(params),
        )
        for row in rows:
            row["data"] = json.loads(row.pop("data_json") or "{}")

        # Greenhouse filter selector
        user_greenhouses = fetch_all(
            "SELECT id, greenhouse_name FROM greenhouses WHERE userid = ? ORDER BY id",
            (userid,),
        ) if userid else []

        rows_json = _html_safe_json(rows)
        return render_template(
            'dashboard/sensor_status.html',
            rows_json=rows_json,
            msg='',
            greenhouses=user_greenhouses,
            selected_greenhouse_id=greenhouse_id,
        )
    except Exception:
        return render_template('dashboard/sensor_status.html', rows_json='[]', msg='Database error.')


@bp.route('/sensor_status/data')
@login_required
def sensor_status_data():
    userid = session.get('userid')
    greenhouse_id = request.args.get('greenhouse_id', type=int)

    conditions = []
    params = []
    if greenhouse_id:
        conditions.append("r.greenhouse_id = ?")
        params.append(greenhouse_id)
    else:
        conditions.append(
            "(r.greenhouse_id IN (SELECT id FROM greenhouses WHERE userid = ?) OR r.userid = ?)"
        )
        params.extend([userid, userid])

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    try:
        rows = fetch_all(
            f"""
            SELECT r.id, r.recorded_at, r.source, r.device_id, r.data_json,
                   g.greenhouse_name, s.name as schema_name
            FROM sensor_readings_custom r
            LEFT JOIN greenhouses g ON g.id = r.greenhouse_id
            LEFT JOIN sensor_schemas s ON s.id = r.schema_id
            {where}
            ORDER BY r.recorded_at DESC, r.id DESC
            LIMIT 100
            """,
            tuple(params),
        )
        for row in rows:
            row["data"] = json.loads(row.pop("data_json") or "{}")
        return jsonify(rows)
    except Exception:
        return jsonify([]), 500


@bp.route('/notifications')
@login_required
def notifications():
    userid = session.get('userid')

    # Scope rules to the current user's greenhouses
    rules = fetch_all(
        """
        SELECT nr.id, nr.field_name, nr.operator, nr.threshold, nr.message, nr.enabled,
               nr.created_at, nr.greenhouse_id, nr.schema_id,
               g.greenhouse_name, s.name as schema_name
        FROM notification_rules nr
        LEFT JOIN greenhouses g ON g.id = nr.greenhouse_id
        LEFT JOIN sensor_schemas s ON s.id = nr.schema_id
        WHERE nr.greenhouse_id IN (SELECT id FROM greenhouses WHERE userid = ?)
           OR nr.greenhouse_id IS NULL
        ORDER BY nr.id DESC
        """,
        (userid,),
    )

    greenhouses = fetch_all(
        "SELECT id, greenhouse_name FROM greenhouses WHERE userid = ? ORDER BY id", (userid,)
    ) if userid else []

    # Only schemas belonging to the user's greenhouses
    schemas_raw = fetch_all(
        """
        SELECT ss.id, ss.name, ss.fields_json
        FROM sensor_schemas ss
        JOIN greenhouses g ON g.id = ss.greenhouse_id
        WHERE g.userid = ?
        ORDER BY g.greenhouse_name, ss.name
        """,
        (userid,),
    ) if userid else []
    schemas = []
    for s in schemas_raw:
        schemas.append({
            "id": s["id"],
            "name": s["name"],
            "fields": _parse_schema_fields(s.get("fields_json", "[]")),
        })

    recent_alerts = fetch_all(
        """
        SELECT a.id, a.field_name, a.value, a.triggered_at, a.acknowledged,
               r.message, r.operator, r.threshold,
               g.greenhouse_name
        FROM notification_alerts a
        LEFT JOIN notification_rules r ON r.id = a.rule_id
        LEFT JOIN greenhouses g ON g.id = a.greenhouse_id
        WHERE a.greenhouse_id IN (SELECT id FROM greenhouses WHERE userid = ?)
           OR a.greenhouse_id IS NULL
        ORDER BY a.triggered_at DESC
        LIMIT 30
        """,
        (userid,),
    )

    return render_template(
        'dashboard/notifications.html',
        rules=rules,
        greenhouses=greenhouses,
        schemas=schemas,
        recent_alerts=recent_alerts,
    )


@bp.route('/notifications/create', methods=['POST'])
@login_required
def create_notification_rule():
    greenhouse_id = request.form.get('greenhouse_id') or None
    schema_id = request.form.get('schema_id') or None
    field_name = request.form.get('field_name', '').strip()
    operator = request.form.get('operator', 'gt')
    threshold_raw = request.form.get('threshold', '0')
    message = request.form.get('message', '').strip()

    if not field_name:
        flash('Field name is required.', 'error')
        return redirect(request.referrer or url_for('sensors.notifications'))

    try:
        threshold = float(threshold_raw)
    except (TypeError, ValueError):
        flash('Threshold must be a number.', 'error')
        return redirect(request.referrer or url_for('sensors.notifications'))

    created_at = datetime.now(timezone.utc).isoformat()
    execute(
        """
        INSERT INTO notification_rules
            (greenhouse_id, schema_id, field_name, operator, threshold, message, enabled, created_at)
        VALUES (?, ?, ?, ?, ?, ?, 1, ?)
        """,
        (greenhouse_id, schema_id, field_name, operator, threshold, message, created_at),
    )
    flash('Alert rule created.', 'success')
    # Return to the referring page (greenhouse detail or notifications page)
    return redirect(request.referrer or url_for('sensors.notifications'))


@bp.route('/notifications/<int:rule_id>/edit', methods=['POST'])
@login_required
def edit_notification_rule(rule_id):
    rule = fetch_one("SELECT id FROM notification_rules WHERE id = ?", (rule_id,))
    if not rule:
        flash('Rule not found.', 'error')
        return redirect(url_for('sensors.notifications'))

    greenhouse_id = request.form.get('greenhouse_id') or None
    schema_id = request.form.get('schema_id') or None
    field_name = request.form.get('field_name', '').strip()
    operator = request.form.get('operator', 'gt')
    threshold_raw = request.form.get('threshold', '0')
    message = request.form.get('message', '').strip()

    if not field_name:
        flash('Field name is required.', 'error')
        return redirect(url_for('sensors.notifications'))

    try:
        threshold = float(threshold_raw)
    except (TypeError, ValueError):
        flash('Threshold must be a number.', 'error')
        return redirect(url_for('sensors.notifications'))

    execute(
        """
        UPDATE notification_rules
        SET greenhouse_id = ?, schema_id = ?, field_name = ?, operator = ?, threshold = ?, message = ?
        WHERE id = ?
        """,
        (greenhouse_id, schema_id, field_name, operator, threshold, message, rule_id),
    )
    flash('Alert rule updated.', 'success')
    return redirect(url_for('sensors.notifications'))


@bp.route('/notifications/<int:rule_id>/toggle', methods=['POST'])
@login_required
def toggle_notification_rule(rule_id):
    rule = fetch_one("SELECT id, enabled FROM notification_rules WHERE id = ?", (rule_id,))
    if rule:
        execute(
            "UPDATE notification_rules SET enabled = ? WHERE id = ?",
            (0 if rule['enabled'] else 1, rule_id),
        )
    return redirect(request.referrer or url_for('sensors.notifications'))


@bp.route('/notifications/<int:rule_id>/delete', methods=['POST'])
@login_required
def delete_notification_rule(rule_id):
    execute("DELETE FROM notification_rules WHERE id = ?", (rule_id,))
    flash('Rule deleted.', 'success')
    return redirect(request.referrer or url_for('sensors.notifications'))


@bp.route('/notifications/alerts/<int:alert_id>/ack', methods=['POST'])
@login_required
def ack_alert(alert_id):
    execute("UPDATE notification_alerts SET acknowledged = 1 WHERE id = ?", (alert_id,))
    return redirect(request.referrer or url_for('sensors.notifications'))
