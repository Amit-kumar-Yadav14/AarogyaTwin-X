# AarogyaTwin-X structured evidence summary

**Evidence status:** synthetic development evidence only  
**Artifact seed:** `2026`  
**Artifact version:** `aarogya-day3-bundle-v1`  
**Evaluation date/context:** saved Day-3 artifact results; no new training or retraining performed for this summary

## 1. Scope and boundaries

AarogyaTwin-X is a local research prototype. It is not a diagnostic device, clinical decision tool, treatment-effect estimator, or source of medical advice.

- All patient records, observations, labels, forecasts, and metrics are synthetic.
- No public CGM benchmark or real patient data was used.
- The API is local-only.
- Simulator parameters are not measured physiological states.
- The adaptive residual is not a clinically identified insulin-sensitivity model.
- No medication, dosing, diagnosis, or treatment recommendation is produced.

## 2. Data and evaluation design

| Item | Saved design |
|---|---:|
| Synthetic patients | 60 |
| Synthetic days per patient | 5 |
| Observation grid | 5 minutes |
| Feature-anchor interval | 30 minutes |
| Training patients | 36 |
| Calibration patients | 12 |
| Calibration-tuning patients | 6 |
| Calibration-interval patients | 6 |
| Held-out test patients | 12 |
| Test patient-days | 60 |

The global models are fitted on training patients. Probability calibration and residual-strength selection use calibration-tuning patients. Forecast interval widths use separate calibration-interval patients. Test patients are not used to select model settings.

## 3. Forecast definition and results

The served forecast uses temporal lag features plus bounded causal-in-time residual personalization. It reports named heads at 30, 60, and 120 minutes. Intervals use split-conformal absolute residual widths from calibration-interval patients.

| Horizon | MAE (mg/dL) | RMSE (mg/dL) | Interval coverage | Mean interval width (mg/dL) |
|---:|---:|---:|---:|---:|
| 30 min | 7.21 | 9.76 | 89.95% | 30.04 |
| 60 min | 7.85 | 10.42 | 89.36% | 32.08 |
| 120 min | 8.38 | 11.00 | 90.00% | 34.93 |

Coverage target: 90%. These values are held-out synthetic results, not clinical accuracy.

## 4. Event-probability calibration

The event endpoint is a new sustained episode within 120 minutes. The threshold is strictly above `180 mg/dL`; confirmation requires four consecutive 5-minute readings. Anchors already above threshold and rows with missing future readings are not assigned negative labels.

Fusion classifier results on 1,510 valid held-out event windows:

| Metric | Before probability calibration | After probability calibration |
|---|---:|---:|
| AUROC | 0.94330 | 0.94330 |
| AUPRC | 0.27652 | 0.27652 |
| Brier score | 0.05035 | **0.02437** |
| Log loss | 0.18466 | **0.13559** |
| Expected calibration error | 0.05814 | **0.02387** |

The calibrated probabilities are better on proper scoring and calibration metrics in this synthetic test, while ranking metrics remain unchanged.

## 5. Missingness and abstention

The prediction policy abstains when no CGM is available or the latest CGM is older than 15 minutes.

| Scenario | Horizon | MAE | RMSE | Coverage | Abstention |
|---|---:|---:|---:|---:|---:|
| Natural simulator missingness | 30 min | 7.19 | 9.70 | 90.02% | 0.33% |
| Natural simulator missingness | 60 min | 7.85 | 10.40 | 89.36% | 0.36% |
| Natural simulator missingness | 120 min | 8.60 | 11.25 | 89.46% | 0.36% |
| Recent streams ~25% missing | 30 min | 7.37 | 10.05 | 89.26% | 0.33% |
| Recent streams ~25% missing | 60 min | 8.02 | 10.58 | 89.03% | 0.36% |
| Recent streams ~25% missing | 120 min | 8.63 | 11.25 | 89.35% | 0.36% |
| Recent CGM dropout, 30 min | all | Not measured | Not measured | Not measured | **100%** |

The complete-dropout case has no forecast score because the system intentionally refuses to guess.

Event-label exclusions are never converted to negative labels. The saved artifact records 4,141 excluded/contract-ineligible train rows, 1,457 calibration rows, and 1,322 test rows; `None` includes anchors already above threshold and rows with missing future readings.

## 6. Synthetic distribution-shift stress tests

The model was frozen. Shifts were applied only to held-out synthetic test inputs; no shifted result selected a model setting.

| Test-only shift | 120-minute MAE | 120-minute RMSE | Coverage |
|---|---:|---:|---:|
| Nominal held-out test | 8.60 | 11.25 | 89.46% |
| Glucose level +25 mg/dL | 15.39 | 18.40 | 62.09% |
| Meal carbohydrate inputs doubled | 8.69 | 11.36 | 89.35% |
| HbA1c static input +1.0 | 10.72 | 13.78 | 80.26% |

These are stress-test results, not claims of distributional robustness. The glucose-level shift causes the largest degradation.

## 7. Event-level alert results

There were 22 unique synthetic event episodes across 12 held-out test patients. Alert metrics use the calibrated fusion classifier and 60 test patient-days.

| Probability threshold | Window precision | Window sensitivity | Window F1 | Episode sensitivity | Median lead | False alerts / patient-day |
|---:|---:|---:|---:|---:|---:|---:|
| 0.10 | 31.8% | 17.9% | 0.230 | 22.7% | 70 min | 0.250 |
| 0.20 | 33.3% | 10.3% | 0.157 | 18.2% | 70 min | 0.133 |
| 0.50 | 0.0% | 0.0% | Not defined | 0.0% | Not available | 0.050 |

The threshold changes the trade-off between sensitivity and false alerts. These results are synthetic and should not be interpreted as clinical alert performance.

## 8. Reproducibility and checks

The saved Day-3 evidence was produced from the seeded local artifact pipeline. The final approved verification pass reported:

- Backend tests: `6 passed`
- Synthetic artifact build: passed for 60 patients, 5 days, seed `2026`
- Frontend TypeScript/Vite build: passed
- Local API smoke test: passed
- Calibration roles verified patient-disjoint
- CGM dropout verified to abstain
- No public benchmark stretch goal used

## 9. Known limitations

- Results come from one seeded simulator and are not external validation.
- Replay windows are correlated within patients; row counts are not independent subjects.
- Event prevalence is low and the held-out cohort is small for alert-level conclusions.
- Distribution-shift results show that interval coverage can fail under changed conditions.
- Missingness tests use controlled synthetic patterns and do not represent all sensor-failure modes.
- No causal treatment effect, medication recommendation, diagnosis, or clinical validation is provided.
