"""
Calibration layer: turns a raw composite score into an interpretable
match PROBABILITY -- e.g. "score 0.82" doesn't tell a student anything,
but "91% likely the same item" does.

Analogy: a raw similarity score is like a exam's raw marks out of 137 --
technically a number, but meaningless until you convert it to a percentile
everyone understands. Platt scaling is exactly that conversion, fit on
labelled (score, is_same_item) pairs.

Uses scikit-learn's LogisticRegression on a single feature (the composite
score) -- this IS Platt scaling; sklearn just doesn't call it that by name.
"""

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.calibration import calibration_curve


class MatchCalibrator:
    def __init__(self):
        self.model = LogisticRegression()
        self.fitted = False

    def fit(self, raw_scores: list[float], labels: list[int]):
        """
        raw_scores: composite_score() outputs from labelled report pairs
        labels: 1 if the pair is actually the same item, 0 otherwise

        You'll build this labelled set during your evaluation phase --
        e.g. a few hundred hand-confirmed lost/found pairs plus an
        equal number of confirmed non-matches.
        """
        X = np.array(raw_scores).reshape(-1, 1)
        y = np.array(labels)
        self.model.fit(X, y)
        self.fitted = True

    def predict_proba(self, raw_score: float) -> float:
        if not self.fitted:
            raise RuntimeError("Calibrator not fitted yet -- call .fit() first")
        return float(self.model.predict_proba([[raw_score]])[0][1])

    def expected_calibration_error(
        self, raw_scores: list[float], labels: list[int], n_bins: int = 10
    ) -> float:
        """
        ECE: average gap between "predicted confidence" and "actual accuracy"
        across confidence buckets. Lower is better (0 = perfectly calibrated).
        This is the number you'll report in your evaluation section against [8],[9].
        """
        probs = [self.predict_proba(s) for s in raw_scores]
        prob_true, prob_pred = calibration_curve(labels, probs, n_bins=n_bins, strategy="uniform")
        # calibration_curve drops empty bins, so weight by how many bins actually returned
        return float(np.mean(np.abs(prob_true - prob_pred)))