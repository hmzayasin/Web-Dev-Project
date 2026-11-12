from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
from app import db, login_manager
class Employer(db.Model):
    id=db.Column(db.Integer,primary_key=True); name=db.Column(db.String(120),nullable=False)
    description=db.Column(db.Text,default=""); status=db.Column(db.String(20),default="pending")
    users=db.relationship("User",backref="employer",lazy=True)
    vacancies=db.relationship("Vacancy",backref="employer",lazy=True)
class User(UserMixin,db.Model):
    id=db.Column(db.Integer,primary_key=True); name=db.Column(db.String(100),nullable=False)
    email=db.Column(db.String(150),unique=True,nullable=False); password_hash=db.Column(db.String(255),nullable=False)
    role=db.Column(db.String(20),nullable=False,default="applicant")
    employer_id=db.Column(db.Integer,db.ForeignKey("employer.id")); cv_filename=db.Column(db.String(255))
    created_at=db.Column(db.DateTime,default=datetime.utcnow)
    def set_password(self,p): self.password_hash=generate_password_hash(p)
    def check_password(self,p): return check_password_hash(self.password_hash,p)
class Vacancy(db.Model):
    id=db.Column(db.Integer,primary_key=True); employer_id=db.Column(db.Integer,db.ForeignKey("employer.id"),nullable=False)
    title=db.Column(db.String(140),nullable=False); location=db.Column(db.String(120),default="")
    job_type=db.Column(db.String(60),default="Full-time"); description=db.Column(db.Text,nullable=False)
    status=db.Column(db.String(20),default="draft"); created_at=db.Column(db.DateTime,default=datetime.utcnow)
@login_manager.user_loader
def load_user(uid): return db.session.get(User,int(uid))
