"""Central configuration for AttendX. Edit this file for local testing.

For hosted deployments, environment variables override these defaults so secrets
can be configured in the hosting dashboard instead of committed to source control.
"""

# Generate a long random value before deploying. Keep this value private.
SECRET_KEY = "shiv"

# Local testing uses SQLite. For hosting, set DATABASE_URL to your PostgreSQL URL.
DATABASE_URL = "postgresql://neondb_owner:npg_zpfEPnlk5N2y@ep-nameless-sunset-azpqdzr2-pooler.c-3.ap-southeast-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require"

# Optional initial admin account. Set both fields to create the admin on first run.
ADMIN_EMAIL = "shivamnavinmishra5678@gmail.com"
ADMIN_PASSWORD = "shiv"

# Set True when deployed behind HTTPS; keep False for localhost.
COOKIE_SECURE = True

# Development only: keep False unless debugging locally.
FLASK_DEBUG = False

# Hosting providers commonly supply PORT automatically.
PORT = 5000

# SMTP is required for student email OTP. Configure these values for real delivery.
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_USER = "shivamnavinmishra5678@gmail.com"
SMTP_PASSWORD = "roft ppgu fdfi vkqj"
SMTP_FROM = "shivamnavinmishra5678@gmail.com"
