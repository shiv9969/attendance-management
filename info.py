"""Central configuration for AttendX. Edit this file for local testing.

For hosted deployments, environment variables override these defaults so secrets
can be configured in the hosting dashboard instead of committed to source control.
"""

# Generate a long random value before deploying. Keep this value private.
SECRET_KEY = "CHANGE-ME-to-a-long-random-secret-before-use"

# Local testing uses SQLite. For hosting, set DATABASE_URL to your PostgreSQL URL.
DATABASE_URL = "sqlite:///attendx.db"

# Optional initial admin account. Set both fields to create the admin on first run.
ADMIN_EMAIL = "admin@example.edu"
ADMIN_PASSWORD = "CHANGE-ME-to-a-strong-admin-password"

# Set True when deployed behind HTTPS; keep False for localhost.
COOKIE_SECURE = False

# Development only: keep False unless debugging locally.
FLASK_DEBUG = False

# Hosting providers commonly supply PORT automatically.
PORT = 5000
