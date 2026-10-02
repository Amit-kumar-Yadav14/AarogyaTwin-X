# AarogyaTwin-X Day-2 explanation

## What was built today

Today we improved the Day-1 glucose forecasting prototype. The system still uses only synthetic data and remains a local research prototype, not a diagnostic device or medical advice tool.

### 1. What data the system uses

The simulator creates:

- 60 artificial patients
- 5 days of data for each patient
- Glucose readings every 5 minutes
- Heart rate and heart-rate variability
- Sleep and activity observations
- Meal carbohydrate observations
- Static information such as age, BMI, HbA1c, diabetes duration, and medication labels

The patients remain separated into:

- 36 training patients
- 12 calibration patients
- 12 held-out test patients

The test patients are never used to train the global model or choose the personalization settings.

No real patient data is used.

### 2. Better use of time history

The Day-1 model mostly used summaries such as recent averages and trends.

Today we added explicit time-history features. The model can now see past values at several points over the previous hour, including:

- Current and earlier glucose values
- Heart rate and HRV values
- Activity and meal values
- Sleep values
- Glucose changes over the previous 15, 30, and 60 minutes

The model only sees data available at the selected replay time. It does not see future observations when making a forecast.

This is still a CPU-friendly gradient-boosting model, not a large neural network.

### 3. Causal-in-time personalization

The global model learns general patterns from the training patients. We then added a small patient-specific correction.

In simple terms:

1. The global model makes a forecast for a patient.
2. Later, when the forecast’s target time has arrived and the real synthetic glucose value is available, the system calculates how far the forecast was from that value.
3. The system keeps a short history of those past errors for that patient.
4. Future forecasts can receive a small bounded correction based on those already-observed errors.

The correction:

- Uses only matured past forecast errors
- Is kept separate for each patient
- Uses a short bounded history
- Is limited to a maximum adjustment of 30 mg/dL
- Has its strength selected using calibration patients only
- Is never allowed to use the current forecast’s future target

This is an **adaptive residual correction**. It is not a clinically identified insulin-sensitivity model and should not be interpreted as one.

### 4. Baselines and ablations

We added explicit comparisons so the learned model can be judged against simpler alternatives.

The forecast comparisons are:

- Day-1 summary-feature model
- Last observed glucose value
- Patient’s running mean glucose through the replay point
- Temporal model without personalization
- Temporal model with causal residual personalization

The event classifier also keeps feature-group comparisons:

- Static patient information only
- Sensor/history information only
- Combined information
- A simple prevalence-based comparator

These comparisons are measured on the held-out synthetic test patients.

### 5. Evaluation results

The final held-out synthetic forecast results are shown as MAE, followed by RMSE:

| Forecast model | 30 minutes | 60 minutes | 120 minutes |
|---|---:|---:|---:|
| Day-1 summary baseline | 7.21 (9.72) | 7.91 (10.45) | 8.66 (11.30) |
| Last observed glucose | 9.73 (14.09) | 12.27 (17.18) | 14.03 (18.68) |
| Patient running-mean glucose | 11.26 (14.99) | 11.38 (15.09) | 11.56 (15.26) |
| Temporal model, no personalization | 7.21 (9.76) | 7.85 (10.42) | 8.60 (11.25) |
| Temporal model with personalization | 7.21 (9.76) | 7.86 (10.44) | **8.38 (11.00)** |

The main result is that the learned models perform better than the two naive baselines. Personalization helped most at the 120-minute horizon. It did not improve every horizon, so the system records the actual before-and-after results rather than claiming a universal improvement.

The selected personalization strengths were:

- 30 minutes: `0.00`
- 60 minutes: `0.25`
- 120 minutes: `0.25`

The forecast interval coverage remained close to its 90% target:

- 30 minutes: `89.84%`
- 60 minutes: `89.91%`
- 120 minutes: `89.53%`

These are measurements on this particular simulator. They are not clinical accuracy results.

### 6. What the dashboard now shows

The dashboard still shows:

- A held-out synthetic patient
- Replay history and the current replay time
- Current glucose, trend, heart rate, activity, and sleep context
- 30-, 60-, and 120-minute forecast heads
- Forecast uncertainty intervals
- New sustained high-glucose event risk when it is valid
- CGM dropout warnings and prediction abstention
- Provenance and declared limitations

The evaluation section now also exposes the measured model comparisons, including both naive forecast baselines and the before-versus-after personalization results.

The dashboard continues to label context signals as observed context, not causal explanations. Scenario inputs remain an assumption-based sandbox, not a treatment estimate or medical recommendation.

## In short

Today we gave the model a better memory of recent time history, added a carefully bounded patient-specific correction based only on already-known past errors, and added simple baselines so the results can be judged honestly.

Everything remains synthetic, patient-disjoint, local, and explicitly not for clinical use.
