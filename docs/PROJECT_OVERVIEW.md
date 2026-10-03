# AarogyaTwin-X: simple project overview

## 1. Why was this project built?

AarogyaTwin-X was built as a **local synthetic research prototype** to demonstrate how a glucose forecasting workflow could be designed responsibly.

The main idea is not only to show a prediction. The project also shows:

- What data was available at prediction time
- Whether the recent CGM signal was fresh enough
- How uncertain the forecast was
- What happens when sensor data disappears
- How the model performs on held-out patients
- Where the system fails under synthetic distribution shifts
- What the model cannot claim

The project was designed for a short CPU-friendly build, a reproducible demo, and an honest competition/research presentation—not for clinical deployment.

> **Important:** This is not a diagnostic device, clinical validation, medical advice system, dosing tool, or treatment recommendation system.

## 2. What data does it use?

The project uses **only generated synthetic data**.

The synthetic cohort contains:

- 60 artificial patients
- 5 synthetic days for every patient
- A reading grid of every 5 minutes
- Glucose/CGM readings
- Heart rate
- Heart-rate variability
- Sleep context
- Activity/steps
- Meal carbohydrate observations
- Static fields such as age, BMI, HbA1c, diabetes duration, and medication labels

The simulator adds realistic-looking variation:

- Different patient patterns
- Daily rhythms
- Meals and activity
- Correlated noise
- Missing observations
- CGM gaps

The simulator's hidden settings are not treated as measured physiology. They are only used internally to generate artificial observations.

## 3. How is the data split?

The split is by **patient**, not only by individual rows:

- 36 patients: global model training
- 6 patients: probability calibration and residual-strength tuning
- 6 different patients: forecast interval calibration
- 12 patients: final held-out testing

The test patients are not used to choose model settings.

This prevents the model from simply memorizing the same patient in both training and testing.

## 4. How does the model work?

### Step 1: Past-only features

At a selected replay time, the model sees only information available up to that time.

It uses:

- Recent glucose values
- Glucose changes over 15, 30, and 60 minutes
- Recent heart rate and HRV
- Recent meals and activity
- Sleep context
- Static patient information
- Missingness indicators

It cannot use future readings when producing a current forecast.

### Step 2: Temporal forecast model

A CPU-friendly gradient-boosting model produces three named glucose forecast heads:

- 30 minutes ahead
- 60 minutes ahead
- 120 minutes ahead

The connecting line in the chart is only visual interpolation. It does not mean that every minute between those points has an independently calibrated forecast.

### Step 3: Event probability

The project defines a new sustained high-glucose event as:

- Glucose strictly above `180 mg/dL`
- Four consecutive readings
- Each reading five minutes apart
- A 15-minute confirmation span

If the current anchor is already above the threshold, the system does not assign a new-event probability.

### Step 4: Probability calibration

The event probability is calibrated separately from the classifier using calibration-tuning patients.

This checks whether a probability such as 20% behaves more like a measured 20% probability in the synthetic evaluation.

### Step 5: Forecast intervals

Forecast uncertainty intervals are calculated from separate calibration-interval patients using split-conformal residual widths.

The interval is not a guarantee. It communicates measured uncertainty on the saved synthetic evaluation.

### Step 6: Patient residual adjustment

The model can use a small patient-specific correction:

1. Make a forecast.
2. Wait until that forecast's target timestamp arrives.
3. Observe the synthetic actual value.
4. Calculate the past error.
5. Use a short, bounded error history for later forecasts.

This is a **causal-in-time adaptive residual**. It is not a clinically identified insulin-sensitivity model.

## 5. What does the dashboard show?

### Synthetic research warning

The top ribbon says:

```text
SYNTHETIC RESEARCH
NOT FOR CLINICAL USE
```

This warning is always visible.

### API status

The dashboard reports whether the local API is ready, loading, or unavailable.

It does not insert fake medical numbers if the backend is unavailable.

### Patient selector

Only held-out synthetic test patients are shown. The panel includes synthetic demographics, evaluation split, and replay range.

### Replay clock

The replay clock moves in five-minute steps. At every position, the model uses only observations available up to that point.

### Current summary

The summary shows:

- Latest observed glucose
- Recent glucose slope
- Heart rate
- Steps during the last hour
- Sleep context
- CGM freshness
- Recent missingness
- Event state

### History panel

The history chart shows observations available before the replay clock. Missing values are shown as unavailable rather than replaced with invented values.

### Observed drivers

The drivers panel shows recent context such as:

- CGM
- Glucose slope
- Activity
- Meal history
- Heart rate

These are observed context signals. They are not SHAP explanations, causal claims, or treatment effects.

### Forecast panel

The forecast panel shows:

- 30-minute estimate
- 60-minute estimate
- 120-minute estimate
- Interval around each estimate
- 120-minute event risk when it is valid
- Data-quality warnings
- Interval method and calibration target

If CGM is too stale, the forecast is withheld and estimates become null.

### CGM dropout

The dropout switch removes the latest 30 minutes of CGM input.

The expected behavior is:

- Warning appears
- Data quality becomes insufficient
- Forecast becomes unavailable
- Risk becomes null
- The engine explains that it abstained

This is safer than pretending the missing signal is fresh.

### Scenario panel

The scenario panel compares the baseline forecast with an assumption-based sandbox scenario.

Inputs are limited to:

- 0–30 minutes of assumed activity
- 0–100 g of assumed carbohydrate

These are sandbox limits, not recommendations. The scenario is not a treatment-effect estimate and must not be used for dosing or care decisions.

### Evidence panel

The evidence panel shows deterministic information assembled by the API:

- Synthetic data description
- Model version
- Simulation version
- Calibration split
- Risk semantics
- Limitations

It is not an LLM-generated clinical explanation.

### Metrics panel

The metrics panel displays saved synthetic held-out results, including:

- Forecast MAE and RMSE
- Interval coverage and width
- Event AUROC and AUPRC
- Brier score and log loss
- Calibration error
- Missingness tests
- Distribution-shift stress tests
- Alert-level metrics
- Declared limitations

## 6. Main measured synthetic results

Final served forecast results:

| Horizon | MAE | RMSE | Coverage | Mean interval width |
|---:|---:|---:|---:|---:|
| 30 minutes | 7.21 mg/dL | 9.76 mg/dL | 89.95% | 30.04 mg/dL |
| 60 minutes | 7.85 mg/dL | 10.42 mg/dL | 89.36% | 32.08 mg/dL |
| 120 minutes | 8.38 mg/dL | 11.00 mg/dL | 90.00% | 34.93 mg/dL |

Calibrated fusion event classifier:

- AUROC: `0.94330`
- AUPRC: `0.27652`
- Brier score: `0.02437`
- Log loss: `0.13559`
- Expected calibration error: `0.02387`

These results describe this seeded simulator and held-out synthetic patients only.

## 7. Advantages of the project

### 7.1 Synthetic-only and privacy-safe for development

No real patient information is needed for the prototype. This makes early development, testing, and demonstrations safer.

### 7.2 Patient-disjoint evaluation

The test patients are separate from training patients. This is stronger than randomly splitting rows from the same patients.

### 7.3 Past-only replay design

The replay engine is designed to prevent future data from entering current features. This makes the demo closer to a real-time workflow.

### 7.4 Honest uncertainty

The dashboard does not show only a point estimate. It shows intervals, calibration information, data freshness, and reasons for abstention.

### 7.5 Safe missing-data behavior

When recent CGM is too old, the system refuses to produce a forecast instead of silently guessing.

### 7.6 Reproducible local execution

The simulator uses a fixed seed and creates local artifacts, metrics, provenance, and a manifest.

### 7.7 CPU-friendly architecture

The model runs on a normal CPU without CUDA, a large GPU, or large downloaded model weights.

### 7.8 Useful evidence beyond one accuracy number

The project reports:

- Forecast error
- Interval coverage
- Probability calibration
- Missingness behavior
- Distribution-shift behavior
- Event-level alert burden

### 7.9 Clear research boundaries

The dashboard explicitly avoids calling observed context causal attribution and avoids presenting synthetic metrics as clinical proof.

## 8. Disadvantages and limitations

### 8.1 Synthetic data is not real physiology

The simulator may look realistic while still missing important real-world behavior. Good synthetic metrics do not prove real-patient performance.

### 8.2 No clinical validation

The project has not been validated by clinicians, hospitals, prospective studies, or real CGM data.

### 8.3 Small held-out patient count

Only 12 patients are in the final test split. Alert-level results, especially episode sensitivity, should be treated as exploratory.

### 8.4 Correlated replay windows

Many 30-minute anchors from the same patient are related to each other. The number of rows is therefore not the same as the number of independent subjects.

### 8.5 Distribution shift can hurt performance

Under a synthetic glucose-level shift of `+25 mg/dL`, 120-minute interval coverage fell to about `62%`. This shows that the model is not automatically robust to changed conditions.

### 8.6 Alert sensitivity is limited

The synthetic alert results show a trade-off between false alerts and episode detection. They are not ready for clinical alerting.

### 8.7 Intervals are not universal guarantees

Conformal-style intervals are measured under the calibration setup. They can fail when the data distribution changes.

### 8.8 Residual personalization is limited

The patient residual is a bounded correction based on past prediction errors. It does not identify physiology, insulin sensitivity, or treatment response.

### 8.9 Scenario panel is not causal

The activity and meal scenario uses fixed illustrative assumptions. It does not estimate what would happen after a real intervention.

### 8.10 Local setup is still required

The user must start the local API and frontend, and artifacts must exist before forecasts are available.

## 9. How to run it in VS Code

### First time

```bash
cd /home/xking/projects/health
source .venv/bin/activate
python -m pip install -r backend/requirements.txt
cd frontend
npm install
cd ..
```

If artifacts are missing:

```bash
PYTHON_BIN="$PWD/.venv/bin/python" ./scripts/train.sh
```

### Terminal 1: API

```bash
cd /home/xking/projects/health
source .venv/bin/activate
PYTHON_BIN="$PWD/.venv/bin/python" ./scripts/run_api.sh
```

### Terminal 2: dashboard

```bash
cd /home/xking/projects/health/frontend
npm run dev
```

Open:

```text
http://127.0.0.1:5173
```

API documentation:

```text
http://127.0.0.1:8000/docs
```

Stop both services with `Ctrl+C` in their terminals.

## 10. One-line summary

AarogyaTwin-X is a synthetic, local, leakage-aware glucose forecasting demo that combines temporal forecasts, uncertainty, calibration, replay, missing-data abstention, evidence, and limitations—but it is not a clinically validated or treatment-guidance system.
