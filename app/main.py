from pathlib import Path
from functools import wraps
from flask import Blueprint,render_template,request,redirect,url_for,flash,current_app,send_from_directory,abort
from flask_login import login_required,current_user
from werkzeug.utils import secure_filename
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
    if current_user.role=="recruiter" and current_user.employer_id: vacancies=Vacancy.query.filter_by(employer_id=current_user.employer_id).all()
    elif current_user.role=="admin": vacancies=Vacancy.query.all()
    return render_template("dashboard.html",vacancies=vacancies)
@main_bp.route("/profile",methods=["GET","POST"])
@role_required("applicant")
def profile():
    if request.method=="POST":
        f=request.files.get("cv")
        if f and f.filename:
            name=secure_filename(f.filename); ext=name.rsplit(".",1)[-1].lower() if "." in name else ""
            if ext not in {"pdf","doc","docx"}: flash("Upload a PDF, DOC or DOCX file.","error")
            else:
                stored=f"user_{current_user.id}_{name}"; f.save(Path(current_app.config["UPLOAD_FOLDER"])/stored)
                current_user.cv_filename=stored; db.session.commit(); flash("CV uploaded to private storage.","success")
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
