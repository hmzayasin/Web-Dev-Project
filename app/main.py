from pathlib import Path
from functools import wraps
from flask import Blueprint,render_template,request,redirect,url_for,flash,current_app,send_from_directory,abort
from flask_login import login_required,current_user
from werkzeug.utils import secure_filename
from app import db
from app.models import Vacancy,User
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
    vacancies=Vacancy.query.filter_by(status="open").limit(3).all()
    return render_template("home.html",vacancies=vacancies)
@main_bp.route("/jobs")
def jobs():
    q=request.args.get("q","").strip(); query=Vacancy.query.filter_by(status="open")
    if q:
        like=f"%{q}%"; query=query.filter(db.or_(Vacancy.title.ilike(like),Vacancy.location.ilike(like),Vacancy.description.ilike(like)))
    return render_template("jobs.html",vacancies=query.all(),q=q)
@main_bp.route("/jobs/<int:vid>")
def vacancy_detail(vid):
    v=Vacancy.query.get_or_404(vid)
    if v.status!="open": abort(404)
    return render_template("vacancy_detail.html",vacancy=v)
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
