"""
FastAPI entrypoint. Run locally with:
    uvicorn app.main:app --reload --port 8000

Then open http://127.0.0.1:8000/docs for the auto-generated Swagger UI --
this is the fastest way to test the API without building the frontend yet.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.db.session import Base, engine
from app.models import Report, Match, CustodyRecord  # noqa: F401 -- must import so tables register
from app.routers import reports_router, matches_router

app = FastAPI(
    title="FindIt Campus API",
    description="Geo-temporal fusion matching for campus lost & found",
    version="0.1.0",
)

# Allow the React frontend (running on a different port during dev) to call this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],  # Vite / CRA defaults
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(reports_router)
app.include_router(matches_router)


@app.on_event("startup")
def on_startup():
    # Creates tables if they don't exist yet. Fine for early development --
    # switch to Alembic migrations (database/migrations/) before this gets
    # used with real data, since create_all() can't handle schema changes.
    Base.metadata.create_all(bind=engine)


@app.get("/")
def root():
    return {"status": "ok", "service": "FindIt Campus API"}