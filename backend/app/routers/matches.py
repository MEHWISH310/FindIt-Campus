"""
POST /matches/find/{report_id} runs the actual matching pipeline:
  1. pull the report + every opposite-type OPEN report
  2. score each pair with fusion.composite_score()
  3. save the results as Match rows, sorted best-first

Calibration (turning raw_score into a probability) is intentionally
optional here -- until you've trained MatchCalibrator on real labelled
pairs (your evaluation phase), match_probability stays null and the UI
should just show raw_score/ranking. Wire in a trained, persisted
calibrator once you have one (pickle it, load it here).
"""

import math
from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.report import Report, ReportType, ReportStatus
from app.models.match import Match, MatchStatus
from app.routers.schemas import MatchOut
from app.matching.embeddings import cosine_sim
from app.matching.fusion import ReportSignals, composite_score

router = APIRouter(prefix="/matches", tags=["matches"])

# If the top two candidates' raw scores are within this margin, trigger
# disambiguation instead of auto-picking the top one (per your abstract:
# "if the leading candidates are not too far apart... asks a targeted
# disambiguation question").
DISAMBIGUATION_MARGIN = 0.05


def _haversine_meters(lat1, lon1, lat2, lon2) -> float:
    """Great-circle distance between two lat/lon points, in meters."""
    R = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


@router.post("/find/{report_id}", response_model=List[MatchOut])
def find_matches(report_id: str, db: Session = Depends(get_db)):
    report = db.query(Report).filter(Report.id == report_id).first()
    if not report:
        raise HTTPException(404, "Report not found")

    opposite_type = ReportType.FOUND if report.report_type == ReportType.LOST else ReportType.LOST
    candidates = (
        db.query(Report)
        .filter(Report.report_type == opposite_type, Report.status == ReportStatus.OPEN)
        .all()
    )

    scored = []
    for candidate in candidates:
        distance_m = None
        if report.latitude is not None and candidate.latitude is not None:
            distance_m = _haversine_meters(
                report.latitude, report.longitude, candidate.latitude, candidate.longitude
            )

        hours_apart = None
        if report.item_datetime and candidate.item_datetime:
            hours_apart = abs((report.item_datetime - candidate.item_datetime).total_seconds()) / 3600

        signals = ReportSignals(
            text_sim=cosine_sim(report.text_embedding, candidate.text_embedding),
            image_sim=cosine_sim(report.image_embedding, candidate.image_embedding),
            distance_m=distance_m,
            hours_apart=hours_apart,
        )
        result = composite_score(signals)
        scored.append((candidate, result))

    scored.sort(key=lambda x: x[1]["score"], reverse=True)

    # Decide status: needs disambiguation if top 2 are too close
    needs_disambiguation = (
        len(scored) >= 2 and (scored[0][1]["score"] - scored[1][1]["score"]) < DISAMBIGUATION_MARGIN
    )

    saved_matches = []
    for candidate, result in scored[:5]:  # keep top 5 candidates
        lost_id = report.id if report.report_type == ReportType.LOST else candidate.id
        found_id = candidate.id if report.report_type == ReportType.LOST else report.id

        match = Match(
            lost_report_id=lost_id,
            found_report_id=found_id,
            raw_score=result["score"],
            used_signals=result["used_signals"],
            signal_weights=result["weights"],
            status=MatchStatus.NEEDS_DISAMBIGUATION if needs_disambiguation else MatchStatus.CANDIDATE,
        )
        db.add(match)
        saved_matches.append(match)

    db.commit()
    for m in saved_matches:
        db.refresh(m)

    return saved_matches