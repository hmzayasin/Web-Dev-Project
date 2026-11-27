"""F1 accounts: register, log in, log out (M).

Security notes
  * Every form here carries a CSRF token (checked app-wide in app/csrf.py).
  * Log out is POST-only, so another site can't log a user out with a link or image.
  * ?next= is only followed when it points back into InRole (no open redirects).
  * Public sign-up can only create applicants or recruiters; reviewers and admins are created by staff.
"""
from urllib.parse import urlparse

from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required, login_user, logout_user

from app import db
from app.models import Employer, User

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")

SIGNUP_ROLES = ("applicant", "recruiter")
LIMITS = {"name": 100, "email": 150, "organisation": 120, "organisation_description": 1000}


def _safe_next(target):
    """Only allow relative paths on this site, e.g. '/jobs/3'. Blocks '//evil.com' and 'https://evil.com'."""
    if not target or not target.startswith("/") or target.startswith("//") or "\\" in target:
        return None
    parts = urlparse(target)
    return target if not parts.scheme and not parts.netloc else None


def _fresh_session_token():
    # a new CSRF token after a log-in/log-out so an old token can't be reused
    session.pop("_csrf_token", None)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))
    if request.method == "POST":
        user = User.query.filter_by(email=request.form.get("email", "").strip().lower()).first()
        if user and user.check_password(request.form.get("password", "")):
            login_user(user)
            _fresh_session_token()
            flash("Welcome back.", "success")
            return redirect(_safe_next(request.args.get("next")) or url_for("main.dashboard"))
        flash("Email or password was incorrect.", "error")
        return render_template("login.html", email=request.form.get("email", "")), 401
    return render_template("login.html", email="")


def _validate_signup(form):
    errors = []
    name, email = form.get("name", "").strip(), form.get("email", "").strip().lower()
    password, role = form.get("password", ""), form.get("role", "applicant")
    organisation = form.get("organisation", "").strip()
    if not name or len(name) > LIMITS["name"]:
        errors.append("Enter your full name (up to 100 characters).")
    local, _, domain = email.partition("@")
    if not local or "." not in domain or " " in email or len(email) > LIMITS["email"]:
        errors.append("Enter a valid email address.")
    if len(password) < 8:
        errors.append("Choose a password of at least 8 characters.")
    if role not in SIGNUP_ROLES:
        errors.append("Choose whether you are joining as an applicant or a recruiter.")
    if role == "recruiter" and not (2 <= len(organisation) <= LIMITS["organisation"]):
        errors.append("Recruiters must enter their organisation's name.")
    if not errors and User.query.filter_by(email=email).first():
        errors.append("That email is already registered.")
    return errors


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))
    if request.method == "POST":
        errors = _validate_signup(request.form)
        if errors:
            for message in errors:
                flash(message, "error")
            return render_template("register.html", form=request.form), 400
        form = request.form
        role = form["role"]
        employer = None
        if role == "recruiter":
            # R6: new organisations start as "pending" until an admin verifies them in the moderation queue
            employer = Employer(name=form["organisation"].strip(), status="pending",
                                description=form.get("organisation_description", "").strip()[:LIMITS["organisation_description"]])
            db.session.add(employer)
            db.session.flush()
        user = User(name=form["name"].strip(), email=form["email"].strip().lower(), role=role,
                    employer_id=employer.id if employer else None)
        user.set_password(form["password"])
        db.session.add(user)
        db.session.commit()
        login_user(user)
        _fresh_session_token()
        if employer:
            flash("Account created. You can draft vacancies now; publishing starts once an admin verifies your organisation.", "success")
        else:
            flash("Account created. Add your CV on your profile before you apply.", "success")
        return redirect(url_for("main.dashboard"))
    return render_template("register.html", form={})


@auth_bp.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    _fresh_session_token()
    flash("You have been logged out.", "success")
    return redirect(url_for("main.home"))
