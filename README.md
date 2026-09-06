# FindIt Campus

A geo-temporal fusion framework for intelligent lost-and-found matching on a college campus.

## Overview

FindIt Campus is a multi-modal lost-and-found platform for VIT. It replaces
informal recovery methods (WhatsApp groups, notice boards, walking desk to
desk) with a structured system that scores lost reports against found
reports using text, images, location, and time, and walks an owner through
a verified claim and a recorded physical handover.

The core idea: a raw similarity number means nothing to a student, so every
signal is fused into one composite score, and (once there is labelled data)
that score is calibrated into an interpretable match probability.

---

## Key Features

### Multi-modal matching

* Text descriptions encoded with Sentence-Transformers (`all-MiniLM-L6-v2`, 384-d)
* Photos encoded with OpenCLIP (`ViT-B-32`, openai weights, 512-d), mean-pooled
  across a report's photos so one blurry shot doesn't sink the match
* Handles wording differences ("black wallet" vs "dark brown leather wallet")

### Geo-temporal fusion

* Composite score = weighted sum of text similarity, image similarity,
  location proximity (exponential decay, ~300 m half-life), and time
  proximity (exponential decay, ~48 h half-life)
* When a signal is missing (no photo, no coordinates), its weight is
  redistributed across the signals that are present rather than penalising
  the pair
* Every match records which signals were used and their weights, so a
  low-confidence result can be explained ("matched on text + location only")

### Confidence-calibrated scoring

* A Platt-scaling calibrator (`scikit-learn` logistic regression on the
  composite score) converts the raw score into a 0–1 match probability
* Reliability is measured with Expected Calibration Error
* **Status:** the calibrator is trained offline from confirmed matches
  (`python -m app.matching.train_calibrator`). Until at least 20 confirmed
  matches exist, no calibrator is persisted and the UI falls back to the
  raw score / ranking.

### Smart disambiguation

* If the top candidates are within a small margin of each other *and* the
  leader clears a minimum plausibility score, the system asks a targeted,
  rule-based follow-up question instead of guessing
* The owner picks their item in a forced-choice UI; the rest of the
  competing cluster is rejected

### Asymmetric verification

* A found report carries a hidden verification question and answer that
  never appear in the public listing
* Only the person who filed the matching lost report can attempt a claim;
  they must answer the finder's question (checked server-side, case- and
  whitespace-insensitive)
* Contact details are revealed only after a successful claim
* Online attempts are limited to 3; after that the claim locks and the only
  way forward is in-person verification at the desk

### Verification-answer leak guards

* A deterministic check rejects a found report whose verification answer is
  already recoverable from its public title/description/attributes
* An additional LLM advisory check (Google Gemini) catches the semantic
  cases the string check misses; it is advisory only and fails open

### Custody ledger and handover flow

* A correct online answer moves the match to `VERIFIED` — the item is still
  with the admin, not yet handed over
* An admin confirms the physical handover in person, which writes an
  immutable `CustodyRecord` (item, claimant, verifier, timestamp), marks
  both reports `RESOLVED`, and emails the finder
* An admin can also complete verification on a locked-out claimant's behalf
  once they've proven ownership at the desk

### High-risk item handling

* IDs, phones, laptops, and academic documents are auto-flagged high-risk
* Their photos are pixelated in the public listing; the clear originals are
  kept privately for matching and revealed only at handover
* High-risk found items left unclaimed for 7+ days can be escalated by an
  admin (no scheduler yet — triggered from the dashboard)

### Collection-point routing (PRP / SJT)

* Each found item is assigned one of two collection points
* Each admin is tied to one collection point and only sees the pickup queue
  for items physically held at their own desk

### Accounts and roles

* College-email-only access (`@vitstudent.ac.in`, `@vit.ac.in`)
* Passwordless signup: a temporary password is emailed, then a real
  password must be set on first login
* Regular users see only the reports they filed; admins (seeded separately)
  see reporter identities and the handover queue

### Conversational assistant

* A chat widget backed by Google Gemini with tool-calling can file a lost
  or found report, search for matches, and — for admins — summarise the
  dashboard and confirm a handover, reusing the same REST endpoints as the
  UI

### Real-time notifications

* Socket.IO events for new reports, escalations, verified claims, and
  handovers, broadcast to all connected clients
* Email on the one-time "possible match found" event and on a completed
  handover

### Progressive Web App

* Installable, with an app-shell precache so the UI loads on flaky campus
  wifi; lost-and-found data itself is always fetched live

---

## Tech stack

### Frontend

* React 18 + Vite
* React Router
* `socket.io-client` for live updates
* `vite-plugin-pwa` (service worker + web manifest)

### Backend

* FastAPI, served as a combined ASGI app with `python-socketio`
* SQLAlchemy 2.x ORM
* PyJWT for auth tokens
* SMTP email (falls back to printing to the console when unconfigured)

### Database

* PostgreSQL with the `pgvector` extension (embeddings stored as `vector`
  columns for in-database similarity search)

### AI / ML

* `sentence-transformers` — text embeddings
* `open_clip_torch` — image embeddings
* `scikit-learn` — score calibration (Platt scaling) and calibration metrics
* `google-genai` — chatbot tool-calling and the verification leak advisory

---

## Project structure

```
FindIt-Campus/
├── backend/
│   ├── app/
│   │   ├── core/         # config, security (JWT/hashing), email
│   │   ├── db/           # SQLAlchemy engine / session
│   │   ├── matching/     # embeddings, fusion, calibration, redaction, leak checks
│   │   ├── models/       # Report, Match, CustodyRecord, User, Building
│   │   ├── routers/      # auth, reports, matches, custody, chatbot
│   │   ├── main.py       # FastAPI + Socket.IO entrypoint
│   │   ├── realtime.py   # Socket.IO server + events
│   │   └── seed_admins.py
│   ├── tests/
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── api/          # REST client, socket client
│   │   ├── components/   # Header, ChatWidget, Modal, toasts, ...
│   │   ├── context/      # AuthContext
│   │   ├── hooks/        # useTheme
│   │   ├── pages/        # Landing, Dashboard, ReportForm, Matches, Admin, auth pages
│   │   ├── styles/
│   │   └── utils/        # buildings, leak-check helper
│   ├── index.html
│   └── vite.config.js
├── database/
│   └── migrations/       # reserved for Alembic (not yet wired up)
└── docs/
    ├── diagrams/
    └── evaluation/
```

---

## Setup

### Prerequisites

* Python 3.11+
* Node.js 18+
* PostgreSQL 14+ with the `pgvector` extension available
  (`CREATE EXTENSION IF NOT EXISTS vector;` in the target database)

### 1. Clone

```bash
git clone <repo-url>
cd FindIt-Campus
```

### 2. Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

Create `backend/.env`:

```env
DATABASE_URL=postgresql+psycopg2://postgres:postgres@localhost:5432/findit_campus
SECRET_KEY=change-me
FRONTEND_BASE_URL=http://localhost:5173

# Optional — email. If blank, emails are printed to the console instead.
SMTP_HOST=
SMTP_PORT=587
SMTP_USER=
SMTP_PASSWORD=
SMTP_FROM=

# Optional — enables the chatbot and the LLM verification advisory.
GEMINI_API_KEY=
```

Run the API (tables are auto-created on startup):

```bash
uvicorn app.main:app --reload --port 8000
```

Interactive API docs: http://127.0.0.1:8000/docs

Seed the two admin accounts (prints their temporary passwords):

```bash
python -m app.seed_admins
```

### 3. Frontend

```bash
cd frontend
npm install
npm run dev
```

The dev server runs on http://localhost:5173 and expects the API at
`http://localhost:8000` (override with `VITE_API_BASE_URL` in
`frontend/.env`).

### 4. Tests

```bash
cd backend
python tests/test_fusion_and_calibration.py
```

Covers the fusion scoring math, the disambiguation clustering, and the
calibrator — the parts that don't need model downloads.

---

## Evaluation

Planned evaluation artifacts live under `docs/evaluation/`:

* Precision / recall vs text-only and image-only baselines
* Reliability diagrams and Expected Calibration Error
  (`MatchCalibrator.expected_calibration_error()`)
* Impact of disambiguation on claim accuracy
* Match quality with a missing modality (text-only vs text + image)

---

## Roadmap

* Alembic migrations to replace the startup `create_all()` + ad-hoc `ALTER`s
* Per-user Socket.IO rooms so notifications target the right person
* Background queue for embedding computation so report creation returns instantly
* Scheduled escalation sweep (currently manual)
* Object storage for photos instead of local disk

---

## Team

* Mehwish
* Mansi Sharma
* Aarushi Chaudhary

---

## License

For academic and research purposes.
