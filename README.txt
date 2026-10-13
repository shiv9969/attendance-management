AttendX Teacher Dashboard update — changed files only

Files included:
- app.py (teacher-specific dashboard routes, subject editing, QR scan attendance flow, student analytics)
- templates/teacher_dashboard.html
- templates/teacher_section.html
- templates/student_detail.html
- templates/qr.html
- templates/scan_identity.html (new)

Replace app.py in the project root and the listed templates in templates/.
No college_admin.html or other college dashboard templates are included or modified.

Validation performed: Python syntax compilation passed. This package has not been tested against your live Heroku/Neon database.
QR sessions rotate the QR token every 20 seconds, and the countdown is hidden. Non-logged-in scanners are asked for the registered student name and email; the student must match an active student record in the same college and be enrolled in the subject. This name/email check does not independently prove identity.
