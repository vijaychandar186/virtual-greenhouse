import json
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from src.config import Config
from src.db import fetch_one, execute
from src.routes import api as api_mod

from test._helpers import temp_sqlite_db


class TestApiHelpersUnit(unittest.TestCase):
    def test_parse_timestamp_variants(self):
        fixed = datetime(2026, 3, 13, 12, 0, tzinfo=timezone.utc)
        with patch.object(api_mod, "datetime") as dt:
            dt.now.return_value = fixed
            dt.fromtimestamp.side_effect = datetime.fromtimestamp
            dt.fromisoformat.side_effect = datetime.fromisoformat
            self.assertEqual(api_mod._parse_timestamp(None), fixed)
            self.assertEqual(api_mod._parse_timestamp(0).tzinfo, timezone.utc)
            self.assertEqual(api_mod._parse_timestamp("2026-03-13T12:00:00Z").isoformat(), "2026-03-13T12:00:00+00:00")

    def test_normalize_schema_name(self):
        self.assertEqual(api_mod._normalize_schema_name({"schema": "a"}), "a")
        self.assertEqual(api_mod._normalize_schema_name({"schema_name": "b"}), "b")
        self.assertEqual(api_mod._normalize_schema_name({}), "default")

    def test_extract_data_prefers_data_dict(self):
        self.assertEqual(api_mod._extract_data({"data": {"x": 1}, "x": 2}), {"x": 1})

    def test_extract_data_filters_reserved(self):
        payload = {"device_id": "d", "schema": "s", "temperature": 22.2, "x": 1}
        self.assertEqual(api_mod._extract_data(payload), {"temperature": 22.2, "x": 1})

    def test_ensure_schema_merges_new_fields(self):
        with temp_sqlite_db() as db_path:
            Config.SQLITE_PATH = db_path
            from src.db import init_sqlite
            init_sqlite()

            execute(
                "INSERT INTO sensor_schemas (name, description, fields_json, created_at) VALUES (?, ?, ?, ?)",
                ("demo", "", json.dumps([{"name": "a", "type": "number", "unit": ""}]), "2026-03-13T00:00:00+00:00"),
            )
            schema_id = api_mod._ensure_schema("demo", ["a", "b"])
            self.assertIsNotNone(schema_id)
            row = fetch_one("SELECT fields_json FROM sensor_schemas WHERE name = ?", ("demo",))
            fields = json.loads(row["fields_json"])
            names = {f["name"] for f in fields}
            self.assertEqual(names, {"a", "b"})


    def test_ensure_schema_creates_new_schema(self):
        with temp_sqlite_db() as db_path:
            Config.SQLITE_PATH = db_path
            from src.db import init_sqlite
            init_sqlite()

            schema_id = api_mod._ensure_schema("brand_new", ["x", "y"])
            self.assertIsNotNone(schema_id)
            row = fetch_one("SELECT fields_json FROM sensor_schemas WHERE name = ?", ("brand_new",))
            fields = json.loads(row["fields_json"])
            names = {f["name"] for f in fields}
            self.assertEqual(names, {"x", "y"})

    def test_parse_timestamp_malformed_falls_back_to_now(self):
        fixed = datetime(2026, 3, 13, 12, 0, tzinfo=timezone.utc)
        with patch.object(api_mod, "datetime") as dt:
            dt.now.return_value = fixed
            dt.fromisoformat.side_effect = ValueError("bad")
            result = api_mod._parse_timestamp("not-a-date")
        self.assertEqual(result, fixed)

    def test_extract_data_without_data_key(self):
        payload = {"device_id": "d", "temperature": 22.2, "humidity": 65.0}
        result = api_mod._extract_data(payload)
        self.assertEqual(result, {"temperature": 22.2, "humidity": 65.0})


if __name__ == "__main__":
    unittest.main()

