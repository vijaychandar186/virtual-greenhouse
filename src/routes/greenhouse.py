import json
from datetime import datetime, timezone
from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from ..lib.db import fetch_one, fetch_all, execute, execute_lastrowid
from ..lib.auth_utils import login_required

bp = Blueprint('greenhouse', __name__)


def _parse_schema_fields(fields_json):
    """Return list of dicts with name/type/unit, handling legacy string list format."""
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


# ── Greenhouse CRUD ────────────────────────────────────────────────────────────

@bp.route('/create_greenhouse', methods=['GET', 'POST'])
@login_required
def create_greenhouse():
    if request.method == 'POST':
        greenhouse_name = request.form.get('greenhouse_name', '').strip()
        location = request.form.get('location', '').strip()
        description = request.form.get('description', '').strip()

        if not greenhouse_name or not location:
            flash('Name and location are required.', 'error')
            return redirect(url_for('greenhouse.create_greenhouse'))

        userid = session.get('userid')
        try:
            new_id = execute_lastrowid(
                """
                INSERT INTO greenhouses
                    (location, greenhouse_name, description, sensors, length, width, userid)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (location, greenhouse_name, description, 'custom', '', '', userid),
            )
            flash('Greenhouse created. Now add sensors to it.', 'success')
            return redirect(url_for('greenhouse.greenhouse_detail', gh_id=new_id))
        except Exception:
            flash('Failed to create greenhouse.', 'error')
            return redirect(url_for('greenhouse.create_greenhouse'))

    return render_template('dashboard/details.html')


@bp.route('/existing_greenhouse')
@login_required
def existing():
    userid = session.get('userid')
    greenhouses = fetch_all(
        "SELECT id, greenhouse_name, location, description FROM greenhouses WHERE userid = ? ORDER BY id",
        (userid,),
    ) if userid else []

    for gh in greenhouses:
        # sensor count
        sensor_cnt = fetch_one(
            "SELECT COUNT(*) as cnt FROM sensor_schemas WHERE greenhouse_id = ?",
            (gh['id'],),
        )
        gh['sensor_count'] = sensor_cnt['cnt'] if sensor_cnt else 0

        # latest reading
        latest = fetch_one(
            """
            SELECT r.data_json, r.recorded_at, r.device_id, s.name as schema_name
            FROM sensor_readings_custom r
            LEFT JOIN sensor_schemas s ON s.id = r.schema_id
            WHERE r.greenhouse_id = ?
            ORDER BY r.recorded_at DESC, r.id DESC
            LIMIT 1
            """,
            (gh['id'],),
        )
        if latest and latest.get('data_json'):
            latest['data'] = json.loads(latest.pop('data_json'))
        elif latest:
            latest.pop('data_json', None)
        gh['latest'] = latest

        cnt = fetch_one(
            "SELECT COUNT(*) as cnt FROM sensor_readings_custom WHERE greenhouse_id = ?",
            (gh['id'],),
        )
        gh['reading_count'] = cnt['cnt'] if cnt else 0

    return render_template('dashboard/existing.html', greenhouses=greenhouses)


@bp.route('/greenhouses/<int:gh_id>')
@login_required
def greenhouse_detail(gh_id):
    userid = session.get('userid')
    gh = fetch_one(
        "SELECT id, greenhouse_name, location, description FROM greenhouses WHERE id = ? AND userid = ?",
        (gh_id, userid),
    )
    if not gh:
        flash('Greenhouse not found.', 'error')
        return redirect(url_for('greenhouse.existing'))

    # Sensors (schemas) for this greenhouse
    sensors_raw = fetch_all(
        "SELECT id, name, description, fields_json, created_at FROM sensor_schemas WHERE greenhouse_id = ? ORDER BY name",
        (gh_id,),
    )
    sensors = []
    for s in sensors_raw:
        sensors.append({
            "id": s["id"],
            "name": s["name"],
            "description": s.get("description", ""),
            "fields": _parse_schema_fields(s.get("fields_json", "[]")),
            "created_at": s.get("created_at", ""),
        })

    # Recent readings
    readings = fetch_all(
        """
        SELECT r.id, r.recorded_at, r.device_id, r.data_json, s.name as schema_name
        FROM sensor_readings_custom r
        LEFT JOIN sensor_schemas s ON s.id = r.schema_id
        WHERE r.greenhouse_id = ?
        ORDER BY r.recorded_at DESC, r.id DESC
        LIMIT 20
        """,
        (gh_id,),
    )
    for r in readings:
        r['data'] = json.loads(r.pop('data_json') or '{}')

    # Devices
    devices = fetch_all(
        "SELECT device_id, label, last_seen_at FROM sensor_devices WHERE greenhouse_id = ? ORDER BY last_seen_at DESC",
        (gh_id,),
    )

    # Alert rules for this greenhouse
    rules = fetch_all(
        """
        SELECT nr.id, nr.field_name, nr.operator, nr.threshold, nr.message, nr.enabled, nr.schema_id,
               s.name as schema_name
        FROM notification_rules nr
        LEFT JOIN sensor_schemas s ON s.id = nr.schema_id
        WHERE nr.greenhouse_id = ?
        ORDER BY nr.id DESC
        """,
        (gh_id,),
    )

    return render_template(
        'dashboard/greenhouse_detail.html',
        gh=gh,
        sensors=sensors,
        readings=readings,
        devices=devices,
        rules=rules,
    )


@bp.route('/greenhouses/<int:gh_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_greenhouse(gh_id):
    userid = session.get('userid')
    gh = fetch_one(
        "SELECT id, greenhouse_name, location, description FROM greenhouses WHERE id = ? AND userid = ?",
        (gh_id, userid),
    )
    if not gh:
        flash('Greenhouse not found.', 'error')
        return redirect(url_for('greenhouse.existing'))

    if request.method == 'POST':
        greenhouse_name = request.form.get('greenhouse_name', '').strip()
        location = request.form.get('location', '').strip()
        description = request.form.get('description', '').strip()

        if not greenhouse_name or not location:
            flash('Name and location are required.', 'error')
            return redirect(url_for('greenhouse.edit_greenhouse', gh_id=gh_id))

        execute(
            """
            UPDATE greenhouses
            SET greenhouse_name = ?, location = ?, description = ?
            WHERE id = ? AND userid = ?
            """,
            (greenhouse_name, location, description, gh_id, userid),
        )
        flash('Greenhouse updated.', 'success')
        return redirect(url_for('greenhouse.greenhouse_detail', gh_id=gh_id))

    return render_template('dashboard/details.html', greenhouse=gh)


@bp.route('/greenhouses/<int:gh_id>/delete', methods=['POST'])
@login_required
def delete_greenhouse(gh_id):
    userid = session.get('userid')
    execute("DELETE FROM sensor_devices WHERE greenhouse_id = ? AND greenhouse_id IN (SELECT id FROM greenhouses WHERE userid = ?)", (gh_id, userid))
    execute("DELETE FROM sensor_readings_custom WHERE greenhouse_id = ? AND greenhouse_id IN (SELECT id FROM greenhouses WHERE userid = ?)", (gh_id, userid))
    execute("DELETE FROM sensor_schemas WHERE greenhouse_id = ? AND greenhouse_id IN (SELECT id FROM greenhouses WHERE userid = ?)", (gh_id, userid))
    execute("DELETE FROM greenhouses WHERE id = ? AND userid = ?", (gh_id, userid))
    flash('Greenhouse deleted.', 'success')
    return redirect(url_for('greenhouse.existing'))


# ── Sensor (schema) CRUD — scoped to a greenhouse ─────────────────────────────

@bp.route('/greenhouses/<int:gh_id>/sensors/create', methods=['POST'])
@login_required
def create_greenhouse_sensor(gh_id):
    userid = session.get('userid')
    gh = fetch_one("SELECT id FROM greenhouses WHERE id = ? AND userid = ?", (gh_id, userid))
    if not gh:
        flash('Greenhouse not found.', 'error')
        return redirect(url_for('greenhouse.existing'))

    name = request.form.get('name', '').strip()
    description = request.form.get('description', '').strip()
    fields_json_str = request.form.get('fields_json', '[]')

    if not name:
        flash('Sensor name is required.', 'error')
        return redirect(url_for('greenhouse.greenhouse_detail', gh_id=gh_id))

    try:
        fields = json.loads(fields_json_str)
    except Exception:
        fields = []

    created_at = datetime.now(timezone.utc).isoformat()
    existing = fetch_one(
        "SELECT id FROM sensor_schemas WHERE greenhouse_id = ? AND name = ?",
        (gh_id, name),
    )
    if existing:
        execute(
            "UPDATE sensor_schemas SET description = ?, fields_json = ? WHERE id = ?",
            (description, json.dumps(fields), existing['id']),
        )
        flash(f'Sensor "{name}" updated.', 'success')
    else:
        execute(
            "INSERT INTO sensor_schemas (greenhouse_id, name, description, fields_json, created_at) VALUES (?, ?, ?, ?, ?)",
            (gh_id, name, description, json.dumps(fields), created_at),
        )
        flash(f'Sensor "{name}" added.', 'success')
    return redirect(url_for('greenhouse.greenhouse_detail', gh_id=gh_id))


@bp.route('/greenhouses/<int:gh_id>/sensors/<int:schema_id>/delete', methods=['POST'])
@login_required
def delete_greenhouse_sensor(gh_id, schema_id):
    userid = session.get('userid')
    gh = fetch_one("SELECT id FROM greenhouses WHERE id = ? AND userid = ?", (gh_id, userid))
    if not gh:
        flash('Greenhouse not found.', 'error')
        return redirect(url_for('greenhouse.existing'))

    execute("DELETE FROM sensor_schemas WHERE id = ? AND greenhouse_id = ?", (schema_id, gh_id))
    flash('Sensor removed.', 'success')
    return redirect(url_for('greenhouse.greenhouse_detail', gh_id=gh_id))


# ── Global sensor templates (greenhouse_id IS NULL) ───────────────────────────

@bp.route('/schemas')
@login_required
def schemas():
    schema_list = fetch_all(
        "SELECT id, name, description, fields_json, created_at FROM sensor_schemas WHERE greenhouse_id IS NULL ORDER BY name"
    )
    for s in schema_list:
        s['fields'] = _parse_schema_fields(s.get('fields_json', '[]'))
    return render_template('dashboard/schema_builder.html', schemas=schema_list)


@bp.route('/schemas/create', methods=['POST'])
@login_required
def create_schema():
    """Create or update a global sensor template (greenhouse_id = NULL)."""
    name = request.form.get('name', '').strip()
    description = request.form.get('description', '').strip()
    fields_json_str = request.form.get('fields_json', '[]')

    if not name:
        flash('Schema name is required.', 'error')
        return redirect(url_for('greenhouse.schemas'))

    try:
        fields = json.loads(fields_json_str)
    except Exception:
        fields = []

    created_at = datetime.now(timezone.utc).isoformat()
    existing = fetch_one("SELECT id FROM sensor_schemas WHERE name = ? AND greenhouse_id IS NULL", (name,))
    if existing:
        execute(
            "UPDATE sensor_schemas SET description = ?, fields_json = ? WHERE id = ?",
            (description, json.dumps(fields), existing['id']),
        )
        flash(f'Template "{name}" updated.', 'success')
    else:
        execute(
            "INSERT INTO sensor_schemas (greenhouse_id, name, description, fields_json, created_at) VALUES (NULL, ?, ?, ?, ?)",
            (name, description, json.dumps(fields), created_at),
        )
        flash(f'Template "{name}" created.', 'success')
    return redirect(url_for('greenhouse.schemas'))


@bp.route('/schemas/<int:schema_id>/delete', methods=['POST'])
@login_required
def delete_schema(schema_id):
    execute("DELETE FROM sensor_schemas WHERE id = ? AND greenhouse_id IS NULL", (schema_id,))
    flash('Template deleted.', 'success')
    return redirect(url_for('greenhouse.schemas'))
