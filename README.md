# InRole — Flask website starter

A working presentation prototype for the COMP3019J InRole project. It focuses on the shared foundation and M's assigned slice: accounts, login/logout, role-aware navigation, starter models, base layout and applicant CV upload.

## Run in Visual Studio Code (Windows)
1. Extract this ZIP.
2. Open the extracted `InRole_Website_Starter` folder in VS Code.
3. Open Terminal → New Terminal.
4. Run:
   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   python run.py
   ```
5. Open http://127.0.0.1:5000 in your browser.

If PowerShell blocks activation, use Command Prompt and run `.venv\Scripts\activate`.

## Demo accounts
Password for all accounts: `InRole123!`

| Role | Email |
|---|---|
| Applicant | applicant@inrole.demo |
| Recruiter | recruiter@inrole.demo |
| Reviewer | reviewer@inrole.demo |
| Administrator | admin@inrole.demo |

The first run seeds Northstar Technologies and three open demo vacancies. To reset, stop the server and delete `instance/inrole.db`.

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
