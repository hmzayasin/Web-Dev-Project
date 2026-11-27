from io import BytesIO
from pathlib import Path

from app import db
from app.models import Application, StatusEvent, User, Vacancy

from .conftest import csrf, login, post


def get_application_id(app, email, title):
    with app.app_context():
        user = User.query.filter_by(email=email).one()
        vacancy = Vacancy.query.filter_by(title=title).one()
        return Application.query.filter_by(
            applicant_id=user.id, vacancy_id=vacancy.id
        ).one().id


def get_vacancy_id(app, title):
    with app.app_context():
        return Vacancy.query.filter_by(title=title).one().id


def upload_cv(client):
    return client.post(
        "/profile",
        data={"cv": (BytesIO(b"candidate CV"), "candidate.pdf")},
        content_type="multipart/form-data",
    )


def test_apply_requires_cv_and_duplicate_is_rejected(app, client):
    vid = get_vacancy_id(app, "Junior Data Analyst")
    login(client, "applicant@inrole.demo")

    response = post(client, f"/jobs/{vid}/apply")
    assert response.status_code == 302
    assert response.location.endswith("/profile")
    with app.app_context():
        applicant = User.query.filter_by(email="applicant@inrole.demo").one()
        assert Application.query.filter_by(vacancy_id=vid, applicant_id=applicant.id).count() == 0

    assert upload_cv(client).status_code == 302
    response = post(client, f"/jobs/{vid}/apply")
    assert response.status_code == 302
    with app.app_context():
        applicant = User.query.filter_by(email="applicant@inrole.demo").one()
        application = Application.query.filter_by(vacancy_id=vid, applicant_id=applicant.id).one()
        assert application.status == "Submitted"
        event = StatusEvent.query.filter_by(application_id=application.id).one()
        assert event.from_status is None
        assert event.to_status == "Submitted"

    response = post(client, f"/jobs/{vid}/apply")
    assert response.status_code == 302
    with app.app_context():
        assert Application.query.filter_by(vacancy_id=vid, applicant_id=applicant.id).count() == 1


def test_apply_rejects_closed_vacancy(app, client):
    closed_vid = get_vacancy_id(app, "Customer Success Associate")
    expired_vid = get_vacancy_id(app, "Marketing Intern")
    login(client, "applicant@inrole.demo")
    upload_cv(client)

    for vid in (closed_vid, expired_vid):
        response = post(client, f"/jobs/{vid}/apply")
        assert response.status_code == 302
    with app.app_context():
        applicant = User.query.filter_by(email="applicant@inrole.demo").one()
        for vid in (closed_vid, expired_vid):
            assert Application.query.filter_by(vacancy_id=vid, applicant_id=applicant.id).count() == 0


def test_recruiter_status_json_validates_transition_note_and_csrf(app, client):
    aid = get_application_id(app, "candidate01@inrole.demo", "Graduate Software Developer")
    login(client, "recruiter@inrole.demo")
    token = csrf(client)

    response = client.post(
        f"/applications/{aid}/status",
        json={"status": "Under review", "note": "Initial review", "csrf_token": token},
        headers={"X-CSRFToken": token},
    )
    assert response.status_code == 200
    assert response.json["status"] == "Under review"

    response = client.post(
        f"/applications/{aid}/status",
        json={"status": "Offer", "note": "", "csrf_token": token},
        headers={"X-CSRFToken": token},
    )
    assert response.status_code == 400
    assert response.json["error"] == "That status transition is not allowed."

    response = client.post(
        f"/applications/{aid}/status",
        json={"status": "Rejected", "note": "", "csrf_token": token},
        headers={"X-CSRFToken": token},
    )
    assert response.status_code == 400
    assert "note" in response.json["error"]

    response = client.post(
        f"/applications/{aid}/status",
        json={"status": "Rejected", "note": "Does not meet requirements.", "csrf_token": token},
        headers={"X-CSRFToken": token},
    )
    assert response.status_code == 200
    with app.app_context():
        events = StatusEvent.query.filter_by(application_id=aid).order_by(StatusEvent.id).all()
        assert [(event.from_status, event.to_status) for event in events] == [
            ("Submitted", "Under review"), ("Under review", "Rejected")
        ]
        assert events[-1].note == "Does not meet requirements."

    response = client.post(
        f"/applications/{aid}/status",
        json={"status": "Under review", "note": "", "csrf_token": "wrong"},
        headers={"X-CSRFToken": "wrong"},
    )
    assert response.status_code == 400

    response = client.post(
        f"/applications/{aid}/status",
        json={"status": "Under review", "note": "", "csrf_token": 123},
    )
    assert response.status_code == 400


def test_recruiter_status_is_scoped_to_own_employer(app, client):
    aid = get_application_id(app, "candidate01@inrole.demo", "Graduate Software Developer")
    login(client, "pending.recruiter@inrole.demo")
    token = csrf(client)

    response = client.post(
        f"/applications/{aid}/status",
        json={"status": "Under review", "note": "", "csrf_token": token},
        headers={"X-CSRFToken": token},
    )
    assert response.status_code == 403


def test_applicant_can_withdraw_and_dashboard_shows_timeline(app, client):
    aid = get_application_id(app, "candidate01@inrole.demo", "Graduate Software Developer")
    login(client, "candidate01@inrole.demo")

    response = post(client, f"/applications/{aid}/withdraw", {"note": "Accepted another role."})
    assert response.status_code == 302
    dashboard = client.get("/dashboard")
    assert dashboard.status_code == 200
    assert b"Accepted another role." in dashboard.data

    with app.app_context():
        application = db.session.get(Application, aid)
        event = StatusEvent.query.filter_by(application_id=aid).one()
        assert application.status == "Withdrawn"
        assert (event.from_status, event.to_status) == ("Submitted", "Withdrawn")


def test_dashboard_shows_seeded_status_without_event_history(client):
    login(client, "applicant@inrole.demo")
    response = client.get("/dashboard")
    assert response.status_code == 200
    assert b"Shortlisted" in response.data
    assert b"Further status updates will appear here." in response.data


def test_applicant_cannot_withdraw_another_users_application(app, client):
    aid = get_application_id(app, "candidate01@inrole.demo", "Graduate Software Developer")
    login(client, "applicant@inrole.demo")
    response = post(client, f"/applications/{aid}/withdraw")
    assert response.status_code == 403


def test_application_cv_download_is_scoped_to_vacancy_owner(app, client):
    aid = get_application_id(app, "candidate03@inrole.demo", "Graduate Software Developer")
    with app.app_context():
        application = db.session.get(Application, aid)
        filename = "candidate_cv.pdf"
        application.applicant.cv_filename = filename
        db.session.commit()
        Path(app.config["UPLOAD_FOLDER"], filename).write_bytes(b"private CV")

    login(client, "recruiter@inrole.demo")
    response = client.get(f"/applications/{aid}/cv")
    assert response.status_code == 200
    assert response.data == b"private CV"

    client.get("/auth/logout")
    login(client, "pending.recruiter@inrole.demo")
    assert client.get(f"/applications/{aid}/cv").status_code == 403

    client.get("/auth/logout")
    login(client, "admin@inrole.demo")
    assert client.get(f"/applications/{aid}/cv").data == b"private CV"