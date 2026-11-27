from app import db
from app.models import (
    Application, DecisionTemplate, Employer, ModerationAction, Report,
    ReviewerFeedback, StatusEvent, Vacancy,
)

from .conftest import login, logout, post


def vacancy_id(app, title):
    with app.app_context():
        return Vacancy.query.filter_by(title=title).one().id


def test_moderation_queue_requires_admin(client):
    assert client.get("/moderation").status_code == 302
    login(client, "reviewer@inrole.demo")
    assert client.get("/moderation").status_code == 403
    logout(client)
    login(client, "admin@inrole.demo")
    assert client.get("/moderation").status_code == 200


def test_moderation_queue_highlights_selected_dismissed_tab(client):
    login(client, "admin@inrole.demo")
    response = client.get("/moderation?status=dismissed")
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert 'class="btn small" href="/moderation?status=dismissed" aria-current="page"' in html


def test_applicant_can_report_vacancy(app, client):
    vid = vacancy_id(app, "Graduate Software Developer")
    login(client, "applicant@inrole.demo")
    assert client.get(f"/jobs/{vid}/report").status_code == 200
    response = post(client, f"/jobs/{vid}/report", {
        "reason": "Misleading information",
        "details": "The salary and role description do not match.",
    })
    assert response.status_code == 302
    with app.app_context():
        report = Report.query.filter_by(vacancy_id=vid).one()
        assert report.reason == "Misleading information"
        assert report.status == "open"


def test_applicant_can_report_employer(app, client):
    login(client, "applicant@inrole.demo")
    with app.app_context():
        employer_id = Employer.query.filter_by(name="Northstar Technologies").one().id
    response = post(client, f"/employers/{employer_id}/report", {
        "reason": "Scam or fraud",
        "details": "The employer requested payment.",
    })
    assert response.status_code == 302
    with app.app_context():
        assert Report.query.filter_by(employer_id=employer_id).one().reason == "Scam or fraud"


def test_removed_vacancy_disappears_from_operational_views(app, client):
    vid = vacancy_id(app, "Graduate Software Developer")
    login(client, "admin@inrole.demo")
    post(client, f"/moderation/vacancy/{vid}/hide")
    with app.app_context():
        assert db.session.get(Vacancy, vid).status == "hidden"
    assert "Graduate Software Developer" in client.get("/moderation").get_data(as_text=True)

    post(client, f"/moderation/vacancy/{vid}/remove", {"reason": "Verified as misleading"})
    with app.app_context():
        vacancy = db.session.get(Vacancy, vid)
        assert vacancy.status == "removed"
        assert vacancy.removal_reason == "Verified as misleading"
        for application in Application.query.filter_by(vacancy_id=vid).all():
            assert application.status in ("Rejected", "Withdrawn", "Vacancy withdrawn")

        assert ModerationAction.query.filter_by(target_type="vacancy", target_id=vid).count() == 2

    assert "Graduate Software Developer" not in client.get("/moderation").get_data(as_text=True)
    assert "Graduate Software Developer" not in client.get("/manage/vacancies/").get_data(as_text=True)
    assert "Graduate Software Developer" not in client.get("/dashboard").get_data(as_text=True)
    assert client.get(f"/jobs/{vid}").status_code == 404

    post(client, f"/moderation/vacancy/{vid}/restore")
    with app.app_context():
        assert db.session.get(Vacancy, vid).status == "removed"


def test_removal_withdraws_active_applications_and_keeps_terminal(app, client):
    vid = vacancy_id(app, "Graduate Software Developer")
    login(client, "admin@inrole.demo")
    post(client, f"/moderation/vacancy/{vid}/remove", {"reason": "Vacancy removed"})
    with app.app_context():
        applications = Application.query.filter_by(vacancy_id=vid).all()
        changed = [a for a in applications if a.status == "Vacancy withdrawn"]
        assert changed
        assert all(a.status != "Vacancy withdrawn" or
                   StatusEvent.query.filter_by(application_id=a.id, to_status="Vacancy withdrawn").count() >= 1
                   for a in applications)


def test_admin_verify_and_suspend_employer(app, client):
    login(client, "admin@inrole.demo")
    with app.app_context():
        employer = Employer.query.filter_by(name="Harbour Digital").one()
        employer_id = employer.id
    post(client, f"/moderation/employer/{employer_id}/verify")
    with app.app_context():
        assert db.session.get(Employer, employer_id).status == "verified"

    post(client, f"/moderation/employer/{employer_id}/suspend")
    with app.app_context():
        assert db.session.get(Employer, employer_id).status == "suspended"
        assert Vacancy.query.filter_by(employer_id=employer_id).first().status == "hidden"


def test_reviewer_feedback_is_scoped_to_owner_and_persisted(app, client):
    vid = vacancy_id(app, "Graduate Software Developer")
    login(client, "reviewer@inrole.demo")
    with app.app_context():
        application = Application.query.filter_by(vacancy_id=vid).first()
        aid = application.id

    assert post(client, f"/applications/{aid}/feedback", {
        "comments": "Strong relevant experience and clear examples.",
        "recommendation": "Proceed",
    }).status_code == 302
    with app.app_context():
        feedback = ReviewerFeedback.query.filter_by(application_id=aid).one()
        assert feedback.recommendation == "Proceed"

    logout(client)
    login(client, "applicant@inrole.demo")
    assert client.get(f"/applications/{aid}/feedback").status_code == 403


def test_admin_report_resolution_and_decision_template(app, client):
    vid = vacancy_id(app, "Graduate Software Developer")
    login(client, "applicant@inrole.demo")
    post(client, f"/jobs/{vid}/report", {"reason": "Spam", "details": "Repeated advertising"})

    logout(client)
    login(client, "admin@inrole.demo")
    with app.app_context():
        report = Report.query.filter_by(vacancy_id=vid).one()
        report_id = report.id
    post(client, f"/moderation/reports/{report_id}/resolve", {"reason": "Reviewed"})
    with app.app_context():
        assert db.session.get(Report, report_id).status == "resolved"

    post(client, "/moderation/templates", {
        "name": "Misleading listing",
        "subject": "Listing removed",
        "body": "This listing was removed after review.",
    })
    with app.app_context():
        assert DecisionTemplate.query.filter_by(name="Misleading listing").count() == 1
    queue_html = client.get("/moderation").get_data(as_text=True)
    assert 'class="panel decision-template-form"' in queue_html
    assert 'id="template-body"' in queue_html
