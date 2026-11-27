"""F20 saved vacancies (M, extra)."""
from app import db
from app.models import Vacancy
from app.saved import SavedVacancy

from .conftest import login, logout, post


def vid(app, title):
    with app.app_context():
        return Vacancy.query.filter_by(title=title).one().id


def saved_count(app, email="applicant@inrole.demo"):
    with app.app_context():
        from app.models import User
        user = User.query.filter_by(email=email).one()
        return SavedVacancy.query.filter_by(user_id=user.id).count()


def save(client, vacancy_id, action="save", **extra):
    return post(client, f"/saved/{vacancy_id}", {"action": action, **extra})


def test_applicant_can_save_and_remove(app, client):
    v = vid(app, "Junior Data Analyst")
    login(client, "applicant@inrole.demo")
    save(client, v)
    assert saved_count(app) == 1
    html = client.get("/saved").get_data(as_text=True)
    assert "Junior Data Analyst" in html
    save(client, v, "unsave")
    assert saved_count(app) == 0
    assert "haven't saved any jobs" in client.get("/saved").get_data(as_text=True)


def test_saving_twice_is_idempotent(app, client):
    v = vid(app, "Junior Data Analyst")
    login(client, "applicant@inrole.demo")
    save(client, v)
    save(client, v)                                   # double-click / resent request
    assert saved_count(app) == 1
    save(client, v, "unsave")
    save(client, v, "unsave")
    assert saved_count(app) == 0


def test_saved_badge_on_job_cards_and_detail_button(app, client):
    v = vid(app, "Junior Data Analyst")
    login(client, "applicant@inrole.demo")
    assert "Save for later" in client.get(f"/jobs/{v}").get_data(as_text=True)
    save(client, v)
    assert "★ Saved" in client.get("/jobs").get_data(as_text=True)
    assert "Saved · remove" in client.get(f"/jobs/{v}").get_data(as_text=True)


def test_redirects_back_to_safe_next_only(app, client):
    v = vid(app, "Junior Data Analyst")
    login(client, "applicant@inrole.demo")
    assert save(client, v, next=f"/jobs/{v}").headers["Location"].endswith(f"/jobs/{v}")
    assert "evil" not in save(client, v, next="https://evil.example").headers["Location"]


def test_cannot_save_hidden_draft_or_unverified_vacancies(app, client):
    login(client, "applicant@inrole.demo")
    assert save(client, vid(app, "UX Research Assistant")).status_code == 404       # draft
    assert save(client, vid(app, "Sales Trainee")).status_code == 404               # unverified employer
    save(client, vid(app, "Customer Success Associate"))                             # closed: refused
    assert saved_count(app) == 0
    assert save(client, 99999).status_code == 404


def test_list_shows_closed_and_removed_states(app, client):
    analyst, backend = vid(app, "Junior Data Analyst"), vid(app, "Backend Engineer (Python)")
    login(client, "applicant@inrole.demo")
    save(client, analyst)
    save(client, backend)
    with app.app_context():
        db.session.get(Vacancy, analyst).status = "closed"
        db.session.get(Vacancy, backend).status = "removed"
        db.session.commit()
    html = client.get("/saved").get_data(as_text=True)
    assert "Closed" in html and "Removed by an administrator" in html


def test_list_marks_vacancies_already_applied_to(app, client):
    with app.app_context():
        frontend = Vacancy.query.filter_by(title="Frontend Developer Intern").one().id   # seed: applicant applied
    login(client, "applicant@inrole.demo")
    save(client, frontend)
    assert "Applied" in client.get("/saved").get_data(as_text=True)


def test_saved_lists_are_private_per_user(app, client):
    v = vid(app, "Junior Data Analyst")
    login(client, "applicant@inrole.demo")
    save(client, v)
    logout(client)
    login(client, "candidate01@inrole.demo")
    assert "Junior Data Analyst" not in client.get("/saved").get_data(as_text=True)
    save(client, v, "unsave")                         # can't remove someone else's save
    assert saved_count(app) == 1


def test_only_applicants_can_save(app, client):
    v = vid(app, "Junior Data Analyst")
    assert client.get("/saved").status_code == 302
    login(client, "recruiter@inrole.demo")
    assert client.get("/saved").status_code == 403
    assert save(client, v).status_code == 403


def test_save_requires_csrf_and_valid_action(app, client):
    v = vid(app, "Junior Data Analyst")
    login(client, "applicant@inrole.demo")
    assert client.post(f"/saved/{v}", data={"action": "save"}).status_code == 400
    assert save(client, v, "explode").status_code == 400
    assert saved_count(app) == 0
