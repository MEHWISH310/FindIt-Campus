"""
SMTP email sending -- used for:
  - first-time login: temp password (auth.py's request_access)
  - match found: notify the LOST reporter a candidate FOUND report exists
  - item claimed: notify the FOUND reporter someone claimed their item

Reads SMTP_* from settings (see core/config.py) -- set these in your real
.env, never commit real credentials. Until they're set, this prints the
email to the console instead of failing, so local dev without SMTP
configured still works.

Setup notes (Gmail, simplest path for a college project):
  1. On the Google account that will send mail: turn on 2-Step
     Verification, then create an "App Password" (Google Account ->
     Security -> 2-Step Verification -> App passwords). Regular account
     passwords don't work here -- Gmail requires an app password for
     SMTP.
  2. In backend/.env:
       SMTP_HOST=smtp.gmail.com
       SMTP_PORT=587
       SMTP_USER=your.address@gmail.com
       SMTP_PASSWORD=<the 16-character app password, no spaces>
       SMTP_FROM=your.address@gmail.com
  3. Restart uvicorn -- send_email() picks up settings on import via
     app.core.config, so a plain reload is enough.
Never put real credentials in code or commit .env -- it should already be
gitignored.
"""

import smtplib
from email.mime.text import MIMEText

from app.core.config import settings


def send_email(to_email: str, subject: str, body: str) -> None:
    if not (settings.smtp_host and settings.smtp_user and settings.smtp_password):
        print(
            f"\n----- [EMAIL STUB -- SMTP not configured, see core/email.py docstring] -----\n"
            f"To: {to_email}\nSubject: {subject}\n\n{body}\n"
            f"-------------------------------------------------------------------------\n"
        )
        return

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = settings.smtp_from or settings.smtp_user
    msg["To"] = to_email

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
        server.starttls()
        server.login(settings.smtp_user, settings.smtp_password)
        server.sendmail(msg["From"], [to_email], msg.as_string())