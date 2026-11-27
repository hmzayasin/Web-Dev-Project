"""Session-backed CSRF protection for state-changing form and JSON requests.

Requests must send a ``csrf_token`` that matches the token stored in the
user's session. Tokens may be sent as a form field, JSON field, or header.

If the team later adopts Flask-WTF's ``CSRFProtect``, delete this file and
remove ``init_csrf(app)`` from create_app() and the blueprint/route hooks.
Templates already call ``csrf_token()`` the same way.
"""
import hmac
import secrets

from flask import abort, request, session

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def generate_csrf_token():
    if "_csrf_token" not in session:
        session["_csrf_token"] = secrets.token_hex(16)
    return session["_csrf_token"]


def csrf_protect():
    """Use as ``blueprint.before_request``."""
    if request.method in SAFE_METHODS:
        return
    payload = request.get_json(silent=True)
    sent = (request.headers.get("X-CSRFToken") or
            (payload.get("csrf_token", "") if isinstance(payload, dict) else "") or
            request.form.get("csrf_token", ""))
    expected = session.get("_csrf_token", "")
    if (not isinstance(sent, str) or not isinstance(expected, str) or not expected or
            not hmac.compare_digest(sent.encode(), expected.encode())):
        abort(400, description="Missing or invalid CSRF token. Reload the page and try again.")


def init_csrf(app):
    app.jinja_env.globals["csrf_token"] = generate_csrf_token
