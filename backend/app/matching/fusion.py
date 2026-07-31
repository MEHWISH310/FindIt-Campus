"""
Composite score = text_sim + image_sim + geo_proximity + time_decay,
with weights redistributed when a signal is missing (no photo, no location, etc).

Think of it like splitting a bill: if one friend didn't order anything,
you don't charge the table "one share short" -- you split the total
across whoever's actually there. Same idea here: if a report has no photo,
the image weight doesn't get lost, it gets folded into text/geo/time.
"""

import math
from dataclasses import dataclass
from typing import Optional


# Base weights when ALL four signals are present. Tune these against a
# labelled dev set once you have one (that's your calibration/eval phase).
BASE_WEIGHTS = {
    "text": 0.35,
    "image": 0.35,
    "geo": 0.15,
    "time": 0.15,
}

GEO_DECAY_METERS = 300.0   # similarity halves roughly every this many meters
TIME_DECAY_HOURS = 48.0    # similarity halves roughly every this many hours


@dataclass
class ReportSignals:
    text_sim: Optional[float] = None     # cosine sim in [-1, 1] or None
    image_sim: Optional[float] = None    # cosine sim in [-1, 1] or None
    distance_m: Optional[float] = None   # meters between lost/found locations, or None
    hours_apart: Optional[float] = None  # hours between lost/found timestamps, or None


def geo_proximity(distance_m: Optional[float]) -> Optional[float]:
    if distance_m is None:
        return None
    return math.exp(-distance_m / GEO_DECAY_METERS)


def time_decay(hours_apart: Optional[float]) -> Optional[float]:
    if hours_apart is None:
        return None
    return math.exp(-abs(hours_apart) / TIME_DECAY_HOURS)


def composite_score(signals: ReportSignals) -> dict:
    """
    Returns {"score": float in [0,1]-ish, "used_signals": [...], "weights": {...}}
    so the caller (and later, the disambiguation step) can see exactly what
    was used -- useful for debugging and for explaining a match to a user.
    """
    values = {
        "text": signals.text_sim,
        "image": signals.image_sim,
        "geo": geo_proximity(signals.distance_m),
        "time": time_decay(signals.hours_apart),
    }

    present = {k: v for k, v in values.items() if v is not None}
    if not present:
        return {"score": 0.0, "used_signals": [], "weights": {}}

    # Redistribute: renormalize base weights over only the present signals.
    total_base = sum(BASE_WEIGHTS[k] for k in present)
    weights = {k: BASE_WEIGHTS[k] / total_base for k in present}

    score = sum(weights[k] * present[k] for k in present)

    return {
        "score": score,
        "used_signals": list(present.keys()),
        "weights": weights,
    }