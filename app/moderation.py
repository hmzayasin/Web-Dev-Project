from datetime import datetime

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy import or_

from app import db
from app.csrf import csrf_protect
from app.main import role_required
from app.models import Application, DecisionTemplate, Employer, ModerationAction, Report, ReviewerFeedback, StatusEvent, Vacancy

moderation_bp = Blueprint("moderation", __name__)
moderation_bp.before_request(csrf_protect)

REPORT_REASONS = ("Misleading information", "Discrimination", "Scam or fraud", "Inappropriate content", "Spam", "Other")
RECOMMENDATIONS = ("No recommendation", "Proceed", "Hold", "Reject")


def apply_moderation(target_type, target_id, action_name, reason=""):
    if target_type == "vacancy":
        target = db.get_or_404(Vacancy, target_id)
        if target.status == "removed":
            return False
        if action_name == "hide":
            target.status = "hidden"
        elif action_name == "remove":
            target.status = "removed"
            target.removal_reason = reason or "Removed by an administrator."
            target.removed_at = datetime.utcnow()
            terminal = {"Rejected", "Withdrawn", "Vacancy withdrawn"}
            for application in Application.query.filter_by(vacancy_id=target.id).all():
                if application.status not in terminal:
                    old_status = application.status
                    application.status = "Vacancy withdrawn"
                    db.session.add(StatusEvent(
                        application_id=application.id, from_status=old_status,
                        to_status="Vacancy withdrawn", note=target.removal_reason,
                        created_by_id=current_user.id,
                    ))
        elif action_name == "restore" and target.status == "hidden":
            target.status = "closed"
        elif action_name == "publish":
            target.status = "closed"
        else:
            return False
    elif target_type == "employer":
        target = db.get_or_404(Employer, target_id)
        if action_name == "verify":
            target.status = "verified"
        elif action_name == "suspend":
            target.status = "suspended"
            for vacancy in Vacancy.query.filter_by(employer_id=target.id).filter(
                    or_(Vacancy.status == "open", Vacancy.status == "closed")).all():
                vacancy.status = "hidden"
        elif action_name in ("restore", "unsuspend"):
            target.status = "verified"
        else:
            return False
    else:
        return False
    db.session.add(ModerationAction(
        moderator_id=current_user.id, target_type=target_type, target_id=target_id,
        action=action_name, reason=reason,
    ))
    return True


@moderation_bp.route("/moderation")
@role_required("admin")
def queue():
    status = request.args.get("status", "open")
    query = Report.query
    if status in ("open", "resolved", "dismissed"):
        query = query.filter_by(status=status)
    reports = query.order_by(Report.created_at.desc()).all()
    vacancies = Vacancy.query.filter(Vacancy.status != "removed").order_by(Vacancy.created_at.desc()).all()
    employers = Employer.query.order_by(Employer.name).all()
    templates = DecisionTemplate.query.order_by(DecisionTemplate.name).all()
    actions = ModerationAction.query.order_by(ModerationAction.created_at.desc()).limit(20).all()
    return render_template("moderation_queue.html", reports=reports, vacancies=vacancies,
                           employers=employers, templates=templates, actions=actions,
                           status=status, reasons=REPORT_REASONS)


@moderation_bp.route("/admin/moderation")
@role_required("admin")
def admin_queue_alias():
    return redirect(url_for("moderation.queue"))

@moderation_bp.route("/moderation/queue")
@role_required("admin")
def queue_alias():
    return redirect(url_for("moderation.queue"))


@moderation_bp.route("/moderation/action", methods=["POST"])
@role_required("admin")
def action():
    try:
        target_id = int(request.form.get("target_id", ""))
    except (TypeError, ValueError):
        abort(400)
    target_type = request.form.get("target_type", "")
    action_name = request.form.get("action", "")
    reason = request.form.get("reason", "").strip()[:2000]
    if not apply_moderation(target_type, target_id, action_name, reason):
        flash("Unknown moderation action.", "error")
    else:
        db.session.commit()
        flash("Moderation action completed.", "success")
    return redirect(url_for("moderation.queue"))


@moderation_bp.route("/moderation/<target_type>/<int:target_id>/<action_name>", methods=["POST"])
@role_required("admin")
def action_alias(target_type, target_id, action_name):
    reason = request.form.get("reason", "").strip()[:2000]
    if not apply_moderation(target_type, target_id, action_name, reason):
        flash("Unknown moderation action.", "error")
    else:
        db.session.commit()
        flash("Moderation action completed.", "success")
    return redirect(url_for("moderation.queue"))


@moderation_bp.route("/moderation/reports/<int:report_id>/<action_name>", methods=["POST"])
@role_required("admin")
def report_action(report_id, action_name):
    report = db.get_or_404(Report, report_id)
    if action_name not in ("resolve", "dismiss", "reopen"):
        abort(400)
    report.status = {"resolve": "resolved", "dismiss": "dismissed", "reopen": "open"}[action_name]
    db.session.add(ModerationAction(
        moderator_id=current_user.id, target_type="report", target_id=report.id,
        action=action_name, reason=request.form.get("reason", "").strip()[:2000],
    ))
    db.session.commit()
    flash("Report updated.", "success")
    return redirect(url_for("moderation.queue"))


@moderation_bp.route("/jobs/<int:vid>/report", methods=["GET", "POST"])
@role_required("applicant", "recruiter", "reviewer")
def report_vacancy(vid):
    vacancy = db.get_or_404(Vacancy, vid)
    if request.method == "POST":
        reason = request.form.get("reason", "")
        details = request.form.get("details", "").strip()
        if reason not in REPORT_REASONS:
            flash("Choose a valid report reason.", "error")
            return redirect(url_for("moderation.report_vacancy", vid=vid))
        db.session.add(Report(reporter_id=current_user.id, vacancy_id=vacancy.id,
                              employer_id=vacancy.employer_id, reason=reason, details=details[:2000]))
        db.session.commit()
        flash("Report submitted. An administrator will review it.", "success")
        return redirect(url_for("main.vacancy_detail", vid=vid))
    return render_template("report.html", target=vacancy, target_type="vacancy", reasons=REPORT_REASONS)

@moderation_bp.route("/report/vacancy/<int:vid>", methods=["GET", "POST"])
@role_required("applicant", "recruiter", "reviewer")
def report_vacancy_alias(vid):
    return report_vacancy(vid)


@moderation_bp.route("/employers/<int:eid>/report", methods=["GET", "POST"])
@role_required("applicant", "recruiter", "reviewer")
def report_employer(eid):
    employer = db.get_or_404(Employer, eid)
    if request.method == "POST":
        reason = request.form.get("reason", "")
        details = request.form.get("details", "").strip()
        if reason not in REPORT_REASONS:
            flash("Choose a valid report reason.", "error")
            return redirect(url_for("moderation.report_employer", eid=eid))
        db.session.add(Report(reporter_id=current_user.id, employer_id=employer.id,
                              reason=reason, details=request.form.get("details", "").strip()[:2000]))
        db.session.commit()
        flash("Employer report submitted.", "success")
        return redirect(url_for("main.jobs"))
    return render_template("report.html", target=employer, target_type="employer", reasons=REPORT_REASONS)

@moderation_bp.route("/report/employer/<int:eid>", methods=["GET", "POST"])
@role_required("applicant", "recruiter", "reviewer")
def report_employer_alias(eid):
    return report_employer(eid)


@moderation_bp.route("/applications/<int:aid>/feedback", methods=["GET", "POST"])
@role_required("reviewer", "admin")
def reviewer_feedback(aid):
    application = db.get_or_404(Application, aid)
    if current_user.role == "reviewer" and current_user.employer_id != application.vacancy.employer_id:
        abort(403)
    if request.method == "POST":
        comments = request.form.get("comments", "").strip()
        recommendation = request.form.get("recommendation", "No recommendation")
        if len(comments) < 3:
            flash("Add feedback comments before saving.", "error")
        elif recommendation not in RECOMMENDATIONS:
            flash("Choose a valid recommendation.", "error")
        else:
            db.session.add(ReviewerFeedback(application_id=application.id,
                                            reviewer_id=current_user.id,
                                            comments=comments,
                                            recommendation=recommendation))
            db.session.commit()
            flash("Reviewer feedback saved.", "success")
            return redirect(url_for("vacancies.applicants", vid=application.vacancy_id))
    feedback = ReviewerFeedback.query.filter_by(application_id=application.id).order_by(
        ReviewerFeedback.created_at.desc()).all()
    return render_template("review_feedback.html", application=application,
                           feedback=feedback, recommendations=RECOMMENDATIONS)

@moderation_bp.route("/review/<int:aid>", methods=["GET", "POST"])
@role_required("reviewer", "admin")
def reviewer_feedback_alias(aid):
    return reviewer_feedback(aid)


@moderation_bp.route("/moderation/templates", methods=["POST"])
@role_required("admin")
def create_template():
    name = request.form.get("name", "").strip()
    subject = request.form.get("subject", "").strip()
    body = request.form.get("body", "").strip()
    if not name or not subject or len(body) < 10:
        flash("A template needs a name, subject and body.", "error")
    else:
        db.session.add(DecisionTemplate(name=name[:100], subject=subject[:150], body=body[:5000]))
        db.session.commit()
        flash("Decision template created.", "success")
    return redirect(url_for("moderation.queue"))


@moderation_bp.route("/moderation/templates/<int:tid>/delete", methods=["POST"])
@role_required("admin")
def delete_template(tid):
    template = db.get_or_404(DecisionTemplate, tid)
    db.session.delete(template)
    db.session.commit()
    flash("Decision template deleted.", "success")
    return redirect(url_for("moderation.queue"))
