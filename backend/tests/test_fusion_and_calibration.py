"""
Sanity checks for fusion.py and calibration.py -- run with:
    python tests/test_fusion_and_calibration.py

Doesn't touch embeddings.py (that needs torch/CLIP downloads); this just
proves the *scoring math* behaves correctly, which is the part reviewers
will grill you on.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.matching.fusion import ReportSignals, composite_score, competing_cluster
from app.matching.calibration import MatchCalibrator
import random

print("=== Fusion tests ===")

# Case 1: all signals present
s1 = composite_score(ReportSignals(text_sim=0.9, image_sim=0.8, distance_m=50, hours_apart=2))
print("All signals present:", s1)
assert abs(sum(s1["weights"].values()) - 1.0) < 1e-9

# Case 2: missing image (report filed without a photo) -- weight should redistribute
s2 = composite_score(ReportSignals(text_sim=0.9, image_sim=None, distance_m=50, hours_apart=2))
print("Missing image:       ", s2)
assert "image" not in s2["used_signals"]
assert abs(sum(s2["weights"].values()) - 1.0) < 1e-9

# Case 3: only text (no photo, no geo, no time known)
s3 = composite_score(ReportSignals(text_sim=0.7))
print("Text-only:           ", s3)
assert s3["weights"]["text"] == 1.0

print("\n=== Disambiguation cluster tests ===")

# Clear #1 with a distant #3/#4/#5 -- only the top two should cluster
c1 = competing_cluster([0.82, 0.80, 0.5, 0.3, 0.1], margin=0.05)
print("Clear leader, distant rest:", c1)
assert c1 == {0, 1}

# Three-way photo finish -- all three should cluster, not just top-2
c2 = competing_cluster([0.80, 0.78, 0.77, 0.3], margin=0.05)
print("Three-way close race:      ", c2)
assert c2 == {0, 1, 2}

# One clear winner, nobody else close
c3 = competing_cluster([0.9, 0.4, 0.2], margin=0.05)
print("One clear winner:          ", c3)
assert c3 == {0}

# No candidates at all
assert competing_cluster([], margin=0.05) == set()

print("\n=== Calibration tests ===")
random.seed(42)
# Fake labelled data: higher composite score -> more likely a true match
raw_scores = [random.uniform(0, 1) for _ in range(300)]
labels = [1 if (s + random.uniform(-0.15, 0.15)) > 0.5 else 0 for s in raw_scores]

cal = MatchCalibrator()
cal.fit(raw_scores, labels)

p_low = cal.predict_proba(0.1)
p_high = cal.predict_proba(0.9)
print(f"P(match | raw_score=0.1) = {p_low:.3f}")
print(f"P(match | raw_score=0.9) = {p_high:.3f}")
assert p_high > p_low, "Calibrator should assign higher probability to higher raw scores"

ece = cal.expected_calibration_error(raw_scores, labels)
print(f"Expected Calibration Error: {ece:.4f}")

print("\nAll checks passed.")