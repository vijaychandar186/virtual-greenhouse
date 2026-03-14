import unittest

from flask import Blueprint
from flask import Flask
from werkzeug.security import generate_password_hash

from src.routes import auth as auth_mod
from src.auth_utils import login_required


class TestAuthUnit(unittest.TestCase):
    def test_verify_password_plain_and_hashed(self):
        self.assertTrue(auth_mod._verify_password("pw", "pw"))
        self.assertFalse(auth_mod._verify_password("pw", "nope"))

        hashed = generate_password_hash("pw")
        self.assertTrue(auth_mod._verify_password(hashed, "pw"))
        self.assertFalse(auth_mod._verify_password(hashed, "nope"))

    def test_login_required_redirects_and_sets_cache_headers(self):
        app = Flask(__name__)
        app.secret_key = "test"

        auth_bp = Blueprint("auth", __name__)

        @auth_bp.route("/login")
        def login():
            return "login"

        app.register_blueprint(auth_bp)

        @app.route("/private")
        @login_required
        def private():
            return "ok"

        c = app.test_client()
        r = c.get("/private")
        self.assertEqual(r.status_code, 302)
        self.assertIn("/login", r.location)

        with c.session_transaction() as sess:
            sess["username"] = "u"
        r2 = c.get("/private")
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(r2.data, b"ok")
        self.assertIn("no-store", r2.headers.get("Cache-Control", ""))


if __name__ == "__main__":
    unittest.main()
