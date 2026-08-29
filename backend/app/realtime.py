"""
Real-time layer, per your abstract's promise of "real-time notifications"
(match found, escalation, item claimed). Built on python-socketio's
AsyncServer, mounted alongside the FastAPI app (see main.py) so it shares
the same port/process -- no separate service to run or deploy.

Events emitted (all broadcast to every connected client -- there's no
per-user auth/rooms yet, since auth itself isn't wired up; see backlog
Task 8. Fine for a campus-scale tool where "everyone sees lost & found
activity" is the whole point):

  report:created   -- a new lost/found report was submitted
  report:escalated -- unclaimed high-risk item(s) got auto-escalated
  match:found       -- a strong candidate match was found for a report
  item:claimed      -- a claim was verified and the item changed custody

Kept intentionally thin: sio.emit() calls live next to the DB writes they
describe (in reports.py / matches.py), not centralized here, so it's
obvious which write triggers which notification.
"""

import socketio

sio = socketio.AsyncServer(
    async_mode="asgi",
    # Same origins as the CORS middleware in main.py -- Vite/CRA dev ports.
    cors_allowed_origins=["http://localhost:5173", "http://localhost:3000"],
)


@sio.event
async def connect(sid, environ):
    # No auth yet -- anyone can connect and listen. Revisit once accounts
    # exist (Task 8) if per-user targeting is ever needed.
    pass


@sio.event
async def disconnect(sid):
    pass