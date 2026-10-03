# AarogyaTwin-X improvement roadmap

## Current project position

AarogyaTwin-X is already a useful synthetic, local research prototype with:

- Patient-disjoint train/calibration/test evaluation
- Past-only replay features
- Temporal glucose forecasts at 30, 60, and 120 minutes
- Calibrated probabilities and forecast intervals
- CGM dropout abstention
- Distribution-shift stress tests
- Event-level alert metrics
- Local API, dashboard, evidence summary, and presentation decks

The main point to remember is:

> Good results on a synthetic simulator do not prove good performance on real patients.

The current project is strongest as an honest, reproducible research demonstration—not as a clinically validated product.

## Highest-priority improvements

### 1. Evaluate multiple synthetic seeds

The current headline results use seed `2026`. Run several fixed seeds, for example `2026` through `2030`, and report:

- Mean metric
- Standard deviation
- Minimum and maximum
- Per-seed results

This shows whether the result is stable or dependent on one lucky simulator seed.

### 2. Add patient-level confidence intervals

Replay rows from the same patient are correlated. Add patient-level summaries and bootstrap intervals for:

- MAE
- RMSE
- Interval coverage
- Brier score
- Alert sensitivity
- False alerts per patient-day

Do not treat thousands of correlated windows as thousands of independent subjects.

### 3. Add browser end-to-end tests

Automate the real dashboard flow:

1. Load the dashboard.
2. Select a held-out synthetic patient.
3. Move replay forward by five minutes.
4. Confirm the forecast appears.
5. Enable CGM dropout.
6. Confirm the unavailable forecast and warning.
7. Run the scenario panel.
8. Confirm the non-medical disclaimer.

### 4. Improve the data-quality panel

Report freshness and missingness separately for:

- CGM
- Heart rate
- HRV
- Sleep
- Activity
- Meals

A useful message would be:

```text
CGM fresh; HRV missing; meal stream partially missing
```

### 5. Add event-timeline visualization

Show the relationship between:

- Replay anchor
- Forecast window
- Predicted alert
- Event onset
- Confirmation point
- Lead time

This is easier to understand than only showing AUROC or AUPRC.

## Model improvements

### 6. Add stronger CPU-friendly baselines

Compare the current temporal model with:

- Last observed glucose
- Running patient mean
- Linear autoregressive baseline
- Current gradient-boosting temporal model
- Small GRU or TCN only if CPU evidence justifies it

Do not add a neural model only for presentation value.

### 7. Add conditional forecast intervals

Instead of one width per horizon, evaluate intervals by context:

- High versus low glucose
- Stable versus rapidly changing glucose
- Good versus degraded signal quality
- Low versus high missingness

The result must still be reported as synthetic evidence.

### 8. Add calibration curves

Show a reliability diagram with:

- Predicted probability on the X-axis
- Observed event rate on the Y-axis
- Perfect-calibration diagonal

This makes probability quality easier to understand than a single ECE number.

### 9. Explain alert-threshold trade-offs

Show that lower thresholds generally produce:

- More detected events
- More false alerts

Higher thresholds generally produce:

- Fewer alerts
- More missed events

Do not present any threshold as a clinical recommendation.

## Evaluation improvements

### 10. Add temporal holdout evaluation

In addition to patient-disjoint testing, evaluate a later synthetic time period separately from earlier periods. This tests whether the model handles time drift.

### 11. Add synthetic subgroup analysis

Compare behavior across synthetic groups such as:

- Younger versus older patients
- Lower versus higher HbA1c
- Lower versus higher missingness
- Lower versus higher glucose variability

Label these as synthetic subgroup results, not clinical fairness claims.

### 12. Expand missingness patterns

Test:

- Long continuous sensor outage
- Intermittent sensor failure
- Night-time missingness
- Heart-rate-only outage
- Meal-stream outage
- Multiple streams missing together

The system should either degrade transparently or abstain when the input is insufficient.

## Engineering improvements

### 13. Lock runtime versions

Document and lock:

- Python version
- NumPy
- scikit-learn
- FastAPI
- Uvicorn
- pytest
- Frontend dependencies

The current WSL verification used Python `3.14.4`; the original plan referenced Python 3.11. This difference should be documented clearly or resolved before a clean external setup.

### 14. Add continuous integration

A basic CI workflow should run:

```text
backend compilation
pytest
frontend build
synthetic artifact smoke test
API contract smoke test
```

### 15. Strengthen artifact provenance

Add to the artifact manifest:

- Bundle SHA-256
- Git commit
- Python version
- Package versions
- Simulator version
- Model version
- Build timestamp

### 16. Expand API contract tests

Verify that:

- Every number is finite or null
- Unknown patients return 404
- Invalid steps return 400
- Invalid scenario ranges return 422
- Unavailable forecasts return empty forecast arrays
- Unavailable prediction values are null
- JSON never contains NaN or Infinity

## Dashboard improvements

### 17. Improve the first screen

Show three immediate status cards:

```text
Synthetic data
Local API ready
Held-out test patient
```

### 18. Add simple help text

Explain:

- What event risk means
- What an interval means
- What `Unknown` means
- Why an above-threshold anchor has no new-event risk
- Why observed drivers are not causal explanations

### 19. Add an evidence summary card

Show a compact summary before the raw metrics table:

```text
30-minute MAE: 7.21 mg/dL
60-minute MAE: 7.85 mg/dL
120-minute MAE: 8.38 mg/dL
12 held-out patients
Synthetic only
Patient-disjoint evaluation
```

### 20. Add timeline markers

Mark meals, activity, CGM gaps, replay position, and forecast start directly on the history chart.

## Presentation improvements

### 21. Add real dashboard screenshots

Include screenshots of:

- Normal forecast
- CGM dropout abstention
- Metrics panel
- Scenario disclaimer
- Alert metrics

### 22. Keep one simple architecture flow

```text
Synthetic data
      ↓
Patient-disjoint split
      ↓
Past-only features
      ↓
Temporal model
      ↓
Calibration + uncertainty
      ↓
Local API
      ↓
Dashboard
```

### 23. Show a failure slide

Example:

```text
Synthetic glucose level +25 mg/dL shift
120-minute coverage: 62.09%

Conclusion: the stress test exposes a known weakness.
```

This is more credible than showing only favorable results.

## What should not be added casually

Avoid these unless there is strong evidence and explicit approval:

- Large neural models
- Local LLM copilot
- CUDA or GPU setup
- Public patient datasets without license review
- Medication or dosing features
- Causal treatment claims
- Clinical recommendations
- Fabricated patient or accuracy claims

## Recommended priority order

If time is limited, work in this order:

1. Multiple synthetic seeds
2. Patient-level confidence intervals
3. Real dashboard screenshots in the presentation
4. Browser end-to-end smoke test
5. Exact dependency lock
6. Calibration curve visualization
7. Per-sensor data-quality summary

The project does not need more complexity to become stronger. Its main advantage is the combination of synthetic-only data, patient-disjoint evaluation, past-only replay, calibrated uncertainty, explicit abstention, and honest limitations.
