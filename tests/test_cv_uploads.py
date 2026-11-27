from io import BytesIO
from pathlib import Path

from app import db
from app.main import _activate_cv_upload, _reserve_cv_upload
from app.models import User

from .conftest import csrf, login


def test_stale_cv_upload_cannot_replace_newer_generation(app):
    with app.app_context():
        user = User.query.filter_by(email="applicant@inrole.demo").one()
        user.cv_filename = "existing.pdf"
        db.session.commit()

        older_generation = _reserve_cv_upload(user.id)
        newer_generation = _reserve_cv_upload(user.id)

        activated, _ = _activate_cv_upload(user.id, older_generation, "older.pdf")
        assert not activated
        activated, previous_filename = _activate_cv_upload(user.id, newer_generation, "newer.pdf")
        assert activated
        assert previous_filename == "existing.pdf"

        db.session.refresh(user)
        assert user.cv_filename == "newer.pdf"
        assert user.cv_upload_version == newer_generation


def test_profile_uploads_use_unique_files_and_replace_active_cv(app, client):
    login(client, "applicant@inrole.demo")

    first = client.post(
        "/profile",
        data={"cv": (BytesIO(b"first CV"), "candidate.pdf"), "csrf_token": csrf(client)},
        content_type="multipart/form-data",
    )
    assert first.status_code == 302
    with app.app_context():
        user = User.query.filter_by(email="applicant@inrole.demo").one()
        first_filename = user.cv_filename
        upload_folder = Path(app.config["UPLOAD_FOLDER"])
        assert (upload_folder / first_filename).read_bytes() == b"first CV"

    second = client.post(
        "/profile",
        data={"cv": (BytesIO(b"new CV"), "candidate.pdf"), "csrf_token": csrf(client)},
        content_type="multipart/form-data",
    )
    assert second.status_code == 302
    with app.app_context():
        user = User.query.filter_by(email="applicant@inrole.demo").one()
        assert user.cv_filename != first_filename
        assert user.cv_upload_version == 2
        assert not (upload_folder / first_filename).exists()
        assert (upload_folder / user.cv_filename).read_bytes() == b"new CV"
