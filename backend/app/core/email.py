"""
Email sending -- used for:
  - first-time login: temp password (auth.py's request_access)
  - match found: notify the LOST reporter a candidate FOUND report exists
  - item claimed: notify the FOUND reporter someone claimed their item

Tries, in order:
  1. Brevo HTTP API (BREVO_API_KEY set) -- sends over HTTPS (port 443),
     which works even on hosts that block outbound SMTP ports (Render's
     free tier blocks 25/465/587 entirely as of Sept 2025). BREVO_SENDER
     just needs to be a single verified sender in Brevo (Senders & IP ->
     Senders, verify via the 6-digit code emailed to it) -- no domain
     purchase or DNS setup required, and once verified you can send to any
     recipient (unlike Resend's onboarding@resend.dev, which can only send
     to your own account email).
  2. Resend HTTP API (RESEND_API_KEY set) -- same HTTPS approach; note the
     resend.dev test sender can only deliver to your own Resend account
     email until you verify a domain there.
  3. SMTP (SMTP_HOST/SMTP_USER/SMTP_PASSWORD set) -- for hosts that do
     allow outbound SMTP.
  4. Console print -- so local dev without any of the above still works.

Brevo setup:
  1. Sign up at brevo.com.
  2. Senders & IP -> Senders -> add your sending address (e.g. your Gmail),
     verify it with the code emailed to it.
  3. SMTP & API -> API Keys -> create a key.
  4. In backend/.env (or your host's env vars):
       BREVO_API_KEY=xkeysib-xxxxxxxxxxxx
       BREVO_SENDER=your.verified.address@gmail.com

Never put real credentials in code or commit .env -- it should already be
gitignored.
"""

import json
import urllib.request
import urllib.error
import smtplib
from email.mime.text import MIMEText

from app.core.config import settings


def _send_via_brevo(to_email: str, subject: str, body: str) -> None:
    payload = json.dumps({
        "sender": {"name": settings.brevo_sender_name, "email": settings.brevo_sender},
        "to": [{"email": to_email}],
        "subject": subject,
        "textContent": body,
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://api.brevo.com/v3/smtp/email",
        data=payload,
        method="POST",
        headers={
            "api-key": settings.brevo_api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            resp.read()
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Brevo API error {e.code}: {detail}") from e


def _send_via_resend(to_email: str, subject: str, body: str) -> None:
    payload = json.dumps({
        "from": settings.resend_from,
        "to": [to_email],
        "subject": subject,
        "text": body,
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://api.resend.com/emails",
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {settings.resend_api_key}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            resp.read()
    except urllib.error.HTTPError as e:
        # Surface Resend's error body (e.g. unverified domain, bad from
        # address) instead of a bare HTTP status code.
        detail = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Resend API error {e.code}: {detail}") from e


def _send_via_smtp(to_email: str, subject: str, body: str) -> None:
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = settings.smtp_from or settings.smtp_user
    msg["To"] = to_email

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
        server.starttls()
        server.login(settings.smtp_user, settings.smtp_password)
        server.sendmail(msg["From"], [to_email], msg.as_string())


def send_email(to_email: str, subject: str, body: str) -> None:
    if settings.brevo_api_key and settings.brevo_sender:
        _send_via_brevo(to_email, subject, body)
        return

    if settings.resend_api_key:
        _send_via_resend(to_email, subject, body)
        return

    if settings.smtp_host and settings.smtp_user and settings.smtp_password:
        _send_via_smtp(to_email, subject, body)
        return

    print(
        f"\n----- [EMAIL STUB -- no BREVO/RESEND/SMTP configured, see core/email.py docstring] -----\n"
        f"To: {to_email}\nSubject: {subject}\n\n{body}\n"
        f"-------------------------------------------------------------------------\n"
    )