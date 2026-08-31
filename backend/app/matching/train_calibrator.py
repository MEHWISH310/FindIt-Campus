"""
Fits MatchCalibrator on real match outcomes and persists it to disk, so
matches.py can load a trained calibrator instead of leaving
match_probability null forever.

Label source -- Match.status is the ground truth, no manual labeling needed:
  - CONFIRMED matches -> label 1 (a claimant actually verified this pair)
  - sibling matches from the same lost_report_id batch that did NOT get
    confirmed -> label 0 (the system suggested them as candidates, but
    they weren't the real pair)

Run manually once you have enough confirmed claims (and again periodically
as more come in):
    python -m app.matching.train_calibrator
"""

from pathlib import Path

import joblib

from app.db.session import SessionLocal
from app.models.match import Match, MatchStatus
from app.matching.calibration import MatchCalibrator

# Below this many confirmed matches, Platt scaling is just overfitting noise
# -- leave match_probability null (matches.py falls back to raw_score) until
# there's enough signal to fit on.
MIN_CONFIRMED = 20

CALIBRATOR_PATH = Path(__file__).parent / "calibrator.pkl"


def build_training_set(db):
    confirmed = db.query(Match).filter(Match.status == MatchStatus.CONFIRMED).all()
    lost_ids_with_confirmation = {m.lost_report_id for m in confirmed}

    raw_scores = [m.raw_score for m in confirmed]
    labels = [1] * len(confirmed)

    if lost_ids_with_confirmation:
        siblings = (
            db.query(Match)
            .filter(
                Match.lost_report_id.in_(lost_ids_with_confirmation),
                Match.status != MatchStatus.CONFIRMED,
            )
            .all()
        )
        raw_scores += [m.raw_score for m in siblings]
        labels += [0] * len(siblings)

    return raw_scores, labels


def train():
    db = SessionLocal()
    try:
        raw_scores, labels = build_training_set(db)
        n_positive = sum(labels)

        if n_positive < MIN_CONFIRMED:
            print(f"Only {n_positive} confirmed matches (need {MIN_CONFIRMED}) -- skipping fit.")
            return None
        if len(set(labels)) < 2:
            print("Training set has only one class -- skipping fit.")
            return None

        calibrator = MatchCalibrator()
        calibrator.fit(raw_scores, labels)
        joblib.dump(calibrator, CALIBRATOR_PATH)
        print(f"Fit calibrator on {len(raw_scores)} pairs ({n_positive} positive) -> {CALIBRATOR_PATH}")
        return calibrator
    finally:
        db.close()


if __name__ == "__main__":
    train()
