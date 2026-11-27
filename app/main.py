from pathlib import Path
from functools import wraps
from uuid import uuid4
from flask import Blueprint,render_template,request,redirect,url_for,flash,current_app,send_from_directory,abort,jsonify
from flask_login import login_required,current_user
from werkzeug.utils import secure_filename
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from app import db
from app.application_rules import MAX_STATUS_NOTE_LENGTH, STATUS_TRANSITIONS, is_withdrawable, validate_status_change
from app.csrf import csrf_protect
from app.models import Vacancy,User,Application,Employer,StatusEvent
main_bp=Blueprint("main",__name__)
def role_required(*roles):
    def deco(fn):
        @wraps(fn)
        @login_required
        def wrapped(*a,**kw):
            if current_user.role not in roles: abort(403)
            return fn(*a,**kw)
        return wrapped
    return deco
@main_bp.route("/")
def home():
    vacancies=Vacancy.public_query().order_by(Vacancy.created_at.desc()).limit(3).all()
    return render_template("home.html",vacancies=vacancies)
@main_bp.route("/jobs")
def jobs():
    # F5: server-side search + filters (the page also filters live in the browser, see static/js/jobs.js)
    q=request.args.get("q","").strip()[:100]; location=request.args.get("location","").strip()
    job_type=request.args.get("type","").strip(); sort=request.args.get("sort","newest")
    if sort not in ("newest","closing"): sort="newest"
    everything=Vacancy.public_query().all()   # used only to build the filter drop-downs
    locations=sorted({v.location for v in everything if v.location}); job_types=sorted({v.job_type for v in everything if v.job_type})
    query=Vacancy.public_query()
    if q:
        like=f"%{q}%"; query=query.filter(db.or_(Vacancy.title.ilike(like),Vacancy.location.ilike(like),Vacancy.description.ilike(like),Employer.name.ilike(like)))
    if location: query=query.filter(Vacancy.location==location)
    if job_type: query=query.filter(Vacancy.job_type==job_type)
    if sort=="closing": query=query.order_by(Vacancy.closing_date.is_(None),Vacancy.closing_date.asc(),Vacancy.created_at.desc())
    else: query=query.order_by(Vacancy.created_at.desc())
    return render_template("jobs.html",vacancies=query.all(),q=q,location=location,job_type=job_type,sort=sort,locations=locations,job_types=job_types)
@main_bp.route("/jobs/<int:vid>")
def vacancy_detail(vid):
    # F6: public may see open AND closed vacancies of verified employers (closed ones show a closing banner);
    # drafts / hidden / removed / unverified-employer vacancies are 404 except to that employer's staff and admins (R1, R6).
    v=db.get_or_404(Vacancy,vid)
    if v.status=="removed": abort(404)
    staff=current_user.is_authenticated and (current_user.role=="admin" or (current_user.role in ("recruiter","reviewer") and current_user.employer_id==v.employer_id))
    public=v.status in ("open","closed") and v.employer.status=="verified"
    if not public and not staff: abort(404)
    application=None
    if current_user.is_authenticated and current_user.role=="applicant":
        application=Application.query.filter_by(vacancy_id=v.id,applicant_id=current_user.id).first()
    return render_template("vacancy_detail.html",vacancy=v,state=v.effective_status,staff=staff,application=application)
@main_bp.route("/dashboard")
@login_required
def dashboard():
    vacancies=[]
    applications=[]
    if current_user.role=="recruiter" and current_user.employer_id:
        vacancies=Vacancy.query.filter_by(employer_id=current_user.employer_id).filter(Vacancy.status!="removed").all()
    elif current_user.role=="admin": vacancies=Vacancy.query.filter(Vacancy.status!="removed").all()
    elif current_user.role=="applicant":
        applications=(Application.query.filter_by(applicant_id=current_user.id)
                      .order_by(Application.created_at.desc()).all())
    timelines = {application.id: [] for application in applications}
    if timelines:
        events = (StatusEvent.query.filter(StatusEvent.application_id.in_(timelines))
                  .order_by(StatusEvent.created_at.asc(), StatusEvent.id.asc()).all())
        for event in events:
            timelines[event.application_id].append(event)
    return render_template("dashboard.html",vacancies=vacancies,applications=applications,
                           status_transitions=STATUS_TRANSITIONS, timelines=timelines)


@main_bp.route("/jobs/<int:vid>/apply", methods=["POST"])
@role_required("applicant")
def apply(vid):
    csrf_protect()
    vacancy = db.get_or_404(Vacancy, vid)
    if vacancy.effective_status != "open" or vacancy.employer.status != "verified":
        flash("This vacancy is not accepting applications.", "error")
        return redirect(url_for("main.vacancy_detail", vid=vid))

    cv_filename = current_user.cv_filename
    cv_path = Path(current_app.config["UPLOAD_FOLDER"]) / (cv_filename or "")
    if not cv_filename or Path(cv_filename).name != cv_filename or not cv_path.is_file():
        flash("Upload a CV to your profile before applying.", "error")
        return redirect(url_for("main.profile"))

    existing = Application.query.filter_by(vacancy_id=vid, applicant_id=current_user.id).first()
    if existing:
        flash("You have already applied for this vacancy.", "error")
        return redirect(url_for("main.vacancy_detail", vid=vid))

    application = Application(vacancy_id=vid, applicant_id=current_user.id)
    db.session.add(application)
    db.session.flush()
    db.session.add(StatusEvent(
        application_id=application.id, from_status=None, to_status="Submitted",
        note="Application submitted.", created_by_id=current_user.id,
    ))
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        flash("You have already applied for this vacancy.", "error")
        return redirect(url_for("main.vacancy_detail", vid=vid))

    flash("Your application has been submitted.", "success")
    return redirect(url_for("main.dashboard"))


@main_bp.route("/applications/<int:aid>/status", methods=["POST"])
@role_required("recruiter")
def update_application_status(aid):
    csrf_protect()
    if not request.is_json:
        return jsonify(error="Send this update as a JSON request."), 415
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify(error="Invalid JSON request."), 400

    application = db.get_or_404(Application, aid)
    if not current_user.employer_id or application.vacancy.employer_id != current_user.employer_id:
        abort(403)

    next_status = payload.get("status")
    note = payload.get("note", "")
    error = validate_status_change(application.status, next_status, note)
    if error:
        return jsonify(error=error), 400

    previous_status = application.status
    application.status = next_status
    db.session.add(StatusEvent(
        application_id=application.id, from_status=previous_status,
        to_status=next_status, note=note.strip(), created_by_id=current_user.id,
    ))
    db.session.commit()
    return jsonify(application_id=application.id, status=application.status,
                   note=note.strip()), 200


@main_bp.route("/applications/<int:aid>/withdraw", methods=["POST"])
@role_required("applicant")
def withdraw_application(aid):
    csrf_protect()
    application = db.get_or_404(Application, aid)
    if application.applicant_id != current_user.id:
        abort(403)
    if not is_withdrawable(application.status):
        flash("This application can no longer be withdrawn.", "error")
        return redirect(url_for("main.dashboard"))

    note = (request.form.get("note") or "").strip()
    if len(note) > MAX_STATUS_NOTE_LENGTH:
        flash(f"The withdrawal note must be at most {MAX_STATUS_NOTE_LENGTH} characters.", "error")
        return redirect(url_for("main.dashboard"))

    previous_status = application.status
    application.status = "Withdrawn"
    db.session.add(StatusEvent(
        application_id=application.id, from_status=previous_status,
        to_status="Withdrawn", note=note or "Application withdrawn by applicant.",
        created_by_id=current_user.id,
    ))
    db.session.commit()
    flash("Your application has been withdrawn.", "success")
    return redirect(url_for("main.dashboard"))


@main_bp.route("/applications/<int:aid>/cv")
@role_required("recruiter", "reviewer", "admin")
def application_cv(aid):
    application = db.get_or_404(Application, aid)
    if current_user.role != "admin" and (
            not current_user.employer_id or application.vacancy.employer_id != current_user.employer_id):
        abort(403)
    filename = application.applicant.cv_filename
    if not filename or Path(filename).name != filename:
        abort(404)
    path = Path(current_app.config["UPLOAD_FOLDER"]) / filename
    if not path.is_file():
        abort(404)
    return send_from_directory(current_app.config["UPLOAD_FOLDER"], filename, as_attachment=True)


def _reserve_cv_upload(user_id):
    result = db.session.execute(
        update(User).where(User.id == user_id).values(
            cv_upload_version=User.cv_upload_version + 1
        )
    )
    if result.rowcount != 1:
        db.session.rollback()
        return None
    generation = db.session.execute(
        select(User.cv_upload_version).where(User.id == user_id)
    ).scalar_one()
    db.session.commit()
    return generation


def _activate_cv_upload(user_id, generation, filename):
    previous_filename = db.session.execute(
        select(User.cv_filename).where(User.id == user_id)
    ).scalar_one()
    result = db.session.execute(
        update(User).where(
            User.id == user_id,
            User.cv_upload_version == generation,
        ).values(cv_filename=filename)
    )
    if result.rowcount != 1:
        db.session.rollback()
        return False, None
    db.session.commit()
    return True, previous_filename


def _remove_cv_file(filename):
    if not filename or Path(filename).name != filename:
        return
    path = Path(current_app.config["UPLOAD_FOLDER"]) / filename
    try:
        path.unlink(missing_ok=True)
    except OSError:
        current_app.logger.exception("Unable to remove obsolete CV file %s", filename)


@main_bp.route("/profile",methods=["GET","POST"])
@role_required("applicant")
def profile():
    if request.method=="POST":
        try:
            generation = _reserve_cv_upload(current_user.id)
        except SQLAlchemyError:
            db.session.rollback()
            current_app.logger.exception("Unable to reserve CV upload for user %s", current_user.id)
            flash("The CV upload could not be started. Please try again.", "error")
            return redirect(url_for("main.profile"))
        if generation is None:
            flash("The CV upload could not be started. Please try again.", "error")
            return redirect(url_for("main.profile"))

        f=request.files.get("cv")
        if f and f.filename:
            name=secure_filename(f.filename); ext=name.rsplit(".",1)[-1].lower() if "." in name else ""
            if ext not in {"pdf","doc","docx"}: flash("Upload a PDF, DOC or DOCX file.","error")
            else:
                stored=f"user_{current_user.id}_{uuid4().hex}.{ext}"
                upload_folder=Path(current_app.config["UPLOAD_FOLDER"])
                try:
                    f.save(upload_folder/stored)
                except OSError:
                    current_app.logger.exception("Unable to save CV for user %s", current_user.id)
                    _remove_cv_file(stored)
                    flash("The CV could not be saved. Please try again.", "error")
                    return redirect(url_for("main.profile"))
                try:
                    activated, previous_filename = _activate_cv_upload(current_user.id, generation, stored)
                except SQLAlchemyError:
                    db.session.rollback()
                    current_app.logger.exception("Unable to activate CV for user %s", current_user.id)
                    _remove_cv_file(stored)
                    flash("The CV could not be saved. Please try again.", "error")
                    return redirect(url_for("main.profile"))
                if not activated:
                    _remove_cv_file(stored)
                    flash("A newer CV upload is already in progress. This older upload was discarded.", "error")
                    return redirect(url_for("main.profile"))
                _remove_cv_file(previous_filename)
                flash("CV uploaded to private storage.", "success")
        return redirect(url_for("main.profile"))
    return render_template("profile.html")
@main_bp.route("/private-cv/<int:uid>")
@login_required
def private_cv(uid):
    if current_user.id!=uid and current_user.role!="admin": abort(403)
    u=User.query.get_or_404(uid)
    if not u.cv_filename: abort(404)
    return send_from_directory(current_app.config["UPLOAD_FOLDER"],u.cv_filename,as_attachment=True)
@main_bp.app_errorhandler(403)
def forbidden(e): return render_template("403.html"),403
