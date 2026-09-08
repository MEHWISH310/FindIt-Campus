"""
Generates the evaluation artifacts docs/evaluation/README.md asks for:
    calibration_report.md   (+ calibration_curve.png)
    precision_recall.md     (+ precision_recall.png)
    disambiguation_impact.md(+ disambiguation_impact.png)
    missing_modality_impact.md (+ missing_modality_impact.png)

WHERE TO PUT THIS FILE: backend/generate_evaluation.py (next to backend/tests/)
HOW TO RUN:
    cd backend
    python generate_evaluation.py

*** IMPORTANT -- READ BEFORE YOU CITE THESE NUMBERS IN YOUR REPORT ***
You don't have hand-labelled real match/non-match pairs yet (that's the
"once the matching pipeline is working on real/labelled data" the
docs/evaluation/README.md is waiting on). So this script does the same
thing your existing tests/test_fusion_and_calibration.py already does:
it runs your REAL composite_score() / MatchCalibrator code, but against
a SEEDED SYNTHETIC labelled set (simulated similarity signals with a
known ground-truth label), not real reports.

That means: the *code path* being measured is 100% real (this is not
faked output), but the *numbers* are illustrative until you swap
`build_synthetic_pairs()` below for real labelled pairs exported from
your DB (columns needed: text_sim, image_sim, distance_m, hours_apart,
category match, location match, and a 1/0 "is_same_item" label from a
human-confirmed handover). Each markdown file says this explicitly at
the top -- don't delete that line before submitting your report.
"""

import argparse
import csv
import os
import random
import sys

import numpy as np
import matplotlib.pyplot as plt
from sklearn.metrics import precision_recall_curve, auc, roc_auc_score

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
from app.matching.fusion import ReportSignals, composite_score, competing_cluster
from app.matching.calibration import MatchCalibrator

OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "docs", "evaluation")
os.makedirs(OUT_DIR, exist_ok=True)

random.seed(42)
np.random.seed(42)

SYNTHETIC_DISCLAIMER = (
    "> **Note:** generated against a seeded synthetic labelled set (see "
    "`generate_evaluation.py`'s docstring), not real handover-confirmed data. "
    "The scoring/calibration code exercised is real; the ground-truth labels are "
    "simulated. Run `export_labelled_pairs.py` against your Neon DB and re-run "
    "this script with `--csv labelled_pairs.csv` to replace these numbers with "
    "real ones before the final report.\n"
)

REAL_DISCLAIMER_TEMPLATE = (
    "> **Note:** generated from **real, human-confirmed data** exported from the "
    "Neon DB via `export_labelled_pairs.py` ({n} labelled pairs: {n_pos} confirmed "
    "matches, {n_neg} confirmed rejections). {small_sample_note}\n"
)


def _float_or_none(v):
    if v in (None, "", "None"):
        return None
    return float(v)


def load_pairs_from_csv(path):
    """Reads labelled_pairs.csv (from export_labelled_pairs.py) into the same
    [(ReportSignals, label), ...] shape build_synthetic_pairs() produces."""
    pairs = []
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            sig = ReportSignals(
                text_sim=_float_or_none(row["text_sim"]),
                image_sim=_float_or_none(row["image_sim"]),
                distance_m=_float_or_none(row["distance_m"]),
                hours_apart=_float_or_none(row["hours_apart"]),
                category_lost=row["category_lost"] or None,
                category_found=row["category_found"] or None,
                location_lost=row["location_lost"] or None,
                location_found=row["location_found"] or None,
            )
            pairs.append((sig, int(row["label"])))
    return pairs


def make_disclaimer(pairs, is_real):
    if not is_real:
        return SYNTHETIC_DISCLAIMER
    n = len(pairs)
    n_pos = sum(1 for _, label in pairs if label == 1)
    n_neg = n - n_pos
    small_sample_note = (
        f"**Small sample ({n} pairs)** -- treat as early/illustrative until more "
        "confirmed handovers and rejections have accumulated."
        if n < 30 else ""
    )
    return REAL_DISCLAIMER_TEMPLATE.format(n=n, n_pos=n_pos, n_neg=n_neg, small_sample_note=small_sample_note)


# -----------------------------------------------------------------------------
# Synthetic labelled pairs -- swap this out for a real CSV/JSON export later.
# Each pair has an underlying "true" similarity level plus noise per-signal,
# which is what makes text/image/geo/time/category/location partially but not
# perfectly agree, same as real messy reports.
# -----------------------------------------------------------------------------

def build_synthetic_pairs(n_pos=250, n_neg=250):
    pairs = []
    categories = ["ID Card", "Wallet", "Phone", "Water Bottle", "Laptop", "Earphones"]
    locations = ["PRP", "SJT", "TT", "PRP Hostel Block A", "SJT Cafeteria"]

    for _ in range(n_pos):
        true_sim = random.uniform(0.6, 1.0)
        cat = random.choice(categories)
        loc = random.choice(locations)
        pairs.append((ReportSignals(
            text_sim=min(1.0, max(-1.0, true_sim + random.uniform(-0.2, 0.2))),
            image_sim=min(1.0, max(-1.0, true_sim + random.uniform(-0.25, 0.25))) if random.random() > 0.15 else None,
            distance_m=abs(random.gauss(80, 120)),
            hours_apart=abs(random.gauss(6, 10)),
            category_lost=cat,
            category_found=cat if random.random() > 0.1 else random.choice(categories),
            location_lost=loc,
            location_found=loc if random.random() > 0.2 else random.choice(locations),
        ), 1))

    for _ in range(n_neg):
        true_sim = random.uniform(-0.2, 0.4)
        pairs.append((ReportSignals(
            text_sim=min(1.0, max(-1.0, true_sim + random.uniform(-0.2, 0.2))),
            image_sim=min(1.0, max(-1.0, true_sim + random.uniform(-0.25, 0.25))) if random.random() > 0.3 else None,
            distance_m=abs(random.gauss(600, 400)),
            hours_apart=abs(random.gauss(60, 50)),
            category_lost=random.choice(categories),
            category_found=random.choice(categories),
            location_lost=random.choice(locations),
            location_found=random.choice(locations),
        ), 0))

    random.shuffle(pairs)
    return pairs


# -----------------------------------------------------------------------------
# 1. calibration_report.md -- reliability diagram + ECE, using YOUR
#    calibration.py (Platt scaling / LogisticRegression on the composite score)
# -----------------------------------------------------------------------------

def run_calibration_report(pairs, disclaimer):
    raw_scores = [composite_score(sig)["score"] for sig, _ in pairs]
    labels = [label for _, label in pairs]

    cal = MatchCalibrator()
    cal.fit(raw_scores, labels)
    ece = cal.expected_calibration_error(raw_scores, labels, n_bins=10)

    from sklearn.calibration import calibration_curve
    probs = [cal.predict_proba(s) for s in raw_scores]
    prob_true, prob_pred = calibration_curve(labels, probs, n_bins=10, strategy="uniform")

    fig, ax = plt.subplots(figsize=(6, 6))
    ax.plot([0, 1], [0, 1], "k--", label="Perfect calibration")
    ax.plot(prob_pred, prob_true, "o-", color="#A23B72", label="MatchCalibrator")
    ax.set_xlabel("Predicted match probability")
    ax.set_ylabel("Observed fraction of true matches")
    ax.set_title(f"Reliability Diagram (ECE = {ece:.4f})")
    ax.legend()
    fig.tight_layout()
    img_path = os.path.join(OUT_DIR, "calibration_curve.png")
    fig.savefig(img_path, dpi=200)
    plt.close(fig)

    p_low = cal.predict_proba(0.2)
    p_mid = cal.predict_proba(0.5)
    p_high = cal.predict_proba(0.85)

    md = f"""# Calibration Report

{disclaimer}
## Method

Composite scores from `fusion.composite_score()` are fit with
`calibration.MatchCalibrator` (Platt scaling / logistic regression on the
single composite-score feature), then binned into 10 buckets to compare
predicted probability against observed match rate.

## Results

- **Expected Calibration Error (ECE): {ece:.4f}** (0 = perfectly calibrated)
- P(match | raw_score=0.2) = {p_low:.3f}
- P(match | raw_score=0.5) = {p_mid:.3f}
- P(match | raw_score=0.85) = {p_high:.3f}
- n = {len(pairs)} pairs ({sum(labels)} positive, {len(labels) - sum(labels)} negative)

![Reliability diagram](calibration_curve.png)

The closer the calibration curve sits to the diagonal, the more an "X%
match probability" shown to a student actually corresponds to X% of
such matches being correct.
"""
    with open(os.path.join(OUT_DIR, "calibration_report.md"), "w") as f:
        f.write(md)
    print(f"ECE={ece:.4f} -- wrote calibration_report.md + calibration_curve.png")


# -----------------------------------------------------------------------------
# 2. precision_recall.md -- fused score vs text-only vs image-only baselines
# -----------------------------------------------------------------------------

def run_precision_recall(pairs, disclaimer):
    labels = np.array([label for _, label in pairs])

    fused = np.array([composite_score(sig)["score"] for sig, _ in pairs])
    text_only = np.array([
        composite_score(ReportSignals(text_sim=sig.text_sim))["score"] for sig, _ in pairs
    ])
    # image-only: pairs missing a photo have no image signal -> score 0 (can't match on nothing)
    image_only = np.array([
        composite_score(ReportSignals(image_sim=sig.image_sim))["score"] if sig.image_sim is not None else 0.0
        for sig, _ in pairs
    ])

    fig, ax = plt.subplots(figsize=(7, 6))
    results = {}
    for name, scores, color in [
        ("Fused (all signals)", fused, "#A23B72"),
        ("Text-only baseline", text_only, "#2E86AB"),
        ("Image-only baseline", image_only, "#6A994E"),
    ]:
        prec, rec, _ = precision_recall_curve(labels, scores)
        pr_auc = auc(rec, prec)
        results[name] = pr_auc
        ax.plot(rec, prec, label=f"{name} (AUC-PR={pr_auc:.3f})", color=color, linewidth=2)

    ax.set_xlabel("Recall")
    ax.set_ylabel("Precision")
    ax.set_title("Precision-Recall: Fused vs Baselines")
    ax.legend(loc="lower left")
    fig.tight_layout()
    img_path = os.path.join(OUT_DIR, "precision_recall.png")
    fig.savefig(img_path, dpi=200)
    plt.close(fig)

    rows = "\n".join(f"| {name} | {pr_auc:.3f} |" for name, pr_auc in results.items())
    md = f"""# Precision / Recall vs Baselines

{disclaimer}
## Method

For each labelled pair, three scores are computed with the same real
`fusion.composite_score()` function, restricted to different signal subsets:
fused (all six signals, weights auto-redistributed for missing ones),
text-only, and image-only. Precision-recall curves are computed by sweeping
the match threshold across each score.

## Results

| Method | AUC-PR |
|---|---|
{rows}

![Precision-recall curves](precision_recall.png)

n = {len(pairs)} pairs ({int(labels.sum())} positive, {int(len(labels) - labels.sum())} negative).
"""
    with open(os.path.join(OUT_DIR, "precision_recall.md"), "w") as f:
        f.write(md)
    print(f"AUC-PR: {results} -- wrote precision_recall.md + precision_recall.png")


# -----------------------------------------------------------------------------
# 3. disambiguation_impact.md -- does flagging close races reduce wrong
#    auto-picks that would otherwise go straight to the claimant?
# -----------------------------------------------------------------------------

DISAMBIGUATION_DISCLAIMER = (
    "> **Note:** this one is always a simulation, even when you pass `--csv` -- "
    "measuring \"how often would naive top-1 have been silently wrong\" needs many "
    "repeated randomized lost-vs-multiple-found scenarios, which your real "
    "confirmed-match data won't have volume for yet. Uses `fusion.competing_cluster()` "
    "(real code) against simulated candidate sets.\n"
)


def run_disambiguation_impact(n_scenarios=200, margin=0.05):
    """
    Simulates n_scenarios "one lost report, several candidate found reports"
    situations. In each, exactly one candidate is the true match. We compare:
      - naive top-1: always auto-suggest the highest-scoring candidate
      - with disambiguation: if competing_cluster() says >=2 candidates are
        within `margin` of the top score, treat it as "needs a follow-up
        question" instead of silently picking one -- i.e. it doesn't
        commit to a possibly-wrong pick without asking.
    "Correct without asking" is naive top-1 being right AND not flagged.
    "Would have been silently wrong" is naive top-1 being wrong.
    """
    naive_correct = 0
    naive_wrong = 0
    flagged = 0
    flagged_and_wouldve_been_wrong = 0

    for _ in range(n_scenarios):
        n_candidates = random.randint(2, 5)
        true_idx = random.randint(0, n_candidates - 1)
        scores = []
        for i in range(n_candidates):
            base = random.uniform(0.75, 0.95) if i == true_idx else random.uniform(0.3, 0.9)
            scores.append(base)

        top_idx = max(range(n_candidates), key=lambda i: scores[i])
        cluster = competing_cluster(scores, margin=margin)
        is_flagged = len(cluster) >= 2

        if top_idx == true_idx:
            naive_correct += 1
        else:
            naive_wrong += 1
            if is_flagged:
                flagged_and_wouldve_been_wrong += 1
        if is_flagged:
            flagged += 1

    naive_accuracy = naive_correct / n_scenarios
    catch_rate = (flagged_and_wouldve_been_wrong / naive_wrong) if naive_wrong else 0.0

    fig, ax = plt.subplots(figsize=(6, 5))
    bars = ax.bar(
        ["Naive top-1\naccuracy", "Wrong picks caught\nby disambiguation"],
        [naive_accuracy, catch_rate],
        color=["#2E86AB", "#A23B72"],
    )
    for b in bars:
        ax.text(b.get_x() + b.get_width() / 2, b.get_height() + 0.02, f"{b.get_height():.1%}", ha="center")
    ax.set_ylim(0, 1.1)
    ax.set_ylabel("Rate")
    ax.set_title(f"Disambiguation Impact (margin={margin})")
    fig.tight_layout()
    img_path = os.path.join(OUT_DIR, "disambiguation_impact.png")
    fig.savefig(img_path, dpi=200)
    plt.close(fig)

    md = f"""# Disambiguation Impact

{DISAMBIGUATION_DISCLAIMER}
## Method

Simulates {n_scenarios} "one lost report vs several found candidates"
scenarios with one true match each. Compares silently auto-picking the
top-scoring candidate against flagging it for a follow-up question when
`fusion.competing_cluster()` finds >= 2 candidates within `margin={margin}`
of the top score.

## Results

- Naive top-1 accuracy (no disambiguation): **{naive_accuracy:.1%}**
- Of the naive top-1's wrong picks, disambiguation flagged **{catch_rate:.1%}**
  of them for a follow-up question instead of silently committing to the
  wrong candidate.
- Total scenarios flagged for disambiguation: {flagged}/{n_scenarios}

![Disambiguation impact](disambiguation_impact.png)
"""
    with open(os.path.join(OUT_DIR, "disambiguation_impact.md"), "w") as f:
        f.write(md)
    print(f"naive_acc={naive_accuracy:.3f} catch_rate={catch_rate:.3f} -- wrote disambiguation_impact.md")


# -----------------------------------------------------------------------------
# 4. missing_modality_impact.md -- how much does match quality degrade
#    when a report has no photo (text-only) vs full multi-modal signals?
# -----------------------------------------------------------------------------

def run_missing_modality_impact(pairs, disclaimer):
    labels = np.array([label for _, label in pairs])

    scenarios = {
        "All signals": lambda s: s,
        "No image (text+geo+time+cat+loc)": lambda s: ReportSignals(
            text_sim=s.text_sim, image_sim=None, distance_m=s.distance_m,
            hours_apart=s.hours_apart, category_lost=s.category_lost,
            category_found=s.category_found, location_lost=s.location_lost,
            location_found=s.location_found,
        ),
        "Text-only": lambda s: ReportSignals(text_sim=s.text_sim),
        "Text+image only (no geo/time/cat/loc)": lambda s: ReportSignals(
            text_sim=s.text_sim, image_sim=s.image_sim,
        ),
    }

    aucs = {}
    for name, transform in scenarios.items():
        scores = np.array([composite_score(transform(sig))["score"] for sig, _ in pairs])
        aucs[name] = roc_auc_score(labels, scores)

    fig, ax = plt.subplots(figsize=(8, 5))
    names = list(aucs.keys())
    vals = [aucs[n] for n in names]
    bars = ax.barh(names, vals, color="#6A994E")
    for b, v in zip(bars, vals):
        ax.text(v + 0.005, b.get_y() + b.get_height() / 2, f"{v:.3f}", va="center")
    ax.set_xlim(0.5, 1.0)
    ax.set_xlabel("ROC-AUC (separating true matches from non-matches)")
    ax.set_title("Missing-Modality Impact on Match Quality")
    fig.tight_layout()
    img_path = os.path.join(OUT_DIR, "missing_modality_impact.png")
    fig.savefig(img_path, dpi=200)
    plt.close(fig)

    rows = "\n".join(f"| {name} | {v:.3f} |" for name, v in aucs.items())
    md = f"""# Missing-Modality Impact

{disclaimer}
## Method

The same labelled pairs are scored with `fusion.composite_score()` under
different available-signal scenarios (fusion.py auto-redistributes weights
over whatever signals are present), then ROC-AUC measures how well each
scenario separates true matches from non-matches.

## Results

| Scenario | ROC-AUC |
|---|---|
{rows}

![Missing modality impact](missing_modality_impact.png)

This quantifies the value of each modality: how much match quality drops
when a report is filed without a photo (common for e.g. a lost ID card
found by someone else), versus having the full six-signal fusion.
"""
    with open(os.path.join(OUT_DIR, "missing_modality_impact.md"), "w") as f:
        f.write(md)
    print(f"AUCs: {aucs} -- wrote missing_modality_impact.md")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--csv", default=None,
        help="Path to labelled_pairs.csv from export_labelled_pairs.py. "
             "If omitted, falls back to seeded synthetic pairs.",
    )
    args = parser.parse_args()

    if args.csv:
        pairs = load_pairs_from_csv(args.csv)
        is_real = True
        print(f"Loaded {len(pairs)} REAL labelled pairs from {args.csv}")
    else:
        pairs = build_synthetic_pairs()
        is_real = False
        print(
            "No --csv given -- using seeded SYNTHETIC pairs. Run "
            "export_labelled_pairs.py against your Neon DB, then re-run this "
            "script with --csv labelled_pairs.csv for real numbers."
        )

    disclaimer = make_disclaimer(pairs, is_real)
    run_calibration_report(pairs, disclaimer)
    run_precision_recall(pairs, disclaimer)
    run_disambiguation_impact()
    run_missing_modality_impact(pairs, disclaimer)
    print(f"\nAll evaluation artifacts written to {os.path.abspath(OUT_DIR)}")