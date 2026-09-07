"""
Composite score = text_sim + image_sim + geo_proximity + time_decay
                   + category_match + location_match,
with weights redistributed when a signal is missing (no photo, no location, etc).

Think of it like splitting a bill: if one friend didn't order anything,
you don't charge the table "one share short" -- you split the total
across whoever's actually there. Same idea here: if a report has no photo,
the image weight doesn't get lost, it gets folded into text/geo/time/etc.

category_match and location_match are NEW: they compare the structured
fields (category dropdown, typed location string) directly, instead of
relying on free-text embedding similarity to "notice" that both reports
say "ID Card" / "PRP". Free-text embeddings are noisy for short generic
descriptions, so these give an explicit, exact-match-style boost.
"""

import math
from dataclasses import dataclass
from typing import Optional


# Base weights when ALL six signals are present. Tune these against a
# labelled dev set once you have one (that's your calibration/eval phase).
BASE_WEIGHTS = {
    "text": 0.20,
    "image": 0.25,
    "geo": 0.10,
    "time": 0.10,
    "category": 0.20,
    "location": 0.15,
}

GEO_DECAY_METERS = 300.0   # similarity halves roughly every this many meters
TIME_DECAY_HOURS = 48.0    # similarity halves roughly every this many hours


@dataclass
class ReportSignals:
    text_sim: Optional[float] = None       # cosine sim in [-1, 1] or None
    image_sim: Optional[float] = None      # cosine sim in [-1, 1] or None
    distance_m: Optional[float] = None     # meters between lost/found locations, or None
    hours_apart: Optional[float] = None    # hours between lost/found timestamps, or None
    category_lost: Optional[str] = None    # e.g. "ID Card"
    category_found: Optional[str] = None   # e.g. "ID Card"
    location_lost: Optional[str] = None    # e.g. "PRP"
    location_found: Optional[str] = None   # e.g. "Prp"


def geo_proximity(distance_m: Optional[float]) -> Optional[float]:
    if distance_m is None:
        return None
    return math.exp(-distance_m / GEO_DECAY_METERS)


def time_decay(hours_apart: Optional[float]) -> Optional[float]:
    if hours_apart is None:
        return None
    return math.exp(-abs(hours_apart) / TIME_DECAY_HOURS)


def _normalize_str(s: Optional[str]) -> Optional[str]:
    if not s:
        return None
    return s.strip().lower()


def category_match_score(cat_a: Optional[str], cat_b: Optional[str]) -> Optional[float]:
    """
    Exact match (case/whitespace-insensitive) on the category field.
    If your categories can have near-variants ("ID Card" vs "Id Cards"),
    swap the equality check for something like:
        from rapidfuzz import fuzz
        return 1.0 if fuzz.ratio(a, b) > 90 else 0.0
    """
    a, b = _normalize_str(cat_a), _normalize_str(cat_b)
    if a is None or b is None:
        return None
    return 1.0 if a == b else 0.0


def location_match_score(loc_a: Optional[str], loc_b: Optional[str]) -> Optional[float]:
    """
    Exact match scores 1.0. Partial/substring match (e.g. "PRP" vs
    "PRP Hostel Block A") scores 0.7 -- still a strong signal, but not
    as strong as an exact match, since substrings can be coincidental.
    """
    a, b = _normalize_str(loc_a), _normalize_str(loc_b)
    if a is None or b is None:
        return None
    if a == b:
        return 1.0
    if a in b or b in a:
        return 0.7
    return 0.0


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
        "category": category_match_score(signals.category_lost, signals.category_found),
        "location": location_match_score(signals.location_lost, signals.location_found),
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


def competing_cluster(scores: list, margin: float) -> set:
    """
    Given composite scores for every candidate (any order), return the
    *indices* of every score within `margin` of the top one -- the set
    that's genuinely too close to auto-rank. Pure function so the
    disambiguation decision in matches.py is testable without a DB: it's
    always >= 2 vs top-2 only, so a clear #1 with a distant #3/#4/#5
    doesn't drag the whole batch into "needs review".
    """
    if not scores:
        return set()
    top = max(scores)
    return {i for i, s in enumerate(scores) if top - s < margin}