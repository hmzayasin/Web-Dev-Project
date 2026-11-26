"""Tiny CSRF protection for the vacancy-management forms.

Every state-changing request under /manage/vacancies must send the hidden
field ``csrf_token`` that matches the token stored in the user's session.

If the team later adopts Flask-WTF's ``CSRFProtect``, delete this file, remove
``init_csrf(app)`` from create_app() and the ``before_request`` line in
vacancies.py; the templates already call ``csrf_token()`` the same way.
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
    sent = request.form.get("csrf_token", "")
    expected = session.get("_csrf_token", "")
    if not expected or not hmac.compare_digest(sent.encode(), expected.encode()):
        abort(400, description="Missing or invalid form token. Reload the page and try again.")


def init_csrf(app):
    app.jinja_env.globals["csrf_token"] = generate_csrf_token
