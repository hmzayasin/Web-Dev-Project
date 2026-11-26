import pytest

from app import create_app


@pytest.fixture
def app(tmp_path):
    # in-memory SQLite; create_app() seeds the demo employers, users and vacancies
    return create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite://",
                       "UPLOAD_FOLDER": str(tmp_path)})


@pytest.fixture
def client(app):
    return app.test_client()


def login(client, email, password="InRole123!"):
    return client.post("/auth/login", data={"email": email, "password": password}, follow_redirects=True)


def csrf(client):
    """Put a known CSRF token in the session and return it for use in form posts."""
    with client.session_transaction() as session:
        session["_csrf_token"] = "test-token"
    return "test-token"


def post(client, url, data=None, **kw):
    data = dict(data or {})
    data["csrf_token"] = csrf(client)
    return client.post(url, data=data, **kw)
