AttendX QR attendance + database connection resilience patch

Files:
- app.py (replace project root app.py)
- templates/scan_identity.html (replace existing template)

Changes:
- QR link must be valid when first opened; the form gets a signed 120-second scan ticket.
- Form submission uses that ticket, so 20-second QR rotation does not interrupt typing.
- Attendance session must remain active; ticket does not survive a stopped/ended session.
- Duplicate attendance integrity conflicts are handled gracefully.
- SQLAlchemy engine enables pool_pre_ping and recycles pooled connections to reduce stale hosted PostgreSQL connections.

Important:
- This reduces one common cause of intermittent 500s (stale DB connections) but does NOT prove the root cause. Check Heroku logs at the time of the next 500 for the exact traceback.
- No College Admin HTML templates or college routes were intentionally changed.
- Make a backup before replacing app.py.
