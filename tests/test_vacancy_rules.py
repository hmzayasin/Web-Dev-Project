"""Pure rule tests: no Flask, no database."""
from datetime import date, timedelta

from app import vacancy_rules as r

TODAY = date(2026, 11, 26)
GOOD = {"title": "Data Analyst", "location": "Dublin", "job_type": "Full-time",
        "description": "x" * 40, "closing_date": "2026-12-31"}


def test_valid_form_passes():
    clean, errors = r.validate_vacancy(GOOD, require_future=True, today=TODAY)
    assert errors == [] and clean["closing_date"] == date(2026, 12, 31)


def test_short_title_and_bad_type_rejected():
    _, errors = r.validate_vacancy({**GOOD, "title": "Hi", "job_type": "Wizard"}, require_future=False, today=TODAY)
    assert len(errors) == 2


def test_past_closing_date_only_blocked_when_future_required():
    past = {**GOOD, "closing_date": "2026-01-01"}
    assert r.validate_vacancy(past, require_future=True, today=TODAY)[1]
    assert not r.validate_vacancy(past, require_future=False, today=TODAY)[1]


def test_garbage_date_rejected_and_blank_allowed():
    assert r.validate_vacancy({**GOOD, "closing_date": "31/12/2026"}, require_future=False, today=TODAY)[1]
    clean, errors = r.validate_vacancy({**GOOD, "closing_date": ""}, require_future=False, today=TODAY)
    assert not errors and clean["closing_date"] is None


def test_effective_status_closes_expired_open_vacancy():
    assert r.effective_status("open", TODAY - timedelta(days=1), TODAY) == "closed"
    assert r.effective_status("open", TODAY, TODAY) == "open"          # last day still open
    assert r.effective_status("draft", TODAY - timedelta(days=9), TODAY) == "draft"
    assert r.effective_status("open", None, TODAY) == "open"


def test_publish_needs_verified_employer_and_future_date():
    ok = dict(employer_verified=True, closing_date=TODAY, today=TODAY)
    assert r.transition("draft", "publish", **ok) == ("open", None)
    assert r.transition("draft", "publish", **{**ok, "employer_verified": False})[0] is None   # R6
    assert r.transition("draft", "publish", **{**ok, "closing_date": None})[0] is None
    assert r.transition("draft", "publish", **{**ok, "closing_date": TODAY - timedelta(days=1)})[0] is None  # R2


def test_close_reopen_unpublish_rules():
    ok = dict(employer_verified=True, closing_date=TODAY + timedelta(days=5), today=TODAY)
    assert r.transition("open", "close", **ok)[0] == "closed"
    assert r.transition("closed", "reopen", **ok)[0] == "open"
    assert r.transition("open", "unpublish", **ok)[0] == "draft"
    assert r.transition("open", "unpublish", application_count=2, **ok)[0] is None
    assert r.transition("draft", "close", **ok)[0] is None
    assert r.transition("open", "reopen", **ok)[0] is None
    assert r.transition("hidden", "publish", **ok)[0] is None          # moderation states are not recruiter-editable
    assert r.transition("draft", "nonsense", **ok)[0] is None


def test_page_and_choice_cleaning():
    assert r.clean_page("3") == 3 and r.clean_page("-4") == 1 and r.clean_page("abc") == 1 and r.clean_page(None) == 1
    assert r.clean_choice("name", r.SORTS, "newest") == "name" and r.clean_choice("x", r.SORTS, "newest") == "newest"
