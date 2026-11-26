from datetime import datetime, date
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
from app import db, login_manager
from app import vacancy_rules as rules
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
    cv_upload_version=db.Column(db.Integer,nullable=False,default=0)
    created_at=db.Column(db.DateTime,default=datetime.utcnow)
    def set_password(self,p): self.password_hash=generate_password_hash(p)
    def check_password(self,p): return check_password_hash(self.password_hash,p)
class Vacancy(db.Model):
    id=db.Column(db.Integer,primary_key=True); employer_id=db.Column(db.Integer,db.ForeignKey("employer.id"),nullable=False)
    title=db.Column(db.String(140),nullable=False); location=db.Column(db.String(120),default="")
    job_type=db.Column(db.String(60),default="Full-time"); description=db.Column(db.Text,nullable=False)
    status=db.Column(db.String(20),default="draft"); created_at=db.Column(db.DateTime,default=datetime.utcnow)
    # --- added for F4/F5/F6 (J) ---
    version=db.Column(db.Integer,nullable=False,default=1)  # optimistic locking: stops a delayed/old save overwriting a newer one
    __mapper_args__={"version_id_col":version}              # SQLAlchemy bumps it on every UPDATE and detects races
    closing_date=db.Column(db.Date)  # R2; statuses: draft / open / closed (hidden / removed are set by admin moderation)
    removal_reason=db.Column(db.Text)
    removed_at=db.Column(db.DateTime)
    @classmethod
    def public_query(cls,today=None):
        """Vacancies any visitor may see in listings: open, employer verified (R6), not past closing date (R2)."""
        today=today or date.today()
        return cls.query.join(Employer,cls.employer_id==Employer.id).filter(
            cls.status=="open",Employer.status=="verified",db.or_(cls.closing_date.is_(None),cls.closing_date>=today))
    @property
    def effective_status(self): return rules.effective_status(self.status,self.closing_date)
    @property
    def is_open(self): return self.effective_status=="open" and self.employer.status=="verified"
    @property
    def days_left(self):
        return None if self.closing_date is None else (self.closing_date-date.today()).days
class Application(db.Model):
    """Minimal application record so vacancy counts / the applicant list (F9) work.
    H owns the full application workflow (apply, status changes, history) and may extend this class."""
    __table_args__=(db.UniqueConstraint("vacancy_id","applicant_id",name="uq_one_application_per_vacancy"),)  # R3
    id=db.Column(db.Integer,primary_key=True) 
    vacancy_id=db.Column(db.Integer,db.ForeignKey("vacancy.id"),nullable=False)
    applicant_id=db.Column(db.Integer,db.ForeignKey("user.id"),nullable=False)
    status=db.Column(db.String(30),nullable=False,default="Submitted"); created_at=db.Column(db.DateTime,default=datetime.utcnow)
    vacancy=db.relationship("Vacancy",backref=db.backref("applications",lazy=True))
    applicant=db.relationship("User",backref=db.backref("applications",lazy=True))

class Report(db.Model):
    id=db.Column(db.Integer,primary_key=True)
    reporter_id=db.Column(db.Integer,db.ForeignKey("user.id"),nullable=False)
    vacancy_id=db.Column(db.Integer,db.ForeignKey("vacancy.id"))
    employer_id=db.Column(db.Integer,db.ForeignKey("employer.id"))
    reason=db.Column(db.String(80),nullable=False)
    details=db.Column(db.Text,default="")
    status=db.Column(db.String(20),nullable=False,default="open")
    created_at=db.Column(db.DateTime,default=datetime.utcnow)
    reporter=db.relationship("User",backref="reports")
    vacancy=db.relationship("Vacancy",backref="reports")
    employer=db.relationship("Employer",backref="reports")

class ReviewerFeedback(db.Model):
    id=db.Column(db.Integer,primary_key=True)
    application_id=db.Column(db.Integer,db.ForeignKey("application.id"),nullable=False)
    reviewer_id=db.Column(db.Integer,db.ForeignKey("user.id"),nullable=False)
    comments=db.Column(db.Text,nullable=False)
    recommendation=db.Column(db.String(30),nullable=False,default="No recommendation")
    created_at=db.Column(db.DateTime,default=datetime.utcnow)
    application=db.relationship("Application",backref=db.backref("feedback",lazy=True))
    reviewer=db.relationship("User",backref="reviewer_feedback")

class ModerationAction(db.Model):
    id=db.Column(db.Integer,primary_key=True)
    moderator_id=db.Column(db.Integer,db.ForeignKey("user.id"),nullable=False)
    target_type=db.Column(db.String(20),nullable=False)
    target_id=db.Column(db.Integer,nullable=False)
    action=db.Column(db.String(30),nullable=False)
    reason=db.Column(db.Text,default="")
    created_at=db.Column(db.DateTime,default=datetime.utcnow)
    moderator=db.relationship("User",backref="moderation_actions")

class DecisionTemplate(db.Model):
    id=db.Column(db.Integer,primary_key=True)
    name=db.Column(db.String(100),nullable=False)
    subject=db.Column(db.String(150),nullable=False)
    body=db.Column(db.Text,nullable=False)
    created_at=db.Column(db.DateTime,default=datetime.utcnow)

class StatusEvent(db.Model):
    id=db.Column(db.Integer,primary_key=True)
    application_id=db.Column(db.Integer,db.ForeignKey("application.id"),nullable=False)
    from_status=db.Column(db.String(30))
    to_status=db.Column(db.String(30),nullable=False)
    note=db.Column(db.Text,default="")
    created_by_id=db.Column(db.Integer,db.ForeignKey("user.id"),nullable=False)
    created_at=db.Column(db.DateTime,default=datetime.utcnow)
    application=db.relationship("Application",backref=db.backref("status_events",lazy=True))
    created_by=db.relationship("User",backref="status_events")

# Descriptive aliases for feature terminology used in the moderation workstream.
ModerationReport = Report
ReviewFeedback = ReviewerFeedback
@login_manager.user_loader
def load_user(uid): return db.session.get(User,int(uid))
