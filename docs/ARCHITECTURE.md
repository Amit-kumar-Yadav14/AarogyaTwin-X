# AarogyaTwin-X architecture

## 1. Purpose

AarogyaTwin-X is a local, reproducible research prototype that replays synthetic patient timelines and returns glucose forecast heads at 30, 60, and 120 minutes. It also estimates the project-defined probability of a new sustained high-glucose event within 120 minutes.

It is not a diagnostic system, clinical validation study, treatment-effect estimator, or medical-advice tool.

## 2. End-to-end flow

```text
Seed 2026
   |
   v
Synthetic simulator
   |  static records + 5-minute observations
   v
Patient-disjoint split
   |  36 train / 6 calibration-tuning / 6 calibration-interval / 12 test
   v
Past-only feature builder
   |  summaries, trends, lags, missingness indicators
   v
Global CPU model
   |  temporal lag HistGradientBoostingRegressor heads
   |  calibrated fusion LogisticRegression event classifier
   v
Calibration and residual layer
   |  Platt probability calibration
   |  split-conformal interval widths
   |  bounded causal-in-time patient residual
   v
Joblib bundle + JSON evidence
   |
   +--> FastAPI local API --> React/Vite dashboard
```

## 3. Synthetic data

Each synthetic patient has static fields—age, sex, BMI, HbA1c, diabetes duration, and medication labels—and five-minute synthetic streams for glucose/CGM, heart rate, HRV, sleep, activity, and meals.

The simulator includes heterogeneous rhythms, meals, activity responses, correlated noise, and missing observations. Hidden simulator parameters are used only to generate observations; they are not serialized as model features or presented as measured physiology.

The operational event definition is intentionally explicit:

- Strictly above `180 mg/dL`.
- Four consecutive five-minute readings.
- A 15-minute confirmation span.
- Anchor must be observed and at or below the threshold for a new-event label.
- Missing future readings are unknown and excluded, never negative.

## 4. Leakage control and splits

Patient identity is the unit of the outer split. No patient appears in both global training and held-out testing.

Within the 12-patient calibration partition:

- 6 patients tune event probability calibration and residual strength.
- 6 different patients calibrate forecast interval widths.

The 12 test patients are not used to select hyperparameters, residual strength, thresholds, or interval widths.

Each feature vector is bounded by its replay anchor. Future observations are not visible to the feature builder or online residual reconstruction.

## 5. Model layers

### Forecast

The forecast heads use a CPU-friendly histogram gradient-boosting regressor. Features include:

- Current and recent summary values
- 15/30/60-minute glucose changes
- Explicit lags for glucose, heart rate, HRV, sleep, activity, and meal streams
- Static patient information
- Missing-value indicators produced by train-only preprocessing

A separate head is fitted for each named horizon.

### Event probability

A fusion logistic classifier estimates the contract-defined new-event probability. Static-only and sensor-only classifiers are retained as ablations. The saved fusion probabilities are calibrated with a Platt sigmoid fitted on calibration-tuning patients.

### Patient residual

For a patient, a prior forecast error becomes eligible only after its target timestamp is observable. A short, bounded history of those matured errors can adjust later forecasts. The strength is selected on calibration-tuning patients and the adjustment is clipped. This is an adaptive residual, not a clinical physiological parameter.

### Uncertainty

Absolute residual widths are computed with a finite-sample split-conformal rank on calibration-interval patients. The dashboard labels the 30/60/120 points as calibrated heads. Connecting lines are visual interpolation only.

## 6. Artifact and serving boundary

`python -m aarogya.pipeline` generates:

- `bundle.joblib` — synthetic cohort and fitted local model objects
- `metrics.json` — measured synthetic results
- `provenance.json` — seed, split, feature, calibration, and limitation metadata
- `manifest.json` — artifact inventory

`TwinEngine` only loads those files. It never trains during API initialization or inference.

The FastAPI service binds to `127.0.0.1:8000` and exposes:

- `/api/health`
- `/api/patients`
- `/api/twin/{id}`
- `/api/twin/{id}/simulate`
- `/api/metrics`

The React/Vite dashboard binds to `127.0.0.1:5173` and proxies `/api` to the local service.

## 7. Dashboard behavior

The dashboard provides:

1. Held-out synthetic patient selection.
2. Five-minute replay movement.
3. Observed history and current context.
4. Three named forecast heads and intervals.
5. Event state and calibrated risk when eligible.
6. CGM dropout simulation with warnings and abstention.
7. Assumption-based scenario comparison with a non-medical disclaimer.
8. Provenance, limitations, and measured evidence.

Loading, unavailable, not-ready, invalid-input, and API-error states are explicit. No fallback medical numbers are inserted.

## 8. Day-3 evidence snapshot

| Horizon | MAE | RMSE | Coverage | Width |
|---:|---:|---:|---:|---:|
| 30 min | 7.21 | 9.76 | 89.95% | 30.04 |
| 60 min | 7.85 | 10.42 | 89.36% | 32.08 |
| 120 min | 8.38 | 11.00 | 90.00% | 34.93 |

The calibrated fusion event classifier reports AUROC `0.94330`, AUPRC `0.27652`, Brier `0.02437`, log loss `0.13559`, and expected calibration error `0.02387` on valid held-out synthetic rows.

The full saved evidence, missingness tests, distribution-shift stress tests, alert metrics, and limitations are in `docs/EVIDENCE_SUMMARY.md`.

## 9. Non-claims

This architecture does not establish:

- Clinical accuracy or safety
- Generalization to real patients
- Causal effects of meals or activity
- Insulin sensitivity or treatment response
- Medication or dosing recommendations
- Robustness under arbitrary distribution shift
- Public-dataset or external benchmark performance
