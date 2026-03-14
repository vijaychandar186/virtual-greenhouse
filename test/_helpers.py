import os
import tempfile
from contextlib import contextmanager

from flask import Flask

from src.config import Config
from src.db import init_sqlite
from src.routes import api_bp


@contextmanager
def temp_sqlite_db():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        yield db_path


def make_api_app(sqlite_path: str) -> Flask:
    Config.SQLITE_PATH = sqlite_path
    init_sqlite()

    app = Flask(__name__)
    app.config["TESTING"] = True
    app.secret_key = "test-secret"
    app.register_blueprint(api_bp)
    return app


def make_full_app(sqlite_path: str) -> Flask:
    from src.routes import auth_bp, greenhouse_bp, main_bp, sensors_bp, api_bp

    src_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src")
    Config.SQLITE_PATH = sqlite_path
    init_sqlite()

    app = Flask(
        __name__,
        template_folder=os.path.join(src_dir, "templates"),
        static_folder=os.path.join(src_dir, "static"),
    )
    app.config["TESTING"] = True
    app.secret_key = "test-secret"
    app.register_blueprint(auth_bp)
    app.register_blueprint(greenhouse_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(sensors_bp)
    app.register_blueprint(api_bp)
    return app

