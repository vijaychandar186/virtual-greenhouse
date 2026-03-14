import secrets
from flask import Blueprint, render_template, request, redirect, url_for, session, flash, make_response
from werkzeug.security import generate_password_hash, check_password_hash
import re
from ..lib.db import fetch_one, execute
from ..lib.auth_utils import login_required

bp = Blueprint('auth', __name__)

def _verify_password(stored_password: str, provided_password: str) -> bool:
    if stored_password.startswith("pbkdf2:") or stored_password.startswith("scrypt:"):
        return check_password_hash(stored_password, provided_password)
    return stored_password == provided_password

@bp.route('/login', methods=['GET', 'POST'])
def login():
    msg = ''
    if request.method == 'POST':
        if 'username' not in request.form or 'password' not in request.form:
            flash('Please fill out the form.', 'error')
            return redirect(url_for('auth.login'))
        username = request.form['username']
        password = request.form['password']
        try:
            account = fetch_one('SELECT * FROM users WHERE username = ?', (username,))
            if account and _verify_password(account['password'], password):
                session['loggedin'] = True
                session['userid'] = account['userid']
                session['username'] = account['username']
                flash('Logged in successfully.', 'success')
                return redirect(url_for('main.dashboard'))
            flash('Incorrect username / password !', 'error')
            return redirect(url_for('auth.login'))
        except Exception:
            flash('Database connection failed. Check your DB file and permissions.', 'error')
            return redirect(url_for('auth.login'))
    return render_template('auth/login.html', msg=msg)

@bp.route('/logout')
def logout():
    session.clear()
    resp = make_response(redirect(url_for('auth.login')))
    resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, private, max-age=0'
    resp.headers['Pragma'] = 'no-cache'
    resp.headers['Expires'] = '0'
    return resp


@bp.route('/settings')
@login_required
def settings():
    user = fetch_one('SELECT userid, username, email, api_key FROM users WHERE userid = ?',
                     (session.get('userid'),))
    return render_template('dashboard/settings.html', user=user)


@bp.route('/settings/rotate-key', methods=['POST'])
@login_required
def rotate_api_key():
    new_key = secrets.token_hex(32)
    execute('UPDATE users SET api_key = ? WHERE userid = ?',
            (new_key, session.get('userid')))
    flash('API key rotated. Update your devices and simulator.', 'success')
    return redirect(url_for('auth.settings'))

@bp.route('/register', methods=['GET', 'POST'])
def register():
    msg = ''
    if request.method == 'POST':
        if 'username' not in request.form or 'password' not in request.form or 'email' not in request.form:
            flash('Please fill out the form !', 'error')
            return redirect(url_for('auth.register'))
        username = request.form['username']
        password = request.form['password']
        email = request.form['email']
        try:
            account = fetch_one('SELECT * FROM users WHERE username = ?', (username,))
            if account:
                flash('Account already exists !', 'error')
                return redirect(url_for('auth.register'))
            if not re.match(r'[^@]+@[^@]+\.[^@]+', email):
                flash('Invalid email address !', 'error')
                return redirect(url_for('auth.register'))
            if not re.match(r'[A-Za-z0-9]+', username):
                flash('Username must contain only characters and numbers !', 'error')
                return redirect(url_for('auth.register'))
            if not username or not password or not email:
                flash('Please fill out the form !', 'error')
                return redirect(url_for('auth.register'))
            hashed_password = generate_password_hash(password)
            api_key = secrets.token_hex(32)
            execute(
                'INSERT INTO users (username, password, email, api_key) VALUES (?, ?, ?, ?)',
                (username, hashed_password, email, api_key)
            )
            flash('Registration successful. Please sign in.', 'success')
            return redirect(url_for('auth.login'))
        except Exception:
            flash('Database connection failed. Check your DB file and permissions.', 'error')
            return redirect(url_for('auth.register'))
    return render_template('auth/register.html', msg=msg)
