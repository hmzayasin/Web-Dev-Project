"""CSRF protection for every state-changing request (M: foundation, H: JSON support).

Every POST/PUT/PATCH/DELETE must send the session's token as the hidden form
field ``csrf_token``, a ``csrf_token`` field in a JSON body, or the ``X-CSRFToken``
header (for JavaScript fetch() calls). Templates get the token with
``{{ csrf_token() }}``; base.html also puts it in ``<meta name="csrf-token">``.

If the team later adopts Flask-WTF's ``CSRFProtect``, delete this file and
``init_csrf(app)`` in create_app(); the templates already use ``csrf_token()``.
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
    """Runs before every request (and is harmless if a blueprint also registers it)."""
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
    app.before_request(csrf_protect)
