# Day-1 integration contract

All numeric API values must be finite or JSON null. ISO-8601 timestamps include an
offset. All returned patients and streams are synthetic. API binds to localhost.

## Prediction engine interface (owned by backend implementation)

Module `backend/aarogya/engine.py` exports:

```python
class TwinEngine:
    def __init__(self, artifact_dir: pathlib.Path): ...  # raises FileNotFoundError if unbuilt
    def list_patients(self) -> list[dict]: ...
    def snapshot(self, patient_id: str, step: int | None = None,
                 sensor_dropout: bool = False) -> dict: ...
    def simulate(self, patient_id: str, step: int | None = None,
                 activity_minutes: int = 15, meal_carbs: int = 0,
                 sensor_dropout: bool = False) -> dict: ...
    def metrics(self) -> dict: ...
```

Unknown patient: `KeyError`; out-of-range step: `ValueError`.
Module `backend/aarogya/pipeline.py` provides a CLI:
`python -m aarogya.pipeline --output artifacts --patients 60 --days 5 --seed 2026`.
It saves the model/data needed by TwinEngine, `metrics.json`, and provenance under
the supplied output path. Engine initialization reads artifacts; it never trains
automatically. There is no network dependency for data generation or inference.

## HTTP surface (owned by main integration)

- `GET /api/health` -> `{status: "ready" | "not_ready", data_mode: "synthetic", message: string}`
- `GET /api/patients` -> `{patients: Patient[]}`
- `GET /api/twin/{id}?step=480&sensor_dropout=false` -> Snapshot
- `POST /api/twin/{id}/simulate` body `{step?: number, activity_minutes: number,
  meal_carbs: number, sensor_dropout?: boolean}` -> Scenario
- `GET /api/metrics` -> Metrics

Patient:
```typescript
type Patient = {
  id: string; name: string; age: number; sex: string; bmi: number; hba1c: number;
  diabetes_years: number; medications: string[]; split: string;
  min_step: number; max_step: number; default_step: number;
};
```

Snapshot:
```typescript
type ForecastPoint = {
  minutes_ahead: number; timestamp: string;
  glucose: number; lower: number; upper: number;
};
type Snapshot = {
  patient: Patient; timestamp: string; step: number;
  status: {
    twin: string; event: "at_risk" | "above_threshold" | "unknown";
    data_quality: "good" | "degraded" | "insufficient";
    sensor_dropout: boolean; cgm_age_minutes: number | null;
    missing_fraction_60m: number;
  };
  current: {
    glucose: number | null; heart_rate: number | null; hrv: number | null;
    steps_60m: number; sleep_hours: number; glucose_slope: number | null;
  };
  predictions: {
    available: boolean; reason: string | null; risk_120m: number | null;
    glucose_30m: number | null; glucose_60m: number | null;
    glucose_120m: number | null; predicted_peak: number | null;
    interval_coverage_target: number; interval_method: string;
    personalized: boolean;
  };
  history: {
    timestamp: string; glucose: number | null; heart_rate: number | null;
    hrv: number | null; steps: number; meal_carbs: number;
  }[];
  forecast: ForecastPoint[];
  drivers: {label: string; value: number | null; unit: string; interpretation: string}[];
  warnings: string[]; evidence_summary: string;
  provenance: {data: string; model_version: string; simulation_version: string;
    calibration_split: string; risk_semantics: string; explanation: string};
};
```

`forecast` contains calibrated head locations 30, 60 and 120 minutes only; connecting
lines between them are visual interpolation, not independently calibrated forecasts.
The UI must not call the maximum of three sampled horizons a guaranteed future peak.
`drivers` are observed context, NOT SHAP explanations or causal model attribution.
When predictions are unavailable, forecast is empty and estimates/risk are null.
If glucose is already above threshold, show that state instead of a new-event risk.
The summary is deterministic evidence formatting, not an LLM-generated answer.

Scenario:
```typescript
type Scenario = {
  baseline: ForecastPoint[]; scenario: ForecastPoint[];
  activity_minutes: number; meal_carbs: number;
  assumptions: string[]; disclaimer: string;
};
```

Activity range 0–30 minutes and carbohydrate input 0–100 g are sandbox input limits,
not recommendations. Do not modify medications. Scenario bounds are inherited
illustrative bands, not calibrated intervention uncertainty; label that clearly.

Metrics: flexible JSON, with required top-level fields `data_mode: "synthetic"`,
`seed`, `cohort` (patients, days, split counts), `event_definition`, `models`
(named baseline results), `forecast` (horizon results), `limitations: string[]`.
Classification results should expose `auroc`, `auprc`, `brier`, `prevalence`,
`n_test`, with undefined values represented by null. Forecast horizons expose
`mae`, `rmse`, `empirical_coverage`, `mean_interval_width`, `n_test`.
Additional measured results are welcome; do not fabricate alert-level performance.

## UI expectations

Use Vite proxy `/api` to `http://127.0.0.1:8000`. Frontend dev port is 5173.
No fallback mock values. Useful loading/error/not-trained states, abort stale
requests, and prevent replay/scenario races. Replay advances one 5-minute step
and stops at max_step. Patient changes clear scenario state. A CGM dropout toggle
removes the most recent 30 minutes of CGM observations from the model input.
Metrics, synthetic-data label and not-for-clinical-use warning must stay accessible.
