"""
Exports REAL labelled pairs from your Neon Postgres DB for evaluation.

WHERE TO PUT THIS: backend/export_labelled_pairs.py (same folder as
backend/app/), so it reuses your existing app.db.session / app.core.config
-- which already reads DATABASE_URL from backend/.env. Nothing here needs
your connection string pasted anywhere; it just imports your app's own
DB session, same as running the server itself.

HOW TO RUN (on your machine, where .env lives):
    cd backend
    python export_labelled_pairs.py

This does NOT reload CLIP / Sentence-Transformers -- it reuses the
text_embedding / image_embedding vectors already stored on each Report row
(pgvector), exactly like matches.py does when scoring live matches, so it's
fast even with no GPU.

WHAT COUNTS AS A LABEL (only humans-confirmed outcomes, not system guesses):
  - Match.status in (VERIFIED, CONFIRMED) -> label = 1 (real confirmed match)
  - Match.status == REJECTED              -> label = 0 (real confirmed non-match)
  - CANDIDATE / NEEDS_DISAMBIGUATION      -> excluded (no human confirmation yet)

Writes backend/labelled_pairs.csv:
  text_sim, image_sim, distance_m, hours_apart,
  category_lost, category_found, location_lost, location_found, label

Then run:
    python generate_evaluation.py --csv labelled_pairs.csv
to build calibration_report.md / precision_recall.md / missing_modality_impact.md
from this real data instead of the synthetic fallback.
"""

import csv
import math
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from app.db.session import SessionLocal
from app.models.match import Match, MatchStatus
from app.models.report import Report
from app.matching.embeddings import cosine_sim


def haversine_meters(lat1, lon1, lat2, lon2):
    R = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


LABEL_MAP = {
    MatchStatus.VERIFIED: 1,
    MatchStatus.CONFIRMED: 1,
    MatchStatus.REJECTED: 0,
}


def main():
    db = SessionLocal()
    rows = []
    try:
        matches = db.query(Match).filter(Match.status.in_(list(LABEL_MAP.keys()))).all()
        for m in matches:
            lost = db.query(Report).filter(Report.id == m.lost_report_id).first()
            found = db.query(Report).filter(Report.id == m.found_report_id).first()
            if lost is None or found is None:
                continue

            text_sim = cosine_sim(lost.text_embedding, found.text_embedding)
            image_sim = cosine_sim(lost.image_embedding, found.image_embedding)

            distance_m = None
            if lost.latitude is not None and found.latitude is not None:
                distance_m = haversine_meters(lost.latitude, lost.longitude, found.latitude, found.longitude)

            hours_apart = None
            if lost.item_datetime and found.item_datetime:
                hours_apart = abs((lost.item_datetime - found.item_datetime).total_seconds()) / 3600

            rows.append({
                "text_sim": text_sim,
                "image_sim": image_sim,
                "distance_m": distance_m,
                "hours_apart": hours_apart,
                "category_lost": lost.category,
                "category_found": found.category,
                "location_lost": lost.location_name,
                "location_found": found.location_name,
                "label": LABEL_MAP[m.status],
            })
    finally:
        db.close()

    out_path = os.path.join(os.path.dirname(__file__), "labelled_pairs.csv")
    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "text_sim", "image_sim", "distance_m", "hours_apart",
            "category_lost", "category_found", "location_lost", "location_found", "label",
        ])
        writer.writeheader()
        writer.writerows(rows)

    n_pos = sum(1 for r in rows if r["label"] == 1)
    n_neg = sum(1 for r in rows if r["label"] == 0)
    print(f"Wrote {len(rows)} labelled pairs ({n_pos} positive, {n_neg} negative) to {out_path}")
    if len(rows) < 30:
        print(
            "\nHeads up: that's a small sample. Metrics/graphs from this few "
            "labelled pairs will be noisy -- treat them as early/illustrative "
            "until more confirmed handovers and rejections have piled up. You "
            "can still run generate_evaluation.py with the synthetic fallback "
            "alongside this for comparison in the meantime."
        )


if __name__ == "__main__":
    main()