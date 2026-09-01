"""
Central config, read from environment variables (or a .env file locally).

Why this file exists separately: hardcoding a DB password or secret key
inside main.py means it ends up in Git history forever. Keeping it here,
reading from env vars, means the actual secrets live in a `.env` file
that's in .gitignore -- never committed.
"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Postgres connection string, e.g.
    # postgresql+psycopg2://user:password@localhost:5432/findit_campus
    database_url: str = "postgresql+psycopg2://postgres:postgres@localhost:5432/findit_campus"

    # Used to sign JWT tokens for auth -- change this in your local .env,
    # never commit a real secret here.
    secret_key: str = "dev-secret-change-me"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24  # 1 day

    # Where uploaded report photos get saved on disk (swap for S3/Cloudinary later)
    upload_dir: str = "uploads"

    # Base URL of the deployed frontend -- used to build the link a QR tag
    # encodes (GET /reports/{id}/qr-code). Must be set to the real deployed
    # URL in production; localhost is fine for dev.
    frontend_base_url: str = "http://localhost:5173"

    # SMTP -- blank by default so local dev without real credentials still
    # works (core/email.py falls back to printing the email to the
    # console). Set these in your real .env once you have them; see
    # core/email.py's docstring for how to get a Gmail app password.
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""

    class Config:
        env_file = ".env"


settings = Settings()