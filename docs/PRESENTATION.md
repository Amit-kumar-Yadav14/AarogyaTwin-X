# AarogyaTwin-X presentation

**Format:** 16:9, local research prototype demo  
**Evidence:** saved seeded synthetic results only  
**Duration:** approximately 20–24 minutes including live demo

## Slide 1 — AarogyaTwin-X

### Forecasts with evidence, not unsupported certainty

- Local synthetic patient replay and glucose forecasting
- 30-, 60-, and 120-minute forecast heads
- Uncertainty, data quality, provenance, and limitations in one workflow

**Presenter note:** Open with the boundary: this is a research prototype, not a diagnostic device or medical-advice system.

## Slide 2 — The question

### Can a forecast be useful without hiding its limitations?

- A point estimate alone is not enough
- The user needs context, uncertainty, and data freshness
- Missing data should trigger a clear limitation or abstention
- Evidence should be measured and reproducible

**Presenter note:** Explain the prototype goal rather than claiming a clinical outcome.

## Slide 3 — The experience

### A clinician-facing research workflow

1. Select a held-out synthetic patient
2. Replay the timeline in five-minute steps
3. Inspect observed context and data quality
4. Review forecast heads, intervals, and event risk
5. Inspect evidence before interpreting the estimate

## Slide 4 — Synthetic data only

### 60 patients × 5 days × 5-minute observations

- Static: age, BMI, HbA1c, diabetes duration, medication labels
- Streams: CGM, heart rate, HRV, sleep, activity, meals
- Seeded variability, rhythms, noise, and missingness
- No real patient records or external benchmark data

## Slide 5 — Leakage-aware evaluation

### Patients are separated, not merely rows

- 36 training patients
- 6 calibration-tuning patients
- 6 calibration-interval patients
- 12 held-out test patients
- Past-only features at every replay anchor

**Presenter note:** Correlated windows are not independent subjects. The patient split is the important boundary.

## Slide 6 — Model architecture

### Small CPU models with explicit boundaries

- Temporal lag gradient-boosting heads for glucose
- Logistic fusion classifier for the event endpoint
- Train-only preprocessing and missing indicators
- Platt event-probability calibration
- Split-conformal forecast intervals

## Slide 7 — Causal-in-time residual

### Personalization that waits for evidence

- Make a forecast at time T
- Wait until its target time is observed
- Calculate the past error
- Use a short bounded history to adjust later forecasts
- Never use the current forecast’s future target

**Presenter note:** This is an adaptive residual. It is not a clinically identified insulin-sensitivity model.

## Slide 8 — Forecast comparison

### Learned forecasts outperform simple synthetic baselines

| Model | 30-min MAE | 60-min MAE | 120-min MAE |
|---|---:|---:|---:|
| Last observed glucose | 9.73 | 12.27 | 14.03 |
| Patient running mean | 11.26 | 11.38 | 11.56 |
| Day-1 summary model | 7.21 | 7.91 | 8.66 |
| Temporal model | 7.21 | 7.85 | 8.60 |
| Final temporal + residual | 7.21 | 7.85 | 8.38 |

**Presenter note:** The final row uses the saved Day-3 calibration choices. These are synthetic results, not clinical accuracy.

## Slide 9 — Uncertainty

### Coverage near the 90% target in the nominal test

| Horizon | MAE | RMSE | Coverage | Width |
|---|---:|---:|---:|---:|
| 30 min | 7.21 | 9.76 | 89.95% | 30.04 |
| 60 min | 7.85 | 10.42 | 89.36% | 32.08 |
| 120 min | 8.38 | 11.00 | 90.00% | 34.93 |

- Units for errors and width: mg/dL
- Only three named horizon heads are calibrated
- Connecting lines are visual interpolation

## Slide 10 — Probability calibration

### Better probability estimates, unchanged ranking

| Metric | Before | After |
|---|---:|---:|
| Brier score | 0.05035 | 0.02437 |
| Log loss | 0.18466 | 0.13559 |
| Calibration error | 0.05814 | 0.02387 |

- AUROC: 0.94330
- AUPRC: 0.27652
- 1,510 valid held-out synthetic event windows

## Slide 11 — Missing data

### Refuse to guess when CGM is too stale

- Natural missingness: about 0.3% forecast abstention
- Recent stream gaps: measurable error degradation
- Recent 30-minute CGM dropout: 100% abstention
- Unavailable forecasts remain null, not fabricated values

**Presenter note:** The policy uses a 15-minute CGM freshness limit.

## Slide 12 — Distribution shift

### Stress tests reveal failure modes

| 120-minute condition | MAE | Coverage |
|---|---:|---:|
| Nominal frozen model | 8.60 | 89.46% |
| Glucose level +25 mg/dL | 15.39 | 62.09% |
| Meal inputs doubled | 8.69 | 89.35% |
| HbA1c +1.0 | 10.72 | 80.26% |

- Synthetic test-only transformations
- No retraining or setting selection from these results
- Not a claim of distributional robustness

## Slide 13 — Alerts are not AUROC

### Measure event detection and false-alert burden separately

| Threshold | Window precision | Episode sensitivity | False alerts/day |
|---|---:|---:|---:|
| 0.10 | 31.8% | 22.7% | 0.250 |
| 0.20 | 33.3% | 18.2% | 0.133 |
| 0.50 | 0.0% | 0.0% | 0.050 |

- 22 synthetic episodes across 12 test patients
- Project endpoint: four readings strictly above 180 mg/dL
- Small synthetic cohort: no clinical alert claim

## Slide 14 — Live demo

### Walk through evidence before estimates

1. Show synthetic/non-clinical warning
2. Select a held-out patient
3. Replay +5 minutes
4. Inspect history, forecast heads, and intervals
5. Enable dropout and show abstention
6. Review scenario disclaimer and measured evidence

## Slide 15 — Safety and transparency

### Clear boundaries are part of the product

- No real patient data, diagnosis, dosing, or medication change
- Drivers are observed context, not causal attribution
- Scenario changes are sandbox assumptions, not treatment effects
- No hidden future data in replay predictions
- Useful not-ready, loading, error, and unavailable states

## Slide 16 — Reproducibility

### Local artifacts, explicit provenance

- Seed 2026; local synthetic generation
- Joblib bundle plus strict-JSON metrics and provenance
- Engine loads artifacts and never trains automatically
- Local API and dashboard
- Tests and a repeatable smoke path

## Slide 17 — Limitations

### What this prototype does not prove

- Clinical validity or real-patient generalization
- Independent samples from correlated replay windows
- Robustness under arbitrary sensor failures or shifts
- Causal treatment effects or physiological identification
- Reliable clinical alerting from a small synthetic cohort

## Slide 18 — Closing

### A reproducible foundation for honest forecasting research

- Past-only temporal features
- Measured uncertainty and probability calibration
- Data-quality warnings and abstention
- Explicit baseline comparisons and stress tests
- Every result labeled synthetic and non-clinical

**Presenter note:** Close with measured capabilities and next validation needs. Do not promise ranking, selection, clinical benefit, or deployment readiness.
