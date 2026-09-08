# FindIt Campus

A Geo-Temporal Fusion Framework for Intelligent Lost and Found Matching with Calibrated Confidence and Asymmetric Verification.

## Overview

FindIt Campus is a lost-and-found platform for a college campus. It replaces WhatsApp groups, notice boards, and a manned desk with a structured workflow: students file lost/found reports, the backend scores every open opposite-type report against them using text, image, location, and time signals, and surfaces ranked candidates with a calibrated match probability. Ownership is checked asymmetrically (a hidden question set by the finder), and every physical handover is written to an append-only custody ledger.

Access is restricted to verified college accounts (`@vitstudent.ac.in` / `@vit.ac.in`).

---

## Key Features

### Multi-Modal Matching
- Sentence-Transformers (`all-MiniLM-L6-v2`, 384-dim) for text descriptions
- CLIP (`ViT-B/32` via `open_clip`, 512-dim) for photos, mean-pooled across all photos on a report
- Embeddings are stored directly in Postgres via `pgvector`

### Geo-Temporal Fusion
- Composite score over six signals: text similarity, image similarity, geo-proximity, time-decay, category match, location match
- Geo-proximity decays exponentially with a ~300 m scale; time-decay with a ~48 hour scale; distance is computed with the haversine formula
- Base weights (text 0.20, image 0.25, geo 0.10, time 0.10, category 0.20, location 0.15) are renormalized over whichever signals are actually present, so a report missing a photo or coordinates doesn't get penalized — the weight is redistributed, not lost

### Structured Field Signals
- Exact-match and substring checks on the category and location fields, giving an explicit boost that short free-text embeddings often miss

### Confidence Calibration
- Platt scaling (`sklearn.LogisticRegression` on the composite score) turns a raw score into an interpretable match probability, trained on confirmed matches vs. their non-confirmed sibling candidates
- Expected Calibration Error (ECE) routine to validate calibration quality
- Until a calibrator has been trained (needs a minimum number of confirmed matches) the API falls back to showing the raw score/ranking

### Smart Disambiguation
- When the top candidates fall within a 0.05 score margin of each other (and the leading score is at least 0.5), the system raises a targeted, rule-based differentiating question and lets the user pick by forced choice, instead of silently auto-ranking

### Asymmetric Verification
- The finder sets a private challenge question/answer when filing a found report
- A claimant must answer it correctly before any contact details are revealed
- Three failed attempts locks online claiming; recovery is an admin verifying the claimant in person at the collection desk
- The verification answer is checked against the report's own public description to stop the finder from picking a question whose answer is already visible

### Custody Ledger
- Every confirmed handover (item, claimant, verifier, timestamp, collection point) is written to an append-only `CustodyRecord`, visible on a "Claimed items" page

### High-Risk Item Handling
- ID cards, phones, laptops, and academic documents are auto-flagged as high-risk on report creation
- Their photos are pixelated on the public route and swapped back to the original only once a claim is verified — the full-resolution original is always used for matching, so redaction never degrades match quality
- Unclaimed high-risk found items are auto-escalated after 7 days via an admin-run check; other lost reports go "stale" after 14 days and are pushed down in listings

### Real-Time Notifications
- Socket.IO ping the moment a new report crosses the match-notification threshold, plus an email (SMTP) for the same event and for a successful claim
- Notification fires once, at report-creation time — not every time someone reopens the matches page, to avoid duplicate emails

### Conversational Assistant
- A chat widget backed by Google Gemini (`gemini-3.1-flash-lite`) with function calling
- Can create a lost/found report, search for matches, and explain how verification/custody/high-risk handling work, asking one clarifying question at a time
- Admin users get extra tools through the same chat: a dashboard summary, a list of pending pickups, and confirming a handover

### Role-Based Views
- Admins are each tied to a collection point (PRP, SJT, or TT) and see pending pickups, escalations, and can verify/confirm handovers for their desk
- Non-admin users see a restricted "My Claimed Items" view scoped to their own reports/claims

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | React (Vite), PWA (`vite-plugin-pwa`), `react-router-dom`, `axios`, `socket.io-client` |
| Backend | FastAPI (Python) |
| Database | PostgreSQL + `pgvector` (report metadata, embedding vectors, custody records) |
| Text encoding | Sentence-Transformers (`all-MiniLM-L6-v2`) |
| Image encoding | CLIP (`open_clip`, `ViT-B/32`) |
| Calibration | scikit-learn (Platt scaling / logistic regression) |
| Auth | JWT (`PyJWT`), college-domain-restricted signup with temporary-password onboarding |
| Real-time | Socket.IO (`python-socketio`) |
| Email | SMTP |
| Conversational assistant | Google Gemini (`google-genai`), function calling |

---

## Project Structure

```
FindIt-Campus/
├── backend/
│   ├── app/
│   │   ├── core/           # config, email, security/auth helpers
│   │   ├── db/              # SQLAlchemy session/engine
│   │   ├── matching/         # fusion.py, embeddings.py, calibration.py,
│   │   │                     # redaction.py, verification_guard.py, leak_check.py
│   │   ├── models/            # Report, Match, CustodyRecord, User, Building
│   │   ├── routers/            # reports, matches, custody, auth, chatbot
│   │   ├── main.py               # FastAPI + Socket.IO entrypoint
│   │   └── seed_admins.py         # bootstrap admin accounts
│   ├── tests/
│   │   └── test_fusion_and_calibration.py
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── api/            # REST client, socket client
│   │   ├── components/      # header, chat widget, modals, notifications, etc.
│   │   ├── context/           # auth context
│   │   ├── pages/               # Landing, Dashboard, ReportForm, Matches,
│   │   │                        # ClaimedItems, Admin, Login, etc.
│   │   └── utils/                # buildings, leak-check helpers
│   └── package.json
├── database/
│   └── migrations/          # placeholder — schema currently managed by
│                              # SQLAlchemy create_all() + additive ALTERs on startup
└── docs/
    ├── diagrams/
    └── evaluation/
```

---

## Setup Instructions

### Backend

```bash
cd backend
pip install -r requirements.txt
```

Create a `.env` file in `backend/` (never commit it):

```
DATABASE_URL=postgresql+psycopg2://postgres:postgres@localhost:5432/findit_campus
SECRET_KEY=change-me
FRONTEND_BASE_URL=http://localhost:5173
CORS_ORIGINS=http://localhost:5173,http://localhost:3000

SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your.address@gmail.com
SMTP_PASSWORD=your-16-char-app-password
SMTP_FROM=your.address@gmail.com

GEMINI_API_KEY=your-gemini-key
```

Requires a Postgres database with the `pgvector` extension enabled (`CREATE EXTENSION vector;`). Tables are created automatically on startup; a few additive column migrations also run automatically.

```bash
uvicorn app.main:app --reload --port 8000
```

API docs: `http://127.0.0.1:8000/docs`

### Frontend

```bash
cd frontend
npm install
npm run dev
```

---

## Evaluation Status

The fusion and calibration logic is covered by unit tests (`backend/tests/test_fusion_and_calibration.py`): weights always renormalize to 1.0, a missing photo redistributes the image weight across the remaining signals, a text-only report collapses to a text weight of 1.0, the disambiguation clustering behaves correctly on clear-leader / three-way-tie / empty-set boundary cases, and the Platt calibrator is monotonic with a reportable Expected Calibration Error.

Full quantitative evaluation — precision/recall/F1 against text-only and image-only baselines, calibration error and reliability diagrams, and a missing-modality ablation — is the next phase, to be run on a hand-labelled campus dataset alongside a semester-long pilot.

---

## Team

- Mehwish 
- Mansi Sharma
- Aarushi Chaudhary 

Faculty guide: Dr. Baskaran P

---

## License

This project is for academic and research purposes.
