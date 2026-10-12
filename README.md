# AttendX — QR Attendance Management System

Beginner-friendly Flask + SQLite/PostgreSQL web application with a white responsive UI.

## Features included
- Student signup and separate Student / Teacher login selection.
- Admin-provisioned teacher/admin accounts (public signup cannot self-assign privileged roles).
- Teacher subject creation, student enrollment by registered email, QR attendance sessions.
- QR payload rotates every 20 seconds; signed tokens expire after 20 seconds and the previous token is invalidated.
- Students who scan while logged out are asked to log in; the scanned token is carried through login.
- Attendance marked automatically after a logged-in student scans a valid QR and is enrolled in the subject.
- Duplicate attendance protection for a session.
- Student overall and per-subject attendance history / percentages.
- Teacher student lookup by name/email, limited to students enrolled in the teacher's subjects.
- Attendance correction request and teacher/admin review workflow.
- CSV attendance export and audit log.
- Admin dashboard and account provisioning.
- SQLite for local testing; PostgreSQL URL support for deployment.
- Basic automated tests.

## Run locally (Python 3.10+)
1. Extract ZIP and open the `AttendX` folder in VS Code.
2. Create a virtual environment:
   - Windows: `py -m venv .venv` then `.venv\\Scripts\\activate`
   - macOS/Linux: `python3 -m venv .venv` then `source .venv/bin/activate`
3. Install dependencies: `pip install -r requirements.txt`
4. Open `info.py` and set `SECRET_KEY`, `ADMIN_EMAIL`, and `ADMIN_PASSWORD`. Replace both `CHANGE-ME` values before using the app. The admin account is created on first run only when both email and password are configured and the email does not already exist.
5. Run `python app.py`.
6. Open `http://127.0.0.1:5000`.

An initial admin is created only when both `ADMIN_EMAIL` and `ADMIN_PASSWORD` are configured and that email does not already exist. For hosted deployment, environment variables can override `info.py` settings; configure secrets in the host dashboard rather than committing real secrets.

## Deploy to Heroku
Heroku's availability and pricing can change; create an app in your Heroku account first.
1. Extract the ZIP, open terminal in `AttendX`.
2. Install Git and the Heroku CLI and sign in: `heroku login`.
3. Create app: `heroku create your-unique-app-name`.
4. Add a managed PostgreSQL add-on from the Heroku dashboard / marketplace.
5. Configure `SECRET_KEY`, `ADMIN_EMAIL`, `ADMIN_PASSWORD`, and `COOKIE_SECURE=1` in the Heroku app settings (Config Vars). These environment variables override `info.py` and are safer for deployed secrets.
6. Initialize Git and deploy:
   `git init`
   `git add .`
   `git commit -m "Initial AttendX deployment"`
   `heroku git:remote -a your-unique-app-name`
   `git push heroku main`
   If your local branch is `master`, use `git push heroku master:main`.
7. Open the deployed app with `heroku open`.

**Important:** Use PostgreSQL in hosted environments. Ephemeral app filesystems may reset, so SQLite is for local development only. Never commit real secrets or share admin credentials. Do not use the sample `CHANGE-ME` values in production. Set a strong secret key. Configure email delivery separately if you need real email notifications.

## QR security notes
The token is signed, tied to an attendance session, stored as a hash, and expires after 20 seconds. The server invalidates the prior token on rotation. A rotating QR discourages old screenshot reuse but does **not** prove physical presence by itself: someone can still relay a live QR remotely. Consider teacher confirmation, a classroom-only network, location checks with consent, or a second-factor challenge for higher assurance. Do not treat browser geolocation as tamper-proof.

## Email behavior
The app displays a helpful “not enrolled / account not found” message. It does not send real email automatically yet because that requires an SMTP/provider account and secrets. For real mail, configure a transactional email provider and add verified delivery, rate limits, and bounce handling. Do not claim an email was sent unless the provider confirms it.

## Run tests
`python -m unittest discover -s tests -v`

## Limitations before production
- Add CSRF protection, rate limiting, email verification, password reset and an actual transactional email provider.
- Run migrations (e.g. Flask-Migrate) when schema changes instead of relying on `create_all`.
- Add college SIS integration only after the institution approves credentials and data access.
- Add monitoring, backups, privacy notice, retention policy and security review.
