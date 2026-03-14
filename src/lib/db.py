import os
import sqlite3
from .config import Config


def _row_to_dict(row):
    if row is None:
        return None
    return dict(row)


def _rows_to_dicts(rows):
    return [dict(row) for row in rows]


def _sqlite_connect():
    os.makedirs(os.path.dirname(Config.SQLITE_PATH), exist_ok=True)
    conn = sqlite3.connect(Config.SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_sqlite():
    conn = _sqlite_connect()
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            userid INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            email TEXT NOT NULL
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS greenhouses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            location TEXT NOT NULL,
            greenhouse_name TEXT NOT NULL,
            sensors TEXT NOT NULL DEFAULT 'unspecified',
            length TEXT NOT NULL DEFAULT 'unspecified',
            width TEXT NOT NULL DEFAULT 'unspecified',
            description TEXT DEFAULT '',
            primary_schema TEXT DEFAULT '',
            userid INTEGER NOT NULL,
            FOREIGN KEY (userid) REFERENCES users(userid)
        )
        """
    )
    # Migrate existing greenhouses table with new optional columns
    for col_def in [
        "description TEXT DEFAULT ''",
        "primary_schema TEXT DEFAULT ''",
    ]:
        try:
            cur.execute(f"ALTER TABLE greenhouses ADD COLUMN {col_def}")
        except Exception:
            pass

    # Migrate users table: per-user API key
    try:
        cur.execute("ALTER TABLE users ADD COLUMN api_key TEXT")
    except Exception:
        pass

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS sensor_status (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            temperature REAL,
            humidity REAL,
            light REAL,
            co2 REAL
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS sensor_devices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            greenhouse_id INTEGER,
            device_id TEXT UNIQUE,
            label TEXT,
            location TEXT,
            last_seen_at TEXT,
            notes TEXT,
            FOREIGN KEY (greenhouse_id) REFERENCES greenhouses(id)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS sensor_schemas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            greenhouse_id INTEGER,
            name TEXT NOT NULL,
            description TEXT,
            fields_json TEXT,
            created_at TEXT,
            FOREIGN KEY (greenhouse_id) REFERENCES greenhouses(id)
        )
        """
    )
    # Migrate old installs: sensor_schemas had name TEXT UNIQUE and no greenhouse_id
    _sc_cols = [row[1] for row in conn.execute("PRAGMA table_info(sensor_schemas)").fetchall()]
    if 'greenhouse_id' not in _sc_cols:
        cur.execute("ALTER TABLE sensor_schemas RENAME TO sensor_schemas_old")
        cur.execute(
            """
            CREATE TABLE sensor_schemas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                greenhouse_id INTEGER,
                name TEXT NOT NULL,
                description TEXT,
                fields_json TEXT,
                created_at TEXT,
                FOREIGN KEY (greenhouse_id) REFERENCES greenhouses(id)
            )
            """
        )
        cur.execute(
            """
            INSERT INTO sensor_schemas (greenhouse_id, name, description, fields_json, created_at)
            SELECT
                (SELECT id FROM greenhouses ORDER BY id LIMIT 1),
                name, description, fields_json, created_at
            FROM sensor_schemas_old
            """
        )
        cur.execute("DROP TABLE sensor_schemas_old")
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS sensor_readings_custom (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            greenhouse_id INTEGER,
            device_id TEXT,
            schema_id INTEGER,
            source TEXT,
            data_json TEXT,
            recorded_at TEXT,
            userid INTEGER,
            FOREIGN KEY (greenhouse_id) REFERENCES greenhouses(id),
            FOREIGN KEY (schema_id) REFERENCES sensor_schemas(id)
        )
        """
    )
    # Migrate sensor_readings_custom: track which user owns the reading
    try:
        cur.execute("ALTER TABLE sensor_readings_custom ADD COLUMN userid INTEGER")
    except Exception:
        pass
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS notification_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            greenhouse_id INTEGER,
            schema_id INTEGER,
            field_name TEXT NOT NULL,
            operator TEXT NOT NULL,
            threshold REAL NOT NULL,
            message TEXT DEFAULT '',
            enabled INTEGER DEFAULT 1,
            created_at TEXT,
            FOREIGN KEY (greenhouse_id) REFERENCES greenhouses(id),
            FOREIGN KEY (schema_id) REFERENCES sensor_schemas(id)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS notification_alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rule_id INTEGER,
            greenhouse_id INTEGER,
            device_id TEXT,
            field_name TEXT,
            value REAL,
            triggered_at TEXT,
            acknowledged INTEGER DEFAULT 0,
            FOREIGN KEY (rule_id) REFERENCES notification_rules(id)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS dashboard_charts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            userid INTEGER NOT NULL,
            greenhouse_id INTEGER,
            chart_name TEXT NOT NULL,
            chart_type TEXT NOT NULL DEFAULT 'line',
            schema_id INTEGER,
            field_name TEXT NOT NULL,
            color TEXT DEFAULT '#22c55e',
            position INTEGER DEFAULT 0,
            created_at TEXT,
            FOREIGN KEY (userid) REFERENCES users(userid),
            FOREIGN KEY (greenhouse_id) REFERENCES greenhouses(id),
            FOREIGN KEY (schema_id) REFERENCES sensor_schemas(id)
        )
        """
    )

    # Backfill api_key for any existing users that don't have one
    import secrets as _secrets
    rows = cur.execute("SELECT userid FROM users WHERE api_key IS NULL").fetchall()
    for row in rows:
        cur.execute(
            "UPDATE users SET api_key = ? WHERE userid = ?",
            (_secrets.token_hex(32), row[0]),
        )

    conn.commit()
    conn.close()


def fetch_one(sql, params=()):
    conn = _sqlite_connect()
    cur = conn.cursor()
    cur.execute(sql, params)
    row = cur.fetchone()
    conn.close()
    return _row_to_dict(row)


def fetch_all(sql, params=()):
    conn = _sqlite_connect()
    cur = conn.cursor()
    cur.execute(sql, params)
    rows = cur.fetchall()
    conn.close()
    return _rows_to_dicts(rows)


def execute(sql, params=()):
    conn = _sqlite_connect()
    cur = conn.cursor()
    cur.execute(sql, params)
    conn.commit()
    conn.close()


def execute_lastrowid(sql, params=()):
    conn = _sqlite_connect()
    cur = conn.cursor()
    cur.execute(sql, params)
    conn.commit()
    rowid = cur.lastrowid
    conn.close()
    return rowid
