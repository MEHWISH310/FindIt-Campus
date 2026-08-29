"""
FastAPI entrypoint. Run locally with:
    uvicorn app.main:app --reload --port 8000

Then open http://127.0.0.1:8000/docs for the auto-generated Swagger UI --
this is the fastest way to test the API without building the frontend yet.
"""

import os

import socketio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.db.session import Base, engine
from app.models import Report, Match, CustodyRecord  # noqa: F401 -- must import so tables register
from app.routers import reports_router, matches_router, custody_router
from app.realtime import sio

# Named fastapi_app (not `app`) because the ASGI entrypoint uvicorn actually
# serves needs to be the combined Socket.IO + FastAPI app below -- see the
# `app = socketio.ASGIApp(...)` line at the bottom. Everything about routes,
# middleware, and startup still happens on fastapi_app as normal.
fastapi_app = FastAPI(
    title="FindIt Campus API",
    description="Geo-temporal fusion matching for campus lost & found",
    version="0.1.0",
)

# Allow the React frontend (running on a different port during dev) to call this API
fastapi_app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],  # Vite / CRA defaults
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

fastapi_app.include_router(reports_router)
fastapi_app.include_router(matches_router)
fastapi_app.include_router(custody_router)


@fastapi_app.on_event("startup")
def on_startup():
    # Creates tables if they don't exist yet. Fine for early development --
    # switch to Alembic migrations (database/migrations/) before this gets
    # used with real data, since create_all() can't handle schema changes.
    Base.metadata.create_all(bind=engine)


# Photos are saved to disk under settings.upload_dir (see routers/reports.py's
# upload_photos endpoint) and served back out from here at /uploads/<report_id>/<file>.
# The folder must exist BEFORE StaticFiles is constructed (it checks at import
# time, not at request time), so this runs here rather than in on_startup above.
os.makedirs(settings.upload_dir, exist_ok=True)
fastapi_app.mount("/uploads", StaticFiles(directory=settings.upload_dir), name="uploads")


@fastapi_app.get("/")
def root():
    return {"status": "ok", "service": "FindIt Campus API"}


# Combined ASGI app: Socket.IO handles anything under /socket.io, everything
# else falls through to FastAPI via other_asgi_app. This is what uvicorn
# actually serves -- run it exactly as before:
#     uvicorn app.main:app --reload --port 8000
# The frontend's socket.io-client points at the same http://localhost:8000
# and the socket.io path is negotiated automatically.
app = socketio.ASGIApp(sio, other_asgi_app=fastapi_app, socketio_path="socket.io")