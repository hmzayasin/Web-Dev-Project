from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from pathlib import Path
from config import Config
db = SQLAlchemy()
login_manager = LoginManager()
login_manager.login_view = "auth.login"
def create_app(test_config=None):
    app = Flask(__name__)
    app.config.from_object(Config)
    if test_config: app.config.update(test_config)
    Path(app.config["UPLOAD_FOLDER"]).mkdir(exist_ok=True)
    Path(app.instance_path).mkdir(exist_ok=True)
    db.init_app(app); login_manager.init_app(app)
    from app.models import User, Employer, Vacancy
    from app.csrf import init_csrf
    from app.vacancies import vacancies_bp
    init_csrf(app)
    from app.auth import auth_bp
    from app.main import main_bp
    from app.moderation import moderation_bp
    from app.saved import saved_bp, init_saved
    app.register_blueprint(main_bp); app.register_blueprint(auth_bp); app.register_blueprint(vacancies_bp)
    app.register_blueprint(moderation_bp)
    app.register_blueprint(saved_bp); init_saved(app)
    with app.app_context():
        db.create_all()
        from app.schema_migrations import upgrade_schema
        upgrade_schema(db.engine)
        if not User.query.first():
            employer = Employer(name="Northstar Technologies", description="A growing technology team.", status="verified")
            db.session.add(employer); db.session.flush()
            demo = [
                User(name="Demo Applicant", email="applicant@inrole.demo", role="applicant"),
                User(name="Demo Recruiter", email="recruiter@inrole.demo", role="recruiter", employer_id=employer.id),
                User(name="Demo Reviewer", email="reviewer@inrole.demo", role="reviewer", employer_id=employer.id),
                User(name="Demo Administrator", email="admin@inrole.demo", role="admin")]
            for u in demo: u.set_password("InRole123!"); db.session.add(u)
            db.session.flush()
            db.session.add_all([
                Vacancy(employer_id=employer.id,title="Graduate Software Developer",location="Dublin / Hybrid",job_type="Graduate",description="Build reliable web applications with a collaborative engineering team.",status="open"),
                Vacancy(employer_id=employer.id,title="Junior Data Analyst",location="Dublin",job_type="Full-time",description="Turn data into useful insights and support better decisions.",status="open"),
                Vacancy(employer_id=employer.id,title="Frontend Developer Intern",location="Remote",job_type="Internship",description="Help create accessible and engaging user experiences.",status="open")])
            db.session.commit()
        from app.seed_vacancies import seed_vacancies
        seed_vacancies()
    return app
