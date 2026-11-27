# InRole: job recruitment website

COMP3019J team project (Team Clovers). InRole connects employers that advertise vacancies with applicants, and gives employer staff and administrators the tools to keep decisions consistent and listings trustworthy.

Built with Flask, Flask-SQLAlchemy (SQLite), Flask-Login and Jinja templates, with plain JavaScript for live filtering. Tests use pytest.

## Run it (Windows PowerShell)
```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt -r requirements-dev.txt
py run.py
```
Open http://127.0.0.1:5000. If PowerShell blocks `Activate.ps1`, run `Set-ExecutionPolicy -Scope Process Bypass` first.

On macOS or Linux, use `python3 -m venv .venv` and `source .venv/bin/activate`.

## Run the tests
```powershell
py -m pytest
```
Each test builds a fresh in-memory database, so your demo data is not touched.

## Demo accounts
All demo accounts use the password `InRole123!`.

| Role | Email | Notes |
|---|---|---|
| Applicant | applicant@inrole.demo | Has applied to "Frontend Developer Intern" |
| Recruiter | recruiter@inrole.demo | Northstar Technologies (verified) |
| Reviewer | reviewer@inrole.demo | Northstar Technologies, read-only plus feedback |
| Administrator | admin@inrole.demo | Moderation queue |
| Recruiter (unverified) | pending.recruiter@inrole.demo | Harbour Digital: can draft but not publish |
| Applicants | candidate01@inrole.demo to candidate14@inrole.demo | Applications in every stage |

## Resetting the database
The database is `instance/inrole.db` and is created and seeded on first run. `app/schema_migrations.py` adds new columns to an older database automatically. If something still looks wrong after pulling, stop the server and delete the file:
```powershell
Remove-Item instance\inrole.db
```

## Included
- InRole logo and matching navy / blue / teal visual identity.
- Homepage banner, search bar, feature sections and sample job cards.
- Job search and vacancy detail pages.
- Register, log in and log out.
- Four role-specific dashboards and role-restricted applicant profile.
- Applicant CV upload (PDF, DOC or DOCX; 5 MB max) into `private_uploads/`, outside public static files.
- CV-backed applications with duplicate and vacancy-closing validation, applicant status timelines, recruiter status updates, and applicant withdrawal.
- Application and status-event records alongside the SQLite User, Employer, Vacancy and Application models.

## Important prototype limits
This is a **rough working prototype**, not a production recruitment platform. The demo supports the foundation, vacancy management, CV-backed applications, applicant timelines, recruiter status updates, reviewer feedback, reporting and administrator moderation. Email notifications, interview booking and messaging are not implemented.

The demo uses session-backed CSRF tokens, including for JSON status updates. For production, strengthen secret management and add operational controls such as rate limiting and audit retention. CV access is restricted to the applicant, an administrator, or recruiter/reviewer staff belonging to the application's vacancy owner.

## Structure
- `app/auth.py` — registration and login
- `app/main.py` — homepage, jobs, dashboards, applications, status updates, withdrawal and CV routes
- `app/application_rules.py` — allowed application status transitions
- `app/models.py` — User, Employer, Vacancy, Application and StatusEvent
- `app/templates/` — Jinja pages
- `app/static/css/style.css` — brand styling
- `app/static/js/main.js` — small UI enhancement
- `tests/test_applications.py` — application workflow tests
- `private_uploads/` — private CV storage

## Features and owners
| Area | Owner | Features |
|---|---|---|
| Accounts, security, foundation | M | F1 register / log in / log out, F2 role-based access, F3 profile and private CV (R8), CSRF, layout, error pages, tests |
| Vacancies and applicant lists | J | F4 manage vacancies (R1, R2, R6), F5 search and live filter, F6 vacancy detail, F9 applicant list, optimistic locking |
| Applications and status | H | F7 apply, F8 applicant timeline, F10 status updates, F14 withdraw |
| Review and moderation | S | F15 reviewer feedback, F11 reports, F12 moderation queue, F13 removal handling, F16 decision templates |

## Security rules every page follows
- **Roles:** use `@role_required("recruiter", ...)` from `app/main.py` on any route that is limited to certain roles. It sends anonymous users to log in and returns 403 for the wrong role.
- **CSRF:** every POST, PUT, PATCH and DELETE request is checked (`app/csrf.py`). In a form, add:
  ```html
  <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
  ```
  For JavaScript `fetch()` calls, send the header `X-CSRFToken` with the value of `<meta name="csrf-token">`:
  ```js
  fetch(url, {method: "POST", headers: {"X-CSRFToken": document.querySelector('meta[name="csrf-token"]').content}, ...})
  ```
  In tests, use the `post()`, `login()` and `logout()` helpers from `tests/conftest.py`; they add the token for you.
- **Log out** is POST-only. Use the button in the header, or `logout(client)` in tests.
- **Private CVs (R8)** are stored in `private_uploads/`, outside the public `static` folder. `/private-cv/<id>` only serves a CV to its owner, an admin, or recruiters and reviewers of an employer the applicant has applied to.
- **Passwords** are stored as salted hashes (Werkzeug), never as plain text.
- **Secret key:** set the `SECRET_KEY` environment variable for any shared or deployed copy. The built-in key is for local demos only.

## Project layout
```
app/
  __init__.py          create_app(), blueprints, demo seed
  models.py            User, Employer, Vacancy, Application, Report, ReviewerFeedback, ...
  auth.py              F1 accounts (M)
  main.py              home, jobs, vacancy detail, dashboard, profile and CVs, error pages
  vacancies.py         F4 and F9 (J);  vacancy_rules.py holds the vacancy business rules
  moderation.py        F11, F12, F13, F15, F16 (S)
  csrf.py              CSRF protection for every form
  schema_migrations.py adds new columns to older databases
  seed_vacancies.py    extra demo data
  templates/  static/
private_uploads/       CV files (never committed)
tests/                 pytest suite
```

## Working rules
One branch per feature, small commits with clear messages, and a pull request reviewed by a teammate before merging into `main`. `main` must always run and pass `py -m pytest`.
