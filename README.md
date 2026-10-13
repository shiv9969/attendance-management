# AttendX — updated registration and college dashboard

## What's included
- Login uses **email + password only**. The login page and backend no longer require a college/unique code.
- Student CSV upload automatically generates a distinct `STUXXXXXX` code for each roster record.
- College admin can view student details and their codes, copy a code, and export the roster/codes to CSV.
- College admin can automatically generate one-use `TCHXXXXXX` teacher registration codes.
- Teacher registration requires a generated teacher code; after registration, login uses email/password. College admin approval remains required.
- Teacher account details show each teacher's unique code.
- College admin can add subjects manually, enter subject names/codes, and assign each subject to an approved teacher.
- White background and light-blue button styling.
- Additive startup migration adds `unique_code` columns to existing `user` and `student_roster` tables and backfills codes where possible.

## Setup
1. Install packages: `pip install -r requirements.txt`
2. Set environment variables before deploying: `SECRET_KEY`, `DATABASE_URL`, `ADMIN_EMAIL`, `ADMIN_PASSWORD`. Configure SMTP (`SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`) for student email OTP.
3. Use your hosting provider's config vars for secrets. Do not commit database URLs, email app passwords, or real admin passwords.
4. Deploy the project and test signup/login in a staging environment first.

## CSV format
Required columns: `student_id,name,email`. Optional columns: `department,year,division`.
After import, use **Download student codes CSV** in the college dashboard to distribute unique codes securely to each student.

## Notes
- Teacher registration codes are one-use and should be shared only with the intended teacher.
- Existing database data is retained; however, as with any schema change, take a database backup before deploying.
- Python syntax compilation succeeded in this environment. Automated tests could not run here because Flask dependencies are not installed in the execution environment.
