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

    class Config:
        env_file = ".env"


settings = Settings()