import os
from flask import Flask
from .lib.config import Config
from .lib.db import init_sqlite
from .routes import api_bp, auth_bp, greenhouse_bp, main_bp, sensors_bp

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
STATIC_DIR = os.path.join(BASE_DIR, "static")

app = Flask(__name__, template_folder=TEMPLATES_DIR, static_folder=STATIC_DIR)

app.secret_key = Config.SECRET_KEY

init_sqlite()

app.register_blueprint(main_bp)
app.register_blueprint(auth_bp)
app.register_blueprint(greenhouse_bp)
app.register_blueprint(sensors_bp)
app.register_blueprint(api_bp)

if __name__ == '__main__':
    app.run(debug=True)
