from flask import Blueprint,render_template,redirect,url_for,flash,request
from flask_login import login_user,logout_user,current_user
from app import db
from app.models import User,Employer
auth_bp=Blueprint("auth",__name__,url_prefix="/auth")
@auth_bp.route("/login",methods=["GET","POST"])
def login():
    if current_user.is_authenticated:return redirect(url_for("main.dashboard"))
    if request.method=="POST":
        u=User.query.filter_by(email=request.form.get("email","").strip().lower()).first()
        if u and u.check_password(request.form.get("password","")):
            login_user(u); flash("Welcome back.","success"); return redirect(url_for("main.dashboard"))
        flash("Email or password was incorrect.","error")
    return render_template("login.html")
@auth_bp.route("/register",methods=["GET","POST"])
def register():
    if current_user.is_authenticated:return redirect(url_for("main.dashboard"))
    if request.method=="POST":
        name=request.form.get("name","").strip(); email=request.form.get("email","").strip().lower()
        password=request.form.get("password",""); role=request.form.get("role","applicant")
        if role not in ("applicant","recruiter"): role="applicant"
        if not name or not email or len(password)<8: flash("Enter your details and a password of at least 8 characters.","error")
        elif User.query.filter_by(email=email).first(): flash("That email is already registered.","error")
        else:
            employer=None
            if role=="recruiter":
                employer=Employer(name=f"{name}'s organisation",status="pending"); db.session.add(employer); db.session.flush()
            u=User(name=name,email=email,role=role,employer_id=employer.id if employer else None); u.set_password(password)
            db.session.add(u); db.session.commit(); login_user(u)
            flash("Account created. Recruiter organisations require admin verification.","success")
            return redirect(url_for("main.dashboard"))
    return render_template("register.html")
@auth_bp.route("/logout")
def logout():
    logout_user(); return redirect(url_for("main.home"))
