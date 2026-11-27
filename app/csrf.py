<<<<<<< HEAD
"""Session-backed CSRF protection for state-changing form and JSON requests.

Requests must send a ``csrf_token`` that matches the token stored in the
user's session. Tokens may be sent as a form field, JSON field, or header.

If the team later adopts Flask-WTF's ``CSRFProtect``, delete this file and
remove ``init_csrf(app)`` from create_app() and the blueprint/route hooks.
Templates already call ``csrf_token()`` the same way.
=======
"""CSRF protection for every state-changing request (M: foundation).

Every POST/PUT/PATCH/DELETE must send the session's token, either as the hidden
form field ``csrf_token`` or, for JavaScript fetch() calls, the ``X-CSRFToken``
header. Templates get the token with ``{{ csrf_token() }}``; base.html also puts it
in ``<meta name="csrf-token">`` so scripts can read it.

If the team later adopts Flask-WTF's ``CSRFProtect``, delete this file and
``init_csrf(app)`` in create_app(); the templates already use ``csrf_token()``.
>>>>>>> ec320aee3ad7c4b7b16200062781203f08fd4cfd
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
<<<<<<< HEAD
    payload = request.get_json(silent=True)
    sent = (request.headers.get("X-CSRFToken") or
            (payload.get("csrf_token", "") if isinstance(payload, dict) else "") or
            request.form.get("csrf_token", ""))
=======
    sent = request.form.get("csrf_token") or request.headers.get("X-CSRFToken", "")
>>>>>>> ec320aee3ad7c4b7b16200062781203f08fd4cfd
    expected = session.get("_csrf_token", "")
    if (not isinstance(sent, str) or not isinstance(expected, str) or not expected or
            not hmac.compare_digest(sent.encode(), expected.encode())):
        abort(400, description="Missing or invalid CSRF token. Reload the page and try again.")


def init_csrf(app):
    app.jinja_env.globals["csrf_token"] = generate_csrf_token
    app.before_request(csrf_protect)
