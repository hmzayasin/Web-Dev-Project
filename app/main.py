from pathlib import Path
from functools import wraps
from uuid import uuid4
from flask import Blueprint,render_template,request,redirect,url_for,flash,current_app,send_from_directory,abort
from flask_login import login_required,current_user
from werkzeug.utils import secure_filename
from sqlalchemy import select, update
from sqlalchemy.exc import SQLAlchemyError
from app import db
from app.models import Vacancy,User,Application,Employer
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
    if current_user.role=="recruiter" and current_user.employer_id:
        vacancies=Vacancy.query.filter_by(employer_id=current_user.employer_id).filter(Vacancy.status!="removed").all()
    elif current_user.role=="admin": vacancies=Vacancy.query.filter(Vacancy.status!="removed").all()
    return render_template("dashboard.html",vacancies=vacancies)


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
def can_view_cv(viewer,applicant_id):
    """R8: a CV is private. Only its owner, an admin, or staff (recruiter/reviewer) of an employer
    the applicant has applied to may open it."""
    if viewer.id==applicant_id or viewer.role=="admin": return True
    if viewer.role in ("recruiter","reviewer") and viewer.employer_id:
        return db.session.query(Application.id).join(Vacancy,Application.vacancy_id==Vacancy.id).filter(
            Application.applicant_id==applicant_id,Vacancy.employer_id==viewer.employer_id).first() is not None
    return False
@main_bp.route("/private-cv/<int:uid>")
@login_required
def private_cv(uid):
    if not can_view_cv(current_user,uid): abort(403)   # check permission first so user ids can't be probed
    u=db.get_or_404(User,uid)
    if not u.cv_filename: abort(404)
    response=send_from_directory(current_app.config["UPLOAD_FOLDER"],u.cv_filename,as_attachment=True)
    response.headers["Cache-Control"]="private, no-store"   # don't leave personal data in shared caches
    return response
@main_bp.app_errorhandler(403)
def forbidden(e): return render_template("403.html"),403
@main_bp.app_errorhandler(404)
def not_found(e): return render_template("error.html",code=404,title="We couldn't find that page.",message="The link may be out of date, or the vacancy may have been closed or removed."),404
@main_bp.app_errorhandler(413)
def too_large(e): return render_template("error.html",code=413,title="That file is too large.",message="CVs can be up to 5 MB. Please choose a smaller PDF, DOC or DOCX file."),413
@main_bp.app_errorhandler(400)
def bad_request(e): return render_template("error.html",code=400,title="That request couldn't be processed.",message=getattr(e,"description",None) or "Please go back, reload the page and try again."),400
