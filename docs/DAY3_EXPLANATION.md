# AarogyaTwin-X Day-3 explanation

## What Day 3 added

Day 3 focused on answering a practical question:

> Can the system report how trustworthy its forecasts and alerts are, especially when data quality or patient conditions change?

All evaluations use seeded synthetic data only. The system remains a local research prototype, not a diagnostic device or clinical decision tool.

## 1. Better calibration

Calibration checks whether a probability or uncertainty interval matches what actually happens.

We added:

- Separate patient-disjoint calibration roles:
  - 6 calibration-tuning patients for probability calibration
  - 6 calibration-interval patients for forecast intervals
  - 12 held-out test patients
- Platt sigmoid calibration for event probabilities
- Brier score, log loss, expected calibration error, and reliability bins
- Explicit finite-sample conformal interval calculations

For the fusion event classifier on held-out synthetic rows:

| Metric | Before calibration | After calibration |
|---|---:|---:|
| Brier score | 0.05035 | **0.02437** |
| Log loss | 0.18466 | **0.13559** |
| Expected calibration error | 0.05814 | **0.02387** |

Lower is better for all three metrics. AUROC stayed at `0.94330` and AUPRC at `0.27652`.

The final forecast intervals were close to the 90% target:

| Horizon | Coverage | Mean interval width |
|---|---:|---:|
| 30 minutes | 89.95% | 30.04 mg/dL |
| 60 minutes | 89.36% | 32.08 mg/dL |
| 120 minutes | 90.00% | 34.93 mg/dL |

These are synthetic held-out measurements, not clinical validation.

## 2. Missingness tests

We tested how the frozen model behaves when data is incomplete:

- Natural simulator missingness
- Approximately 25% missingness in recent sensor streams
- Complete 30-minute CGM dropout

At the 30-minute horizon:

| Condition | MAE | RMSE | Interval coverage | Abstention |
|---|---:|---:|---:|---:|
| Natural missingness | 7.19 | 9.70 | 90.02% | 0.33% |
| 25% recent stream missingness | 7.37 | 10.05 | 89.26% | 0.33% |
| 30-minute CGM dropout | Not measured | Not measured | Not measured | **100%** |

The complete dropout case intentionally produces no forecast. When the latest CGM is older than 15 minutes, the engine abstains rather than guessing.

Unknown or contract-ineligible event rows are excluded, never treated as negative. This includes anchors already above the threshold and rows with missing future readings.

## 3. Synthetic distribution-shift tests

We evaluated the model without retraining after applying controlled shifts only to held-out synthetic test inputs:

- Glucose level shifted by `+25 mg/dL`
- Meal carbohydrate inputs doubled
- HbA1c shifted by `+1.0`

At 120 minutes:

| Condition | MAE | RMSE | Interval coverage |
|---|---:|---:|---:|
| Nominal test | 8.60 | 11.25 | 89.46% |
| Glucose level +25 mg/dL | 15.39 | 18.40 | 62.09% |
| Meal inputs doubled | 8.69 | 11.36 | 89.35% |
| HbA1c +1.0 | 10.72 | 13.78 | 80.26% |

The largest degradation occurs under the shifted glucose-level condition. This is a stress-test result, not ordinary test performance and not evidence of clinical robustness.

## 4. Event-level alert metrics

Day 3 added alert metrics beyond AUROC and AUPRC. They measure both individual forecast windows and unique sustained episodes using the project definition:

- Strictly above `180 mg/dL`
- Four consecutive 5-minute readings
- 15-minute confirmation
- Missing future labels excluded

The held-out synthetic test contained 22 event episodes and 1,510 valid event windows.

| Alert threshold | Window precision | Window sensitivity | Episode sensitivity | Median lead | False alerts / patient-day |
|---:|---:|---:|---:|---:|---:|
| 0.10 | 31.8% | 17.9% | 22.7% | 70 min | 0.25 |
| 0.20 | 33.3% | 10.3% | 18.2% | 70 min | 0.133 |
| 0.50 | 0.0% | 0.0% | 0.0% | Not available | 0.05 |

These results show the trade-off between alert threshold and false-alert burden. They are based on a small synthetic cohort and must not be interpreted as clinical alert performance.

## 5. What is now visible in the dashboard

The evaluation section now exposes:

- Calibrated and uncalibrated probability metrics
- Reliability information
- Forecast interval coverage and width
- Missingness and abstention tests
- Synthetic distribution-shift tests
- Event-level alert metrics
- Declared data, split, and model limitations

## Verification

- Backend tests: `6 passed`
- Synthetic artifact rebuild: passed for 60 patients, 5 days, seed `2026`
- Frontend TypeScript/Vite build: passed
- Local API smoke test: passed
- Public CGM benchmark stretch goal: skipped as requested

## In short

Day 3 made the prototype more honest about uncertainty. It now measures whether probabilities are calibrated, tests what happens when data is missing, shows how performance changes under synthetic distribution shifts, and reports alert behavior at the event level.

All data remains synthetic, patient-disjoint, local, and not for clinical use.
