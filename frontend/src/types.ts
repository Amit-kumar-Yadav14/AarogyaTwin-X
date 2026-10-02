export type NullableNumber = number | null;

export type Patient = {
  id: string;
  name: string;
  age: number;
  sex: string;
  bmi: number;
  hba1c: number;
  diabetes_years: number;
  medications: string[];
  split: string;
  min_step: number;
  max_step: number;
  default_step: number;
};

export type ForecastPoint = {
  minutes_ahead: number;
  timestamp: string;
  glucose: number;
  lower: number;
  upper: number;
};

export type SnapshotStatus = {
  twin: string;
  event: 'at_risk' | 'above_threshold' | 'unknown';
  data_quality: 'good' | 'degraded' | 'insufficient';
  sensor_dropout: boolean;
  cgm_age_minutes: NullableNumber;
  missing_fraction_60m: number;
};

export type Snapshot = {
  patient: Patient;
  timestamp: string;
  step: number;
  status: SnapshotStatus;
  current: {
    glucose: NullableNumber;
    heart_rate: NullableNumber;
    hrv: NullableNumber;
    steps_60m: number;
    sleep_hours: number;
    glucose_slope: NullableNumber;
  };
  predictions: {
    available: boolean;
    reason: string | null;
    risk_120m: NullableNumber;
    glucose_30m: NullableNumber;
    glucose_60m: NullableNumber;
    glucose_120m: NullableNumber;
    predicted_peak: NullableNumber;
    interval_coverage_target: number;
    interval_method: string;
    personalized: boolean;
  };
  history: Array<{
    timestamp: string;
    glucose: NullableNumber;
    heart_rate: NullableNumber;
    hrv: NullableNumber;
    steps: number;
    meal_carbs: number;
  }>;
  forecast: ForecastPoint[];
  drivers: Array<{
    label: string;
    value: NullableNumber;
    unit: string;
    interpretation: string;
  }>;
  warnings: string[];
  evidence_summary: string;
  provenance: {
    data: string;
    model_version: string;
    simulation_version: string;
    calibration_split: string;
    risk_semantics: string;
    explanation: string;
  };
};

export type Scenario = {
  baseline: ForecastPoint[];
  scenario: ForecastPoint[];
  activity_minutes: number;
  meal_carbs: number;
  assumptions: string[];
  disclaimer: string;
};

export type HealthResponse = {
  status: 'ready' | 'not_ready';
  data_mode: 'synthetic';
  message: string;
};

export type PatientsResponse = { patients: Patient[] };

export type MetricsPayload = {
  data_mode?: string;
  seed?: number | string | null;
  cohort?: Record<string, unknown> | null;
  event_definition?: string | Record<string, unknown> | null;
  models?: Record<string, unknown> | Array<Record<string, unknown>> | null;
  forecast?: Record<string, unknown> | Array<Record<string, unknown>> | null;
  limitations?: string[] | null;
  [key: string]: unknown;
};

export type AsyncState<T> = {
  data: T | null;
  loading: boolean;
  error: string | null;
};
