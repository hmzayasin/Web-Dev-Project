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
- SQLite models for User, Employer and Vacancy.

## Important prototype limits
This is a **rough working skeleton**, not the complete recruitment platform. It supports the foundation and demo flows only. Full apply submission, application timeline / StatusEvent, recruiter vacancy management, reviewer notes, reporting and administrator moderation are not implemented yet; these belong to the other team workstreams. The detail-page apply action currently directs to the dashboard / account creation rather than submitting a real application.

For a production build, add CSRF protection (e.g. Flask-WTF), stronger secret configuration, and employer-staff CV access checks. In this demo, an applicant can access their own CV and an admin can access CVs; employer access is deliberately not enabled until ownership checks are integrated.

## Structure
- `app/auth.py` — registration and login
- `app/main.py` — homepage, jobs, dashboards, applicant profile and CV route
- `app/models.py` — User, Employer and Vacancy
- `app/templates/` — Jinja pages
- `app/static/css/style.css` — brand styling
- `app/static/js/main.js` — small UI enhancement
- `private_uploads/` — private CV storage
