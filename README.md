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
- A chat widget backed by Google Gemini (`gemini-3.1-flash-lite`) with function calling (Fill by Voice uses `gemini-3.5-flash-lite`)
- Can create a lost/found report, search for matches, and explain how verification/custody/high-risk handling work, asking one clarifying question at a time
- Admin users get extra tools through the same chat: a dashboard summary, a list of pending pickups, and confirming a handover

### Fill by Voice (English only)
- A **Fill by Voice** button sits at the right of the report form's header, beside Back. Clicking it opens a voice panel: the assistant speaks a greeting in a female English voice (when the device has one), listens, fills the form, and asks for everything still missing in one spoken request. Every field stays editable by hand
- Hands-free until the form is complete: it listens again after each reply while required details are missing, then stops. Tap the microphone any time to say more, for example "change the colour to blue" (a spoken change may replace text you typed; otherwise typed text is never overwritten). The conversation is hidden behind a **Show transcript** button
- Nothing is submitted automatically: if you say "submit", the assistant asks you to review the form and press **Submit report** yourself. That button is the only way to save a report and still goes through `POST /reports/`
- Speech-to-text uses the browser's Web Speech API and spoken replies use the browser's speech synthesis (no extra API key or paid service). Locale is the single constant `SPEECH_LOCALE` (`en-IN`) in `frontend/src/hooks/useSpeechRecognition.js`; the voice is chosen in `frontend/src/utils/speechVoice.js`
- Interpretation reuses the existing Gemini setup through one extraction-only endpoint, `POST /voice-form/extract` (login required, no tools, per-user rate limit, output re-validated on the server, nothing stored or logged)
- Found items: the collection point (PRP, SJT or TT) is collected by voice; the verification question can be spoken but the answer is always typed and is never sent to Gemini by this feature. Found reports now require a collection point on the server as well
- **Browser support:** works in Chromium browsers (Chrome, Edge) and some Safari versions; Firefox generally has no support. Unsupported browsers, a denied microphone, or an unavailable Gemini service show a message and leave the manual form usable. The voice you hear depends on the device and browser
- **Privacy and cost:** speech recognition is not guaranteed to be free, private or offline. In Chrome the audio is sent to Google's speech service and an internet connection is required. The transcript is then sent to this app's server and to Gemini. Gemini free-tier limits depend on your project; check them at https://aistudio.google.com/rate-limit. If the quota is exhausted the assistant says so and the manual form still works

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
│   │   │                     # train_calibrator.py, redaction.py,
│   │   │                     # verification_guard.py, leak_check.py
│   │   ├── models/            # Report, Match, CustodyRecord, User, Building
│   │   ├── routers/            # auth, reports, matches, custody, chatbot, voice_form
│   │   ├── voice/               # Gemini extraction for Fill by Voice
│   │   ├── realtime.py           # Socket.IO server
│   │   ├── main.py                # FastAPI + Socket.IO entrypoint, startup migrations
│   │   └── seed_admins.py          # bootstrap admin accounts
│   ├── tests/               # test_voice_form.py (pytest), test_fusion_and_calibration.py (script)
│   ├── export_labelled_pairs.py   # export confirmed/rejected pairs from the DB
│   ├── generate_evaluation.py      # build docs/evaluation reports
│   ├── labelled_pairs.csv           # exported evaluation data
│   └── requirements.txt / requirements-dev.txt
├── frontend/
│   ├── src/
│   │   ├── api/            # REST client, socket client
│   │   ├── components/      # header, chat widget, voice assistant, modals, etc.
│   │   ├── context/           # auth context
│   │   ├── hooks/               # speech recognition, theme
│   │   ├── pages/                # Landing, Dashboard, ReportForm, Matches,
│   │   │                         # ClaimedItems, Admin, Login, etc.
│   │   └── utils/                 # buildings, categories, leak-check, voice helpers
│   └── package.json
└── docs/
    ├── evaluation/          # generated evaluation reports and plots
    └── paper/                # paper draft and figures
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
SECRET_KEY=change-me   # use a long random value in production; the default is insecure
FRONTEND_BASE_URL=http://localhost:5173
CORS_ORIGINS=http://localhost:5173,http://localhost:3000

SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your.address@gmail.com
SMTP_PASSWORD=your-16-char-app-password
SMTP_FROM=your.address@gmail.com

GEMINI_API_KEY=your-gemini-key
```

Run `python -m app.seed_admins` (from `backend/`) once to create the admin accounts.

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

Set `VITE_API_BASE_URL` in `frontend/.env` if the API is not at `http://localhost:8000`.

### Tests

```bash
cd backend && pip install -r requirements-dev.txt && pytest tests/test_voice_form.py
cd backend && python tests/test_fusion_and_calibration.py   # print-based sanity checks
cd frontend && npm test
```

---

## Evaluation Status

`backend/tests/test_fusion_and_calibration.py` is a sanity-check script (not an asserting test suite) for the scoring math: weights renormalize to 1.0, a missing photo redistributes the image weight, a text-only report collapses to a text weight of 1.0, disambiguation clustering on clear-leader / three-way-tie cases, and Platt calibrator monotonicity with a reportable ECE.

Evaluation reports live in [`docs/evaluation/`](docs/evaluation/): fused vs text-only/image-only precision-recall, calibration (ECE and reliability curve), disambiguation impact, and a missing-modality ablation. They are generated from only **8 real labelled pairs** (7 matches, 1 rejection) exported from the live database, so the results are preliminary. A larger evaluation needs more confirmed handovers and rejections, ideally from a semester-long pilot.

---

## Team

- Mehwish
- Mansi Sharma
- Aarushi Chaudhary 

Faculty guide: Dr. Baskaran P

---

## License

All rights reserved. This project is for academic and research purposes.
