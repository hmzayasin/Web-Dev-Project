"""Application status transitions shared by the API and applicant list."""

from app.vacancy_rules import STAGES


STATUS_TRANSITIONS = {
    "Submitted": ("Under review", "Rejected"),
    "Under review": ("Shortlisted", "Rejected"),
    "Shortlisted": ("Interview", "Rejected"),
    "Interview": ("Offer", "Rejected"),
    "Offer": (),
}
MAX_STATUS_NOTE_LENGTH = 1000


def validate_status_change(current_status, next_status, note):
    """Return a validation message, or None when this transition is allowed."""
    if next_status not in STATUS_TRANSITIONS.get(current_status, ()):
        return "That status transition is not allowed."
    if not isinstance(note, str):
        return "The status note must be text."
    if len(note) > MAX_STATUS_NOTE_LENGTH:
        return f"The status note must be at most {MAX_STATUS_NOTE_LENGTH} characters."
    if next_status == "Rejected" and not note.strip():
        return "Add a note when rejecting an application."
    return None


def is_withdrawable(status):
    return status in STAGES