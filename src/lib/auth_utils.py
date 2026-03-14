from functools import wraps
from flask import session, redirect, url_for, after_this_request


def login_required(f):
    """Protect a view: redirect to login if not authenticated.

    Also sets Cache-Control: no-store on every response so the browser
    never serves a stale authenticated page from cache after logout.
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'username' not in session:
            return redirect(url_for('auth.login'))

        @after_this_request
        def _no_cache(response):
            response.headers['Cache-Control'] = (
                'no-store, no-cache, must-revalidate, private, max-age=0'
            )
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '0'
            return response

        return f(*args, **kwargs)
    return decorated
