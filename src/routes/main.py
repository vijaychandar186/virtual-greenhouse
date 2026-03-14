import json
from datetime import datetime, timezone
from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from ..lib.db import fetch_one, fetch_all, execute
from ..lib.auth_utils import login_required

bp = Blueprint('main', __name__)


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


@bp.route("/", methods=["GET"])
def home():
    return render_template("about.html")  # stays at templates root


@bp.route("/dashboard", methods=["GET"])
@login_required
def dashboard():
    userid = session.get('userid')

    greenhouses = fetch_all(
        "SELECT id, greenhouse_name FROM greenhouses WHERE userid = ? ORDER BY id",
        (userid,),
    ) if userid else []

    # Count sensors scoped to this user's greenhouses
    schemas_raw = fetch_all(
        """
        SELECT ss.id, ss.name
        FROM sensor_schemas ss
        JOIN greenhouses g ON g.id = ss.greenhouse_id
        WHERE g.userid = ?
        ORDER BY ss.name
        """,
        (userid,),
    ) if userid else []

    # Summary counts
    total_readings = fetch_one("SELECT COUNT(*) as cnt FROM sensor_readings_custom") or {}
    total_devices = fetch_one("SELECT COUNT(*) as cnt FROM sensor_devices") or {}
    unacked_alerts = fetch_all(
        """
        SELECT a.id, a.field_name, a.value, a.triggered_at,
               r.message, r.operator, r.threshold, g.greenhouse_name
        FROM notification_alerts a
        LEFT JOIN notification_rules r ON r.id = a.rule_id
        LEFT JOIN greenhouses g ON g.id = a.greenhouse_id
        WHERE a.acknowledged = 0
        ORDER BY a.triggered_at DESC
        LIMIT 10
        """
    )

    # Latest readings per greenhouse (for the summary cards)
    for gh in greenhouses:
        latest = fetch_one(
            """
            SELECT r.data_json, r.recorded_at, s.name as schema_name
            FROM sensor_readings_custom r
            LEFT JOIN sensor_schemas s ON s.id = r.schema_id
            WHERE r.greenhouse_id = ?
            ORDER BY r.recorded_at DESC, r.id DESC LIMIT 1
            """,
            (gh['id'],),
        )
        if latest and latest.get('data_json'):
            latest['data'] = json.loads(latest.pop('data_json'))
        elif latest:
            latest.pop('data_json', None)
        gh['latest'] = latest

    needs_greenhouse = len(greenhouses) == 0

    return render_template(
        "dashboard/index.html",
        greenhouses=greenhouses,
        schemas=schemas_raw,
        unacked_alerts=unacked_alerts,
        total_readings=total_readings.get('cnt', 0),
        total_devices=total_devices.get('cnt', 0),
        needs_greenhouse=needs_greenhouse,
    )


@bp.route("/overview", methods=["GET"])
@login_required
def overview():
    userid = session.get('userid')

    charts = fetch_all(
        """
        SELECT c.id, c.chart_name, c.chart_type, c.field_name, c.color,
               c.greenhouse_id, c.schema_id, s.name as schema_name,
               g.greenhouse_name
        FROM dashboard_charts c
        LEFT JOIN sensor_schemas s ON s.id = c.schema_id
        LEFT JOIN greenhouses g ON g.id = c.greenhouse_id
        WHERE c.userid = ?
        ORDER BY c.position, c.id
        """,
        (userid,),
    ) if userid else []

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

    greenhouses = fetch_all(
        "SELECT id, greenhouse_name FROM greenhouses WHERE userid = ? ORDER BY id",
        (userid,),
    ) if userid else []

    return render_template(
        "dashboard/overview.html",
        charts=charts,
        schemas=schemas,
        greenhouses=greenhouses,
    )


@bp.route("/dashboard/charts", methods=["POST"])
@login_required
def create_chart():
    userid = session.get('userid')
    chart_name = request.form.get('chart_name', '').strip()
    chart_type = request.form.get('chart_type', 'line')
    schema_id = request.form.get('schema_id') or None
    field_name = request.form.get('field_name', '').strip()
    greenhouse_id = request.form.get('greenhouse_id') or None
    color = request.form.get('color', '#22c55e')

    if not field_name:
        flash('Field name is required.', 'error')
        return redirect(url_for('main.overview'))

    if not chart_name:
        chart_name = field_name.replace('_', ' ').title()

    created_at = datetime.now(timezone.utc).isoformat()
    execute(
        """
        INSERT INTO dashboard_charts
            (userid, greenhouse_id, chart_name, chart_type, schema_id, field_name, color, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (userid, greenhouse_id, chart_name, chart_type, schema_id, field_name, color, created_at),
    )
    flash('Chart added.', 'success')
    return redirect(url_for('main.overview'))


@bp.route("/dashboard/charts/<int:chart_id>/edit", methods=["POST"])
@login_required
def edit_chart(chart_id):
    userid = session.get('userid')
    chart_name = request.form.get('chart_name', '').strip()
    chart_type = request.form.get('chart_type', 'line')
    schema_id = request.form.get('schema_id') or None
    field_name = request.form.get('field_name', '').strip()
    greenhouse_id = request.form.get('greenhouse_id') or None
    color = request.form.get('color', '#22c55e')

    if not field_name:
        flash('Field name is required.', 'error')
        return redirect(url_for('main.overview'))

    if not chart_name:
        chart_name = field_name.replace('_', ' ').title()

    execute(
        """
        UPDATE dashboard_charts
        SET chart_name = ?, chart_type = ?, schema_id = ?, field_name = ?, greenhouse_id = ?, color = ?
        WHERE id = ? AND userid = ?
        """,
        (chart_name, chart_type, schema_id, field_name, greenhouse_id, color, chart_id, userid),
    )
    flash('Chart updated.', 'success')
    return redirect(url_for('main.overview'))


@bp.route("/dashboard/charts/<int:chart_id>/delete", methods=["POST"])
@login_required
def delete_chart(chart_id):
    execute(
        "DELETE FROM dashboard_charts WHERE id = ? AND userid = ?",
        (chart_id, session.get('userid')),
    )
    flash('Chart removed.', 'success')
    return redirect(url_for('main.overview'))
