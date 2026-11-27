"""F20 saved vacancies (M, extra feature).

Applicants bookmark vacancies and come back to them later. The list shows what has
happened since: closing soon, closed, or removed by an administrator.

Kept in its own module (model + routes) so it doesn't collide with other slices.
Saving and unsaving are explicit actions ("save" / "unsave") rather than a toggle, so
a double-click or a resent request can't flip the result back (idempotent).
"""
from datetime import datetime

from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy.exc import IntegrityError

from app import db
from app.auth import _safe_next
from app.main import role_required
from app.models import Application, Vacancy


class SavedVacancy(db.Model):
    __tablename__ = "saved_vacancy"
    __table_args__ = (db.UniqueConstraint("user_id", "vacancy_id", name="uq_save_vacancy_once"),)
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    vacancy_id = db.Column(db.Integer, db.ForeignKey("vacancy.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    vacancy = db.relationship("Vacancy")


saved_bp = Blueprint("saved", __name__)


def _publicly_visible(vacancy):
    return vacancy.status in ("open", "closed") and vacancy.employer.status == "verified"


def saved_state(vacancy):
    """What the applicant should see for a saved vacancy: (key, label)."""
    if vacancy.status == "removed":
        return "removed", "Removed by an administrator"
    if not _publicly_visible(vacancy):
        return "unavailable", "Temporarily unavailable"
    if vacancy.effective_status == "closed":
        return "closed", "Closed"
    days = vacancy.days_left
    if days is not None and days <= 7:
        return "soon", "Closes today" if days == 0 else ("Closes tomorrow" if days == 1 else f"Closes in {days} days")
    return "open", "Open"


def _saved_ids():
    """Ids the current applicant has saved; looked up once per request for the job cards."""
    if "saved_ids" not in g:
        g.saved_ids = set()
        if current_user.is_authenticated and current_user.role == "applicant":
            g.saved_ids = {vid for (vid,) in db.session.query(SavedVacancy.vacancy_id)
                           .filter_by(user_id=current_user.id)}
    return g.saved_ids


def init_saved(app):
    app.jinja_env.globals["is_saved"] = lambda vid: vid in _saved_ids()


@saved_bp.route("/saved")
@role_required("applicant")
def saved_list():
    rows = (SavedVacancy.query.filter_by(user_id=current_user.id)
            .order_by(SavedVacancy.created_at.desc()).all())
    applied = {vid for (vid,) in db.session.query(Application.vacancy_id)
               .filter_by(applicant_id=current_user.id)}
    items = [{"row": r, "vacancy": r.vacancy, "state": saved_state(r.vacancy),
              "applied": r.vacancy_id in applied} for r in rows]
    # still-open roles first, soonest deadline first; then everything that has closed or gone
    order = {"soon": 0, "open": 1, "closed": 2, "unavailable": 3, "removed": 4}
    items.sort(key=lambda i: (order[i["state"][0]], i["vacancy"].closing_date or datetime.max.date()))
    return render_template("saved.html", items=items)


@saved_bp.route("/saved/<int:vid>", methods=["POST"])
@role_required("applicant")
def save(vid):
    action = request.form.get("action")
    if action not in ("save", "unsave"):
        abort(400)
    vacancy = db.get_or_404(Vacancy, vid)
    row = SavedVacancy.query.filter_by(user_id=current_user.id, vacancy_id=vid).first()
    if action == "save":
        if not _publicly_visible(vacancy):
            abort(404)                     # don't reveal drafts / hidden vacancies
        if not vacancy.is_open:
            flash("Only open vacancies can be saved.", "error")
        elif row is None:
            db.session.add(SavedVacancy(user_id=current_user.id, vacancy_id=vid))
            try:
                db.session.commit()
            except IntegrityError:         # saved twice at the same moment: already saved is fine
                db.session.rollback()
            flash("Saved. Find it under Saved jobs.", "success")
        else:
            flash("Already in your saved jobs.", "success")
    else:
        if row is not None:
            db.session.delete(row)
            db.session.commit()
        flash("Removed from your saved jobs.", "success")
    return redirect(_safe_next(request.form.get("next")) or url_for("saved.saved_list"))
