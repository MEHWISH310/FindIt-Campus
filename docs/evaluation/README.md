# Evaluation

This folder holds your evaluation artifacts, to be filled in once the
matching pipeline is working on real/labelled data:

- `precision_recall.md` — precision/recall vs text-only and image-only baselines
- `calibration_report.md` — reliability diagrams + Expected Calibration Error
  (use `backend/app/matching/calibration.py`'s `expected_calibration_error()`)
- `disambiguation_impact.md` — effect of disambiguation on claim-verification accuracy
- `missing_modality_impact.md` — match quality when text-only vs text+image

Keep raw numbers here as you generate them (even messy notes) — you'll
condense these into the final report/paper's evaluation section later.