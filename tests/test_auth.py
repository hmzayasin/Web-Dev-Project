"""M's slice: F1 accounts, F2 role-based access control, F3 private CVs (R8), CSRF."""
from io import BytesIO
from pathlib import Path

import pytest

from app import db
from app.models import Employer, User, Vacancy

from .conftest import csrf, login, logout, post

PASSWORD = "InRole123!"


def signup(client, **over):
    data = {"name": "Niamh Byrne", "email": "niamh@example.com", "password": "longenough1", "role": "applicant"}
    data.update(over)
    return post(client, "/auth/register", data)


def logged_in_as(client):
    with client.session_transaction() as session:
        return session.get("_user_id")


# ---------------- F1: registration ----------------
def test_register_applicant_logs_in(app, client):
    response = signup(client)
    assert response.status_code == 302 and "/dashboard" in response.headers["Location"]
    with app.app_context():
        user = User.query.filter_by(email="niamh@example.com").one()
        assert user.role == "applicant" and user.employer_id is None
        assert user.password_hash != "longenough1" and user.check_password("longenough1")   # hashed, never plain text
    assert logged_in_as(client) == str(user.id)


def test_register_recruiter_creates_pending_organisation(app, client):
    signup(client, email="hr@acme.ie", role="recruiter", organisation="Acme Robotics",
           organisation_description="Robots for warehouses.")
    with app.app_context():
        user = User.query.filter_by(email="hr@acme.ie").one()
        assert user.role == "recruiter"
        assert user.employer.name == "Acme Robotics" and user.employer.status == "pending"   # R6


def test_recruiter_must_name_organisation(app, client):
    assert signup(client, email="hr@acme.ie", role="recruiter", organisation="").status_code == 400
    with app.app_context():
        assert User.query.filter_by(email="hr@acme.ie").first() is None


@pytest.mark.parametrize("over", [
    {"email": "applicant@inrole.demo"},          # already registered
    {"email": "APPLICANT@inrole.demo"},          # same email, different case
    {"password": "short"},
    {"email": "not-an-email"},
    {"name": ""},
])
def test_register_rejects_bad_input(app, client, over):
    response = signup(client, **over)
    assert response.status_code == 400
    assert logged_in_as(client) is None


@pytest.mark.parametrize("role", ["admin", "reviewer"])
def test_public_signup_cannot_create_privileged_roles(app, client, role):
    assert signup(client, role=role).status_code == 400
    with app.app_context():
        assert User.query.filter_by(email="niamh@example.com").first() is None


def test_register_keeps_typed_values_after_an_error(client):
    html = signup(client, password="short", name="Keep Me").get_data(as_text=True)
    assert 'value="Keep Me"' in html


# ---------------- F1: log in / log out ----------------
def test_login_and_wrong_password(client):
    response = post(client, "/auth/login", {"email": "applicant@inrole.demo", "password": "wrong"})
    assert response.status_code == 401 and logged_in_as(client) is None
    assert "Email or password was incorrect" in response.get_data(as_text=True)
    login(client, "Applicant@InRole.demo")                     # email is case-insensitive
    assert logged_in_as(client) is not None


def test_login_follows_safe_next_only(client):
    data = {"email": "recruiter@inrole.demo", "password": PASSWORD}
    response = post(client, "/auth/login?next=/manage/vacancies/", data)
    assert response.headers["Location"].endswith("/manage/vacancies/")
    logout(client)
    for evil in ("https://evil.example/", "//evil.example/", "/\\evil.example"):
        response = post(client, f"/auth/login?next={evil}", data)
        assert "evil" not in response.headers["Location"]
        logout(client)


def test_protected_page_sends_anonymous_user_to_login_with_next(client):
    response = client.get("/profile")
    assert response.status_code == 302 and "/auth/login" in response.headers["Location"]
    assert "next=" in response.headers["Location"]


def test_logout_is_post_only(client):
    login(client, "applicant@inrole.demo")
    assert client.get("/auth/logout").status_code == 405        # a link or <img> on another site can't log you out
    assert logged_in_as(client) is not None
    logout(client)
    assert logged_in_as(client) is None


def test_logged_in_user_is_sent_away_from_login_and_register(client):
    login(client, "applicant@inrole.demo")
    assert client.get("/auth/login").status_code == 302
    assert client.get("/auth/register").status_code == 302


# ---------------- CSRF on every form ----------------
def test_forms_without_csrf_token_are_rejected(client):
    assert client.post("/auth/login", data={"email": "applicant@inrole.demo", "password": PASSWORD}).status_code == 400
    assert client.post("/auth/register", data={"name": "X", "email": "x@y.ie", "password": "longenough"}).status_code == 400
    login(client, "applicant@inrole.demo")
    assert client.post("/auth/logout").status_code == 400
    assert client.post("/profile", data={"cv": (BytesIO(b"cv"), "cv.pdf")},
                       content_type="multipart/form-data").status_code == 400


def test_csrf_token_can_be_sent_as_header_for_javascript(client):
    login(client, "applicant@inrole.demo")
    token = csrf(client)
    assert client.post("/auth/logout", headers={"X-CSRFToken": token}).status_code == 302


def test_wrong_csrf_token_is_rejected(client):
    csrf(client)
    response = client.post("/auth/login", data={"email": "applicant@inrole.demo", "password": PASSWORD,
                                                "csrf_token": "guessed"})
    assert response.status_code == 400


# ---------------- F2: role-based access control ----------------
ACCESS = [
    # (url, roles that may open it)
    ("/dashboard", {"applicant", "recruiter", "reviewer", "admin"}),
    ("/profile", {"applicant"}),
    ("/manage/vacancies/", {"recruiter", "reviewer", "admin"}),
    ("/manage/vacancies/new", {"recruiter"}),
    ("/moderation", {"admin"}),
]
ACCOUNTS = {"applicant": "applicant@inrole.demo", "recruiter": "recruiter@inrole.demo",
            "reviewer": "reviewer@inrole.demo", "admin": "admin@inrole.demo"}


@pytest.mark.parametrize("role", sorted(ACCOUNTS))
def test_role_access_matrix(client, role):
    login(client, ACCOUNTS[role])
    for url, allowed in ACCESS:
        expected = 200 if role in allowed else 403
        assert client.get(url).status_code == expected, (role, url)


def test_anonymous_users_are_sent_to_login(client):
    for url, _ in ACCESS:
        assert client.get(url).status_code == 302, url


def test_nav_shows_links_for_the_role(client):
    login(client, "applicant@inrole.demo")
    html = client.get("/dashboard").get_data(as_text=True)
    assert "My Profile" in html and "Moderation" not in html and ">Vacancies<" not in html
    logout(client)
    login(client, "admin@inrole.demo")
    html = client.get("/dashboard").get_data(as_text=True)
    assert "Moderation" in html and "My Profile" not in html


# ---------------- F3 / R8: private CVs ----------------
def give_cv(app, email, content=b"%PDF-1.4 demo"):
    """Attach a real file to a demo user's CV and return their id."""
    with app.app_context():
        user = User.query.filter_by(email=email).one()
        user.cv_filename = f"user_{user.id}_test.pdf"
        (Path(app.config["UPLOAD_FOLDER"]) / user.cv_filename).write_bytes(content)
        db.session.commit()
        return user.id


def new_applicant_with_cv(app):
    """An applicant who has NOT applied anywhere."""
    with app.app_context():
        user = User(name="Loner", email="loner@example.com", role="applicant")
        user.set_password(PASSWORD)
        db.session.add(user)
        db.session.commit()
    return give_cv(app, "loner@example.com")


def test_applicant_can_download_own_cv_but_not_others(app, client):
    mine = give_cv(app, "applicant@inrole.demo")
    other = give_cv(app, "candidate01@inrole.demo")
    login(client, "applicant@inrole.demo")
    response = client.get(f"/private-cv/{mine}")
    assert response.status_code == 200 and response.data == b"%PDF-1.4 demo"
    assert "no-store" in response.headers["Cache-Control"]
    assert client.get(f"/private-cv/{other}").status_code == 403


def test_staff_of_employer_applied_to_can_open_cv(app, client):
    candidate = give_cv(app, "candidate01@inrole.demo")      # applied to a Northstar vacancy in the seed data
    for email in ("recruiter@inrole.demo", "reviewer@inrole.demo", "admin@inrole.demo"):
        login(client, email)
        assert client.get(f"/private-cv/{candidate}").status_code == 200, email
        logout(client)


def test_staff_of_other_employers_cannot_open_cv(app, client):
    candidate = give_cv(app, "candidate01@inrole.demo")
    login(client, "pending.recruiter@inrole.demo")           # Harbour Digital: candidate never applied there
    assert client.get(f"/private-cv/{candidate}").status_code == 403


def test_recruiter_cannot_open_cv_of_someone_who_never_applied(app, client):
    loner = new_applicant_with_cv(app)
    login(client, "recruiter@inrole.demo")
    assert client.get(f"/private-cv/{loner}").status_code == 403


def test_cv_missing_or_user_missing_is_404(app, client):
    login(client, "admin@inrole.demo")
    with app.app_context():
        no_cv = User.query.filter_by(email="candidate01@inrole.demo").one().id   # seed gives candidate01 no CV
    assert client.get(f"/private-cv/{no_cv}").status_code == 404
    assert client.get("/private-cv/99999").status_code == 404


def test_cv_is_not_served_from_public_static_folder(app, client):
    give_cv(app, "applicant@inrole.demo")
    with app.app_context():
        filename = User.query.filter_by(email="applicant@inrole.demo").one().cv_filename
    assert client.get(f"/static/{filename}").status_code == 404
    assert client.get(f"/private_uploads/{filename}").status_code == 404


def test_applicant_list_links_to_cv(app, client):
    give_cv(app, "candidate01@inrole.demo")
    with app.app_context():
        vid = Vacancy.query.filter_by(title="Graduate Software Developer").one().id
    login(client, "recruiter@inrole.demo")
    assert "Download CV" in client.get(f"/manage/vacancies/{vid}/applicants?q=candidate01").get_data(as_text=True)


def test_cv_upload_rejects_wrong_file_type(app, client):
    login(client, "applicant@inrole.demo")
    post(client, "/profile", {"cv": (BytesIO(b"MZ"), "virus.exe")}, content_type="multipart/form-data")
    with app.app_context():
        assert User.query.filter_by(email="applicant@inrole.demo").one().cv_filename is None
