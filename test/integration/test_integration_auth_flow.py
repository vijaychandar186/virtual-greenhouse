import unittest

from werkzeug.security import generate_password_hash

from src.config import Config
from src.db import execute, fetch_one

from test._helpers import make_full_app, temp_sqlite_db


class TestAuthFlow(unittest.TestCase):
    # ---- login ----

    def test_login_page_renders(self):
        with temp_sqlite_db() as db_path:
            app = make_full_app(db_path)
            c = app.test_client()
            r = c.get("/login")
            self.assertEqual(r.status_code, 200)
            self.assertIn(b"Sign In", r.data)

    def test_login_success_plain_password(self):
        with temp_sqlite_db() as db_path:
            app = make_full_app(db_path)
            c = app.test_client()
            execute(
                "INSERT INTO users (username, password, email, api_key) VALUES (?, ?, ?, ?)",
                ("testuser", "testpass", "t@e.com", "key"),
            )
            r = c.post("/login", data={"username": "testuser", "password": "testpass"})
            self.assertEqual(r.status_code, 302)
            self.assertIn("/dashboard", r.location)

    def test_login_success_hashed_password(self):
        with temp_sqlite_db() as db_path:
            app = make_full_app(db_path)
            c = app.test_client()
            hashed = generate_password_hash("secret")
            execute(
                "INSERT INTO users (username, password, email, api_key) VALUES (?, ?, ?, ?)",
                ("user1", hashed, "u@e.com", "key"),
            )
            r = c.post("/login", data={"username": "user1", "password": "secret"})
            self.assertEqual(r.status_code, 302)
            self.assertIn("/dashboard", r.location)

    def test_login_wrong_password(self):
        with temp_sqlite_db() as db_path:
            app = make_full_app(db_path)
            c = app.test_client()
            execute(
                "INSERT INTO users (username, password, email, api_key) VALUES (?, ?, ?, ?)",
                ("testuser", "testpass", "t@e.com", "key"),
            )
            r = c.post("/login", data={"username": "testuser", "password": "wrong"})
            self.assertEqual(r.status_code, 302)
            self.assertIn("/login", r.location)

    def test_login_missing_fields(self):
        with temp_sqlite_db() as db_path:
            app = make_full_app(db_path)
            c = app.test_client()
            r = c.post("/login", data={"username": "x"})
            self.assertEqual(r.status_code, 302)
            self.assertIn("/login", r.location)

    # ---- register ----

    def test_register_page_renders(self):
        with temp_sqlite_db() as db_path:
            app = make_full_app(db_path)
            c = app.test_client()
            r = c.get("/register")
            self.assertEqual(r.status_code, 200)
            self.assertIn(b"Sign Up", r.data)

    def test_register_success(self):
        with temp_sqlite_db() as db_path:
            app = make_full_app(db_path)
            c = app.test_client()
            r = c.post("/register", data={
                "username": "newuser",
                "password": "newpass",
                "email": "new@example.com",
            })
            self.assertEqual(r.status_code, 302)
            self.assertIn("/login", r.location)
            user = fetch_one("SELECT * FROM users WHERE username = ?", ("newuser",))
            self.assertIsNotNone(user)
            self.assertTrue(
                user["password"].startswith("scrypt:")
                or user["password"].startswith("pbkdf2:")
            )
            self.assertIsNotNone(user["api_key"])

    def test_register_duplicate_user(self):
        with temp_sqlite_db() as db_path:
            app = make_full_app(db_path)
            c = app.test_client()
            execute(
                "INSERT INTO users (username, password, email, api_key) VALUES (?, ?, ?, ?)",
                ("existing", "pw", "e@e.com", "key"),
            )
            r = c.post("/register", data={
                "username": "existing",
                "password": "pw",
                "email": "new@e.com",
            })
            self.assertEqual(r.status_code, 302)
            self.assertIn("/register", r.location)

    def test_register_invalid_email(self):
        with temp_sqlite_db() as db_path:
            app = make_full_app(db_path)
            c = app.test_client()
            r = c.post("/register", data={
                "username": "newuser",
                "password": "pw",
                "email": "not-an-email",
            })
            self.assertEqual(r.status_code, 302)
            self.assertIn("/register", r.location)

    def test_register_missing_fields(self):
        with temp_sqlite_db() as db_path:
            app = make_full_app(db_path)
            c = app.test_client()
            r = c.post("/register", data={"username": "x"})
            self.assertEqual(r.status_code, 302)
            self.assertIn("/register", r.location)

    # ---- logout ----

    def test_logout_clears_session_and_redirects(self):
        with temp_sqlite_db() as db_path:
            app = make_full_app(db_path)
            c = app.test_client()
            with c.session_transaction() as sess:
                sess["username"] = "u"
                sess["userid"] = 1
                sess["loggedin"] = True
            r = c.get("/logout")
            self.assertEqual(r.status_code, 302)
            self.assertIn("/login", r.location)
            self.assertIn("no-store", r.headers.get("Cache-Control", ""))
            with c.session_transaction() as sess:
                self.assertNotIn("username", sess)

    # ---- settings ----

    def test_settings_page_renders(self):
        with temp_sqlite_db() as db_path:
            app = make_full_app(db_path)
            c = app.test_client()
            execute(
                "INSERT INTO users (username, password, email, api_key) VALUES (?, ?, ?, ?)",
                ("u1", "pw", "u1@e.com", "old-key"),
            )
            with c.session_transaction() as sess:
                sess["username"] = "u1"
                sess["userid"] = 1
                sess["loggedin"] = True
            r = c.get("/settings")
            self.assertEqual(r.status_code, 200)

    def test_rotate_api_key(self):
        with temp_sqlite_db() as db_path:
            app = make_full_app(db_path)
            c = app.test_client()
            execute(
                "INSERT INTO users (username, password, email, api_key) VALUES (?, ?, ?, ?)",
                ("u1", "pw", "u1@e.com", "old-key"),
            )
            with c.session_transaction() as sess:
                sess["username"] = "u1"
                sess["userid"] = 1
                sess["loggedin"] = True
            r = c.post("/settings/rotate-key")
            self.assertEqual(r.status_code, 302)
            self.assertIn("/settings", r.location)
            user = fetch_one("SELECT api_key FROM users WHERE userid = ?", (1,))
            self.assertNotEqual(user["api_key"], "old-key")
            self.assertEqual(len(user["api_key"]), 64)  # 32 bytes hex

    # ---- protected routes redirect when not logged in ----

    def test_protected_routes_redirect_to_login(self):
        with temp_sqlite_db() as db_path:
            app = make_full_app(db_path)
            c = app.test_client()
            for path in ["/dashboard", "/settings", "/existing_greenhouse",
                         "/sensor_status", "/schemas", "/notifications"]:
                with self.subTest(path=path):
                    r = c.get(path)
                    self.assertEqual(r.status_code, 302)
                    self.assertIn("/login", r.location)


if __name__ == "__main__":
    unittest.main()
