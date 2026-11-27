"""M's foundation: error pages, layout, and upgrading an older database."""
from io import BytesIO

from sqlalchemy import create_engine, inspect, text

from app.schema_migrations import upgrade_schema

from .conftest import login, post


def test_friendly_404_page(client):
    response = client.get("/this-page-does-not-exist")
    assert response.status_code == 404
    assert "find that page" in response.get_data(as_text=True)   # the apostrophe is HTML-escaped


def test_upload_over_size_limit_gets_friendly_413(app, client):
    login(client, "applicant@inrole.demo")
    app.config["MAX_CONTENT_LENGTH"] = 1024
    response = post(client, "/profile", {"cv": (BytesIO(b"x" * 4096), "big.pdf")}, content_type="multipart/form-data")
    assert response.status_code == 413
    assert "too large" in response.get_data(as_text=True)


def test_logo_and_csrf_meta_tag_on_every_page(client):
    html = client.get("/").get_data(as_text=True)
    assert "inrole-logo.jpg" in html
    assert '<meta name="csrf-token"' in html


def test_upgrade_adds_vacancy_closing_date_and_version_to_old_database():
    engine = create_engine("sqlite://")
    try:
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE vacancy (id INTEGER PRIMARY KEY, title VARCHAR(140) NOT NULL)"))
            connection.execute(text("INSERT INTO vacancy (id, title) VALUES (1, 'Old role')"))
        upgrade_schema(engine)
        columns = {c["name"] for c in inspect(engine).get_columns("vacancy")}
        assert {"closing_date", "version"} <= columns
        with engine.connect() as connection:
            assert connection.execute(text("SELECT version FROM vacancy WHERE id = 1")).scalar_one() == 1
    finally:
        engine.dispose()
