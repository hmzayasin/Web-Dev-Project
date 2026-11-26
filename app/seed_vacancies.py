"""Extra demo data for J's slice (runs once, after the starter seed in create_app).

Gives you something to click through straight away:
  * Northstar (verified): open vacancies with closing dates, one DRAFT, one CLOSED,
    one OPEN-but-deadline-passed (R2) -> only the open ones appear on /jobs
  * Harbour Digital (PENDING employer): its "open" vacancy stays hidden (R6)
  * 14 demo applicants with applications in every stage -> pagination / filters / counts (F9)
Demo logins (all use password InRole123!):
  recruiter@inrole.demo   reviewer@inrole.demo   pending.recruiter@inrole.demo
"""
from datetime import date, datetime, timedelta

from werkzeug.security import generate_password_hash

from app import db
from app.models import Application, Employer, User, Vacancy

MARKER_EMAIL = "candidate01@inrole.demo"
NAMES = ["Aoife Murphy", "Liam Chen", "Sofia Rossi", "Noah Patel", "Emma Walsh", "Oliver Byrne",
         "Mia Kowalski", "Jack Doyle", "Isla Nguyen", "Conor Ryan", "Zara Ahmed", "Finn O'Brien",
         "Chloe Martin", "Dara Kelly"]
STATUSES = ["Submitted", "Under review", "Shortlisted", "Interview", "Offer", "Submitted", "Under review",
            "Rejected", "Submitted", "Shortlisted", "Withdrawn", "Under review", "Submitted", "Interview"]


def seed_vacancies():
    if User.query.filter_by(email=MARKER_EMAIL).first():
        return  # already seeded
    north = Employer.query.filter_by(name="Northstar Technologies").first()
    if north is None:
        return
    today, now = date.today(), datetime.utcnow()
    password_hash = generate_password_hash("InRole123!")  # hash once, not once per demo user

    # closing dates for the three starter vacancies
    starters = Vacancy.query.filter_by(employer_id=north.id, status="open").order_by(Vacancy.id).limit(3).all()
    for vacancy, days in zip(starters, (21, 30, 9)):
        if vacancy.closing_date is None:
            vacancy.closing_date = today + timedelta(days=days)

    def vac(employer, title, location, job_type, status, closing_offset, description):
        v = Vacancy(employer_id=employer.id, title=title, location=location, job_type=job_type,
                    status=status, closing_date=today + timedelta(days=closing_offset),
                    description=description, created_at=now - timedelta(days=abs(closing_offset) % 9 + 1))
        db.session.add(v)
        return v

    vac(north, "Backend Engineer (Python)", "Dublin / Hybrid", "Full-time", "open", 14,
        "Design and build Flask and SQL services used by thousands of applicants every week.\n\nYou will own features end to end, review code and help us keep the platform fast and secure.")
    vac(north, "UX Research Assistant", "Remote", "Part-time", "draft", 40,
        "Draft listing: help the design team run usability sessions and summarise what we learn.")
    vac(north, "Customer Success Associate", "Dublin", "Full-time", "closed", -5,
        "This role has been filled and is no longer accepting applications.")
    vac(north, "Marketing Intern", "Cork", "Internship", "open", -1,
        "Deadline passed yesterday: shows how R2 treats an open vacancy past its closing date as closed.")

    harbour = Employer(name="Harbour Digital", description="Awaiting verification.", status="pending")
    db.session.add(harbour)
    db.session.flush()
    db.session.add(User(name="Pending Recruiter", email="pending.recruiter@inrole.demo", role="recruiter",
                        employer_id=harbour.id, password_hash=password_hash))
    vac(harbour, "Sales Trainee", "Galway", "Graduate", "open", 20,
        "Hidden from the public listing because this employer is not verified yet (R6).")

    candidates = []
    for i, name in enumerate(NAMES, start=1):
        user = User(name=name, email=f"candidate{i:02d}@inrole.demo", role="applicant", password_hash=password_hash)
        if i % 3 == 0:
            user.cv_filename = f"demo_cv_{i:02d}.pdf"
        db.session.add(user)
        candidates.append(user)
    db.session.flush()

    first = Vacancy.query.filter_by(employer_id=north.id, title="Graduate Software Developer").first()
    second = Vacancy.query.filter_by(employer_id=north.id, title="Junior Data Analyst").first()
    third = Vacancy.query.filter_by(employer_id=north.id, title="Frontend Developer Intern").first()
    if first:
        for i, (user, status) in enumerate(zip(candidates, STATUSES)):
            db.session.add(Application(vacancy_id=first.id, applicant_id=user.id, status=status,
                                       created_at=now - timedelta(hours=7 * i + 2)))
    if second:
        for i, user in enumerate(candidates[:3]):
            db.session.add(Application(vacancy_id=second.id, applicant_id=user.id,
                                       status=["Submitted", "Under review", "Rejected"][i],
                                       created_at=now - timedelta(hours=11 * i + 5)))
    demo_applicant = User.query.filter_by(email="applicant@inrole.demo").first()
    if third and demo_applicant:
        db.session.add(Application(vacancy_id=third.id, applicant_id=demo_applicant.id,
                                   status="Shortlisted", created_at=now - timedelta(days=2)))
    db.session.commit()
