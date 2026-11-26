"""Business rules for vacancies (J's slice: F4, F5, F6, F9).

This file deliberately imports nothing from Flask or the database, so every
rule can be unit-tested on its own and read in one place:

  R1  ownership      -> enforced in app/vacancies.py (_own_or_403)
  R2  closing date   -> effective_status(), validate_vacancy(), transition()
  R6  verification   -> transition() refuses to publish for unverified employers
"""
from datetime import date, datetime

# ---- vacancy statuses -------------------------------------------------------
DRAFT, OPEN, CLOSED = "draft", "open", "closed"
# "hidden" and "removed" are set by admin moderation (S's slice), never by recruiters.
EDITABLE = (DRAFT, OPEN, CLOSED)
JOB_TYPES = ("Full-time", "Part-time", "Graduate", "Internship", "Contract")

# ---- application statuses (F9 filters / counts; mirrors the design report) ----
STAGES = ("Submitted", "Under review", "Shortlisted", "Interview", "Offer")
OUTCOMES = ("Rejected", "Withdrawn", "Vacancy withdrawn")
APPLICATION_STATUSES = STAGES + OUTCOMES

SORTS = ("newest", "oldest", "name", "status")
PAGE_SIZE = 10
LIMITS = {"title": (3, 140), "location": (2, 120), "description": (30, 5000)}


def parse_date(text):
    """'2026-12-31' -> date, anything else -> None."""
    try:
        return datetime.strptime((text or "").strip(), "%Y-%m-%d").date()
    except ValueError:
        return None


def effective_status(status, closing_date, today=None):
    """R2: an 'open' vacancy whose closing date has passed is treated as closed."""
    today = today or date.today()
    if status == OPEN and closing_date is not None and closing_date < today:
        return CLOSED
    return status


def validate_vacancy(form, *, require_future, today=None):
    """Check the create/edit form. Returns (clean_values, list_of_error_messages)."""
    today = today or date.today()
    errors = []
    clean = {
        "title": (form.get("title") or "").strip(),
        "location": (form.get("location") or "").strip(),
        "job_type": (form.get("job_type") or "").strip(),
        "description": (form.get("description") or "").strip(),
        "closing_date": None,
    }
    labels = {"title": "Job title", "location": "Location", "description": "Description"}
    for field, (low, high) in LIMITS.items():
        n = len(clean[field])
        if n < low:
            errors.append(f"{labels[field]} must be at least {low} characters.")
        elif n > high:
            errors.append(f"{labels[field]} must be at most {high} characters.")
    if clean["job_type"] not in JOB_TYPES:
        errors.append("Choose a job type from the list.")
    raw = (form.get("closing_date") or "").strip()
    if raw:
        parsed = parse_date(raw)
        if parsed is None:
            errors.append("Enter the closing date as a valid date.")
        elif require_future and parsed < today:
            errors.append("The closing date must be today or later.")
        else:
            clean["closing_date"] = parsed
    return clean, errors


def transition(status, action, *, employer_verified, closing_date,
               application_count=0, today=None):
    """Apply a status change. Returns (new_status, None) or (None, error_message).

    draft  --publish-->   open      (R6: employer verified; R2: future closing date)
    open   --close-->     closed
    closed --reopen-->    open      (same checks as publish)
    open   --unpublish--> draft     (only while nobody has applied)
    """
    today = today or date.today()
    if action in ("publish", "reopen"):
        needed = DRAFT if action == "publish" else CLOSED
        if status != needed:
            return None, f"You can't {action} a {status} vacancy."
        if not employer_verified:
            return None, "Your organisation must be verified by an administrator before you can publish."
        if closing_date is None:
            return None, "Add a closing date before publishing."
        if closing_date < today:
            return None, "Move the closing date to today or later first."
        return OPEN, None
    if action == "close":
        if status != OPEN:
            return None, f"You can't close a {status} vacancy."
        return CLOSED, None
    if action == "unpublish":
        if status != OPEN:
            return None, f"You can't unpublish a {status} vacancy."
        if application_count:
            return None, "This vacancy already has applications, so close it instead of returning it to draft."
        return DRAFT, None
    return None, "Unknown action."


def clean_choice(value, allowed, default):
    return value if value in allowed else default


def clean_page(raw):
    """?page=abc or ?page=-3 -> 1."""
    try:
        return max(1, int(raw))
    except (TypeError, ValueError):
        return 1
