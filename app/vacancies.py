"""Vacancy management (F4) and applicant list (F9).  Blueprint: ``vacancies``.

Who may do what
  recruiter  create / edit / publish / close / reopen vacancies of THEIR employer (R1)
  reviewer   read-only: see their employer's vacancies and applicant lists
  admin      read-only here (moderation is a separate feature)
"""
from datetime import date

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user

from app import db
from app import vacancy_rules as rules
from app.csrf import csrf_protect
from app.main import role_required
from app.models import Application, User, Vacancy

vacancies_bp = Blueprint("vacancies", __name__, url_prefix="/manage/vacancies")
vacancies_bp.before_request(csrf_protect)


# ---- helpers ----------------------------------------------------------------
def _own_or_403(vid):
    """R1: staff may only touch vacancies owned by their own employer (admin sees all)."""
    vacancy = db.get_or_404(Vacancy, vid)
    if current_user.role != "admin":
        if current_user.employer_id is None or vacancy.employer_id != current_user.employer_id:
            abort(403)
    return vacancy


def _employer_verified():
    return current_user.employer is not None and current_user.employer.status == "verified"


def _application_count(vacancy):
    return Application.query.filter_by(vacancy_id=vacancy.id).count()


# ---- F4: list ---------------------------------------------------------------
@vacancies_bp.route("/")
@role_required("recruiter", "reviewer", "admin")
def manage():
    query = Vacancy.query
    if current_user.role != "admin":
        if current_user.employer_id is None:
            abort(403)
        query = query.filter_by(employer_id=current_user.employer_id)
    rows = query.order_by(Vacancy.created_at.desc()).all()

    tally = {"all": len(rows), "draft": 0, "open": 0, "closed": 0}
    for v in rows:
        tally[v.effective_status] = tally.get(v.effective_status, 0) + 1
    selected = rules.clean_choice(request.args.get("status", "all"), tuple(tally), "all")
    if selected != "all":
        rows = [v for v in rows if v.effective_status == selected]

    counts = dict(
        db.session.query(Application.vacancy_id, db.func.count(Application.id))
        .group_by(Application.vacancy_id).all()
    )
    return render_template(
        "manage_vacancies.html", vacancies=rows, tally=tally, selected=selected,
        counts=counts, can_edit=current_user.role == "recruiter",
        verified=_employer_verified(), today=date.today(),
    )


# ---- F4: create -------------------------------------------------------------
@vacancies_bp.route("/new", methods=["GET", "POST"])
@role_required("recruiter")
def create():
    if current_user.employer_id is None:
        abort(403)
    if request.method == "POST":
        action = request.form.get("action", "save")
        clean, errors = rules.validate_vacancy(request.form, require_future=(action == "publish"))
        if errors:
            for message in errors:
                flash(message, "error")
            return render_template("vacancy_form.html", form=request.form, mode="new",
                                   job_types=rules.JOB_TYPES, vacancy=None), 400
        vacancy = Vacancy(employer_id=current_user.employer_id, status=rules.DRAFT,
                          title=clean["title"], location=clean["location"],
                          job_type=clean["job_type"], description=clean["description"],
                          closing_date=clean["closing_date"])
        db.session.add(vacancy)
        if action == "publish":
            new_status, error = rules.transition(
                rules.DRAFT, "publish", employer_verified=_employer_verified(),
                closing_date=vacancy.closing_date)
            if error:
                flash("Saved as a draft. " + error, "error")
            else:
                vacancy.status = new_status
                flash("Vacancy published.", "success")
        else:
            flash("Draft saved.", "success")
        db.session.commit()
        return redirect(url_for("vacancies.manage"))
    return render_template("vacancy_form.html", form={"job_type": "Full-time"}, mode="new",
                           job_types=rules.JOB_TYPES, vacancy=None)


# ---- F4: edit ---------------------------------------------------------------
@vacancies_bp.route("/<int:vid>/edit", methods=["GET", "POST"])
@role_required("recruiter")
def edit(vid):
    vacancy = _own_or_403(vid)
    if vacancy.status not in rules.EDITABLE:
        flash("This vacancy was removed from public view by an administrator and can't be edited.", "error")
        return redirect(url_for("vacancies.manage"))
    if request.method == "POST":
        publishing = request.form.get("action") == "publish" and vacancy.status == rules.DRAFT
        clean, errors = rules.validate_vacancy(
            request.form, require_future=publishing or vacancy.status == rules.OPEN)
        if errors:
            for message in errors:
                flash(message, "error")
            return render_template("vacancy_form.html", form=request.form, mode="edit",
                                   job_types=rules.JOB_TYPES, vacancy=vacancy), 400
        vacancy.title, vacancy.location = clean["title"], clean["location"]
        vacancy.job_type, vacancy.description = clean["job_type"], clean["description"]
        vacancy.closing_date = clean["closing_date"]
        if publishing:
            new_status, error = rules.transition(
                vacancy.status, "publish", employer_verified=_employer_verified(),
                closing_date=vacancy.closing_date)
            if error:
                flash("Changes saved, but not published. " + error, "error")
            else:
                vacancy.status = new_status
                flash("Vacancy published.", "success")
        else:
            flash("Changes saved.", "success")
        db.session.commit()
        return redirect(url_for("vacancies.manage"))
    form = {"title": vacancy.title, "location": vacancy.location, "job_type": vacancy.job_type,
            "description": vacancy.description,
            "closing_date": vacancy.closing_date.isoformat() if vacancy.closing_date else ""}
    return render_template("vacancy_form.html", form=form, mode="edit",
                           job_types=rules.JOB_TYPES, vacancy=vacancy)


# ---- F4: publish / close / reopen / unpublish --------------------------------
@vacancies_bp.route("/<int:vid>/status", methods=["POST"])
@role_required("recruiter")
def change_status(vid):
    vacancy = _own_or_403(vid)
    action = request.form.get("action", "")
    new_status, error = rules.transition(
        vacancy.status, action, employer_verified=_employer_verified(),
        closing_date=vacancy.closing_date, application_count=_application_count(vacancy))
    if error:
        flash(error, "error")
    else:
        vacancy.status = new_status
        db.session.commit()
        flash({"publish": "Vacancy published.", "close": "Vacancy closed to new applications.",
               "reopen": "Vacancy reopened.", "unpublish": "Vacancy returned to draft."}[action], "success")
    return redirect(url_for("vacancies.manage"))


# ---- F9: applicant list -------------------------------------------------------
@vacancies_bp.route("/<int:vid>/applicants")
@role_required("recruiter", "reviewer", "admin")
def applicants(vid):
    vacancy = _own_or_403(vid)
    status = rules.clean_choice(request.args.get("status", ""), rules.APPLICATION_STATUSES, "")
    sort = rules.clean_choice(request.args.get("sort", "newest"), rules.SORTS, "newest")
    term = request.args.get("q", "").strip()[:100]
    page = rules.clean_page(request.args.get("page"))

    # counts per stage always reflect ALL applicants, whatever filter is active
    counts = {s: 0 for s in rules.APPLICATION_STATUSES}
    for stage, n in (db.session.query(Application.status, db.func.count(Application.id))
                     .filter(Application.vacancy_id == vacancy.id)
                     .group_by(Application.status).all()):
        counts[stage] = n
    total = sum(counts.values())

    query = (Application.query.filter(Application.vacancy_id == vacancy.id)
             .join(User, Application.applicant_id == User.id))
    if status:
        query = query.filter(Application.status == status)
    if term:
        like = f"%{term}%"
        query = query.filter(db.or_(User.name.ilike(like), User.email.ilike(like)))
    if sort == "oldest":
        query = query.order_by(Application.created_at.asc())
    elif sort == "name":
        query = query.order_by(db.func.lower(User.name), Application.created_at.desc())
    elif sort == "status":
        rank = db.case(*[(Application.status == s, i) for i, s in enumerate(rules.APPLICATION_STATUSES)],
                       else_=len(rules.APPLICATION_STATUSES))
        query = query.order_by(rank, Application.created_at.desc())
    else:
        query = query.order_by(Application.created_at.desc())

    pagination = query.paginate(page=page, per_page=rules.PAGE_SIZE, error_out=False)
    return render_template(
        "applicants.html", vacancy=vacancy, pagination=pagination, counts=counts, total=total,
        status=status, sort=sort, q=term, stages=rules.APPLICATION_STATUSES, sorts=rules.SORTS,
        can_edit=current_user.role == "recruiter",
    )
