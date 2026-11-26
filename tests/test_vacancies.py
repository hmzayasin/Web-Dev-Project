"""Integration tests for F4, F5, F6, F9. They use the demo data seeded by create_app()."""
from datetime import date, timedelta

from app import db
from app.models import Application, Employer, User, Vacancy

from .conftest import login, post


def ver(app, vacancy_id):
    with app.app_context():
        return db.session.get(Vacancy, vacancy_id).version


def vid(app, title):
    with app.app_context():
        return Vacancy.query.filter_by(title=title).one().id


def form(**over):
    data = {"title": "QA Engineer", "location": "Dublin", "job_type": "Full-time",
            "description": "Test the product carefully and report problems clearly. " * 2,
            "closing_date": (date.today() + timedelta(days=10)).isoformat(), "action": "save"}
    data.update(over)
    return data


# ---------------- F5 / R2 / R6: what the public can see ----------------
def test_public_list_hides_draft_closed_expired_and_unverified(client):
    html = client.get("/jobs").get_data(as_text=True)
    assert "Graduate Software Developer" in html and "Backend Engineer (Python)" in html
    for hidden in ("UX Research Assistant", "Customer Success Associate", "Marketing Intern", "Sales Trainee"):
        assert hidden not in html


def test_server_side_filters_and_sort(client):
    remote = client.get("/jobs?location=Remote").get_data(as_text=True)
    assert "Frontend Developer Intern" in remote and "Junior Data Analyst" not in remote
    html = client.get("/jobs?type=Graduate").get_data(as_text=True)
    assert "Graduate Software Developer" in html and "Junior Data Analyst" not in html
    assert "Northstar" in client.get("/jobs?q=northstar").get_data(as_text=True)
    assert "No open roles matched" in client.get("/jobs?q=zzzz").get_data(as_text=True)
    assert client.get("/jobs?sort=closing").status_code == 200


def test_home_only_shows_public_vacancies(client):
    assert "Sales Trainee" not in client.get("/").get_data(as_text=True)


# ---------------- F6: detail page ----------------
def test_detail_open_closed_and_hidden_states(app, client):
    assert client.get(f"/jobs/{vid(app, 'Graduate Software Developer')}").status_code == 200
    closed = client.get(f"/jobs/{vid(app, 'Customer Success Associate')}")
    assert closed.status_code == 200 and "This vacancy is closed" in closed.get_data(as_text=True)
    assert "Applications closed" in closed.get_data(as_text=True)
    assert client.get(f"/jobs/{vid(app, 'UX Research Assistant')}").status_code == 404      # draft
    assert client.get(f"/jobs/{vid(app, 'Sales Trainee')}").status_code == 404              # unverified employer
    expired = client.get(f"/jobs/{vid(app, 'Marketing Intern')}")
    assert "This vacancy is closed" in expired.get_data(as_text=True)                       # R2


def test_owner_can_preview_draft_but_other_employer_cannot(app, client):
    draft = vid(app, "UX Research Assistant")
    login(client, "pending.recruiter@inrole.demo")
    assert client.get(f"/jobs/{draft}").status_code == 404
    client.get("/auth/logout")
    login(client, "recruiter@inrole.demo")
    assert "Draft preview" in client.get(f"/jobs/{draft}").get_data(as_text=True)


def test_applicant_sees_their_application_state(app, client):
    login(client, "applicant@inrole.demo")
    html = client.get(f"/jobs/{vid(app, 'Frontend Developer Intern')}").get_data(as_text=True)
    assert "You applied" in html and "Shortlisted" in html


# ---------------- F4: manage vacancies ----------------
def test_manage_requires_staff_role(client):
    assert client.get("/manage/vacancies/").status_code == 302                  # not logged in -> login
    login(client, "applicant@inrole.demo")
    assert client.get("/manage/vacancies/").status_code == 403


def test_recruiter_sees_only_own_employer_vacancies(client):
    login(client, "recruiter@inrole.demo")
    html = client.get("/manage/vacancies/").get_data(as_text=True)
    assert "Graduate Software Developer" in html and "Sales Trainee" not in html


def test_create_draft_then_publish_as_verified_recruiter(app, client):
    login(client, "recruiter@inrole.demo")
    assert post(client, "/manage/vacancies/new", form()).status_code == 302
    v = vid(app, "QA Engineer")
    with app.app_context():
        assert db.session.get(Vacancy, v).status == "draft"
    post(client, f"/manage/vacancies/{v}/status", {"action": "publish", "version": ver(app, v)})
    with app.app_context():
        assert db.session.get(Vacancy, v).status == "open"
    assert "QA Engineer" in client.get("/jobs").get_data(as_text=True)


def test_save_and_publish_in_one_step(app, client):
    login(client, "recruiter@inrole.demo")
    post(client, "/manage/vacancies/new", form(action="publish"))
    with app.app_context():
        assert Vacancy.query.filter_by(title="QA Engineer").one().status == "open"


def test_unverified_employer_cannot_publish(app, client):                        # R6
    login(client, "pending.recruiter@inrole.demo")
    post(client, "/manage/vacancies/new", form(action="publish"))
    with app.app_context():
        assert Vacancy.query.filter_by(title="QA Engineer").one().status == "draft"
    assert "QA Engineer" not in client.get("/jobs").get_data(as_text=True)


def test_invalid_form_is_rejected(client):
    login(client, "recruiter@inrole.demo")
    response = post(client, "/manage/vacancies/new", form(title="x", closing_date="not-a-date"))
    assert response.status_code == 400


def test_cannot_publish_with_past_closing_date(app, client):                       # R2
    login(client, "recruiter@inrole.demo")
    past = (date.today() - timedelta(days=2)).isoformat()
    assert post(client, "/manage/vacancies/new", form(action="publish", closing_date=past)).status_code == 400


def test_close_and_reopen(app, client):
    login(client, "recruiter@inrole.demo")
    v = vid(app, "Backend Engineer (Python)")
    post(client, f"/manage/vacancies/{v}/status", {"action": "close", "version": ver(app, v)})
    with app.app_context():
        assert db.session.get(Vacancy, v).status == "closed"
    assert "Backend Engineer" not in client.get("/jobs").get_data(as_text=True)
    post(client, f"/manage/vacancies/{v}/status", {"action": "reopen", "version": ver(app, v)})
    with app.app_context():
        assert db.session.get(Vacancy, v).status == "open"


def test_cannot_unpublish_with_applications(app, client):
    login(client, "recruiter@inrole.demo")
    v = vid(app, "Graduate Software Developer")
    post(client, f"/manage/vacancies/{v}/status", {"action": "unpublish", "version": ver(app, v)})
    with app.app_context():
        assert db.session.get(Vacancy, v).status == "open"


def test_edit_vacancy(app, client):
    login(client, "recruiter@inrole.demo")
    v = vid(app, "Backend Engineer (Python)")
    assert client.get(f"/manage/vacancies/{v}/edit").status_code == 200
    post(client, f"/manage/vacancies/{v}/edit", form(title="Senior Backend Engineer", version=ver(app, v)))
    with app.app_context():
        assert db.session.get(Vacancy, v).title == "Senior Backend Engineer"


# ---------------- R1: ownership ----------------
def test_other_employer_cannot_edit_or_change_status(app, client):
    v = vid(app, "Graduate Software Developer")
    login(client, "pending.recruiter@inrole.demo")
    assert client.get(f"/manage/vacancies/{v}/edit").status_code == 403
    assert post(client, f"/manage/vacancies/{v}/edit", form()).status_code == 403
    assert post(client, f"/manage/vacancies/{v}/status", {"action": "close"}).status_code == 403
    assert client.get(f"/manage/vacancies/{v}/applicants").status_code == 403


def test_reviewer_is_read_only(app, client):
    v = vid(app, "Graduate Software Developer")
    login(client, "reviewer@inrole.demo")
    assert client.get("/manage/vacancies/").status_code == 200
    assert client.get(f"/manage/vacancies/{v}/applicants").status_code == 200
    assert client.get("/manage/vacancies/new").status_code == 403
    assert post(client, f"/manage/vacancies/{v}/status", {"action": "close"}).status_code == 403


# ---------------- CSRF ----------------
def test_post_without_csrf_token_is_rejected(app, client):
    login(client, "recruiter@inrole.demo")
    v = vid(app, "Backend Engineer (Python)")
    assert client.post(f"/manage/vacancies/{v}/status", data={"action": "close"}).status_code == 400
    with app.app_context():
        assert db.session.get(Vacancy, v).status == "open"


# ---------------- F9: applicant list ----------------
def test_applicant_list_counts_and_pagination(app, client):
    v = vid(app, "Graduate Software Developer")
    login(client, "recruiter@inrole.demo")
    page1 = client.get(f"/manage/vacancies/{v}/applicants").get_data(as_text=True)
    assert "14 applicants" in page1 and "Page 1 of 2" in page1
    page2 = client.get(f"/manage/vacancies/{v}/applicants?page=2").get_data(as_text=True)
    assert "Page 2 of 2" in page2
    assert client.get(f"/manage/vacancies/{v}/applicants?page=999").status_code == 200   # out of range is safe


def test_applicant_list_filter_search_and_sort(app, client):
    v = vid(app, "Graduate Software Developer")
    login(client, "recruiter@inrole.demo")
    html = client.get(f"/manage/vacancies/{v}/applicants?status=Interview").get_data(as_text=True)
    assert "Noah Patel" in html and "Aoife Murphy" not in html
    assert "Sofia Rossi" in client.get(f"/manage/vacancies/{v}/applicants?q=rossi").get_data(as_text=True)
    for sort in ("newest", "oldest", "name", "status", "bogus"):
        assert client.get(f"/manage/vacancies/{v}/applicants?sort={sort}").status_code == 200
    assert client.get(f"/manage/vacancies/{v}/applicants?status=Hacked").status_code == 200


def test_applicant_list_blocked_for_applicants(app, client):
    v = vid(app, "Graduate Software Developer")
    login(client, "applicant@inrole.demo")
    assert client.get(f"/manage/vacancies/{v}/applicants").status_code == 403


# ---------------- lost updates (stale / delayed saves) ----------------
def test_stale_edit_does_not_overwrite_newer_save(app, client):
    login(client, "recruiter@inrole.demo")
    v = vid(app, "Backend Engineer (Python)")
    opened_with = ver(app, v)                                              # both saves started from this version
    post(client, f"/manage/vacancies/{v}/edit", form(title="Second update", version=opened_with))
    # the first save was delayed by a bad connection and only arrives now, still carrying the old version
    response = post(client, f"/manage/vacancies/{v}/edit", form(title="Delayed first save", version=opened_with),
                    follow_redirects=True)
    assert "NOT applied" in response.get_data(as_text=True)
    with app.app_context():
        assert db.session.get(Vacancy, v).title == "Second update"


def test_version_increases_on_every_save(app, client):
    login(client, "recruiter@inrole.demo")
    v = vid(app, "Backend Engineer (Python)")
    before = ver(app, v)
    post(client, f"/manage/vacancies/{v}/edit", form(version=before))
    assert ver(app, v) > before


def test_stale_status_change_is_rejected(app, client):
    login(client, "recruiter@inrole.demo")
    v = vid(app, "Backend Engineer (Python)")
    old = ver(app, v)
    post(client, f"/manage/vacancies/{v}/edit", form(version=old))        # someone edits first
    post(client, f"/manage/vacancies/{v}/status", {"action": "close", "version": old})
    with app.app_context():
        assert db.session.get(Vacancy, v).status == "open"


def test_missing_version_is_rejected(app, client):
    login(client, "recruiter@inrole.demo")
    v = vid(app, "Backend Engineer (Python)")
    post(client, f"/manage/vacancies/{v}/edit", form(title="No version sent"))
    with app.app_context():
        assert db.session.get(Vacancy, v).title != "No version sent"
