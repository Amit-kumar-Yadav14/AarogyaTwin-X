"""Deterministic synthetic cohort generation and leakage-safe feature helpers.

The simulator is deliberately modest: it produces enough heterogeneity, rhythms,
meal/activity responses, noise, and missingness to exercise the Day-1 baselines
without pretending that a simulator parameter is a measured physiological state.
Only observed streams are passed to the model feature builders.  Latent simulator
parameters are never included in a feature row or in the serialized patient data.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import math
from typing import Any, Mapping, Sequence

import numpy as np


STEP_MINUTES = 5
STEPS_PER_HOUR = 60 // STEP_MINUTES
EVENT_THRESHOLD = 180.0
EVENT_CONFIRMATION_READINGS = 4
EVENT_HORIZON_MINUTES = 120
EVENT_HORIZON_STEPS = EVENT_HORIZON_MINUTES // STEP_MINUTES
FORECAST_HORIZONS_MINUTES = (30, 60, 120)
FORECAST_HORIZON_STEPS = tuple(h // STEP_MINUTES for h in FORECAST_HORIZONS_MINUTES)
SIMULATION_VERSION = "synthetic-day1-v1"
BASE_TIMESTAMP = datetime(2026, 1, 1, tzinfo=timezone.utc)

EVENT_DEFINITION: dict[str, Any] = {
    "description": "four consecutive readings strictly >180 mg/dL within the future 120-minute window",
    "threshold_mg_dl": EVENT_THRESHOLD,
    "comparison": ">",
    "consecutive_readings": EVENT_CONFIRMATION_READINGS,
    "reading_interval_minutes": STEP_MINUTES,
    "confirmation_span_minutes": (EVENT_CONFIRMATION_READINGS - 1) * STEP_MINUTES,
    "forecast_window_minutes": EVENT_HORIZON_MINUTES,
    "anchor_requirement": "anchor glucose is observed and <= 180 mg/dL",
    "missing_future_policy": "exclude from labels, never treat as a negative",
}


@dataclass(frozen=True)
class CohortConfig:
    """Configuration used by :func:`generate_cohort`."""

    patients: int = 60
    days: int = 5
    seed: int = 2026


def _finite_float(value: Any, default: float | None = None) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    return result if math.isfinite(result) else default


def timestamp_for_step(step: int, base: datetime = BASE_TIMESTAMP) -> str:
    """Return an offset-bearing ISO-8601 timestamp for a five-minute step."""

    return (base + timedelta(minutes=int(step) * STEP_MINUTES)).isoformat()


def _rng_for_patient(seed: int, patient_index: int) -> np.random.Generator:
    # SeedSequence avoids accidental dependence on Python's randomized hash seed.
    sequence = np.random.SeedSequence([int(seed) & 0xFFFFFFFF, int(patient_index), 9173])
    return np.random.default_rng(sequence)


def _make_meals(
    rng: np.random.Generator,
    n_steps: int,
    day_count: int,
    meal_bias: float,
) -> np.ndarray:
    meals = np.zeros(n_steps, dtype=float)
    for day in range(day_count):
        # Slightly jittered breakfast/lunch/dinner slots.  The jitter is bounded
        # so every meal remains inside its day and is reproducible.
        slots = (
            (7.5, 0.16, 25.0),
            (13.0, 0.20, 48.0),
            (19.0, 0.22, 55.0),
        )
        for hour, jitter, typical in slots:
            minute = hour * 60.0 + float(rng.normal(0.0, jitter * 60.0))
            minute = float(np.clip(minute, 60.0, 22.0 * 60.0))
            index = day * 24 * STEPS_PER_HOUR + int(round(minute / STEP_MINUTES))
            if 0 <= index < n_steps:
                size = typical * (1.0 + 0.20 * meal_bias + float(rng.normal(0.0, 0.13)))
                meals[index] += float(np.clip(size, 8.0, 105.0))
        # A subset of patients has a small snack on a random afternoon/evening.
        if rng.random() < 0.58:
            index = day * 24 * STEPS_PER_HOUR + int(rng.integers(15 * STEPS_PER_HOUR, 22 * STEPS_PER_HOUR))
            if index < n_steps:
                meals[index] += float(np.clip(rng.normal(18.0 + 7.0 * meal_bias, 6.0), 5.0, 45.0))
    return meals


def _inject_missingness(
    rng: np.random.Generator,
    values: np.ndarray,
    random_rate: float,
    gap_count: int,
    max_gap: int,
) -> np.ndarray:
    result = np.asarray(values, dtype=float).copy()
    if result.size == 0:
        return result
    random_mask = rng.random(result.size) < random_rate
    result[random_mask] = np.nan
    for _ in range(gap_count):
        if result.size <= 2:
            break
        start = int(rng.integers(0, max(1, result.size - max_gap)))
        length = int(rng.integers(2, max_gap + 1))
        result[start : min(result.size, start + length)] = np.nan
    return result


def _patient_observations(
    rng: np.random.Generator,
    age: int,
    bmi: float,
    hba1c: float,
    diabetes_years: int,
    n_steps: int,
    days: int,
) -> dict[str, np.ndarray]:
    """Generate observed streams while keeping latent parameters local."""

    time_hours = np.arange(n_steps, dtype=float) / STEPS_PER_HOUR
    hour_of_day = np.mod(time_hours, 24.0)
    # These are simulator-only heterogeneity terms.  They are used to generate
    # observations and intentionally never returned as fields.
    baseline = 94.0 + 8.2 * (hba1c - 5.4) + 0.55 * (bmi - 24.0) + float(rng.normal(0.0, 5.0))
    circadian_phase = float(rng.uniform(-math.pi, math.pi))
    circadian_amp = float(rng.uniform(5.0, 16.0))
    response_gain = float(np.clip(0.84 + 0.055 * (hba1c - 5.5) + rng.normal(0.0, 0.10), 0.50, 1.45))
    activity_response = float(rng.uniform(0.04, 0.15))
    meal_bias = float(np.clip((hba1c - 6.0) / 2.5 + rng.normal(0.0, 0.18), -0.5, 1.5))
    meals = _make_meals(rng, n_steps, days, meal_bias)

    # A short exponential meal response kernel; all arrays are observed or
    # derived from observations, while the coefficients above remain hidden.
    meal_response = np.zeros(n_steps, dtype=float)
    for lag in range(min(30, n_steps)):
        meal_response[lag:] += meals[: n_steps - lag] * math.exp(-lag / 12.0)
    meal_response *= 0.95 * response_gain

    activity = np.zeros(n_steps, dtype=float)
    for day in range(days):
        for start_hour, duration, level in (
            (7.0 + float(rng.normal(0.0, 0.25)), 0.7, 90.0),
            (12.3 + float(rng.normal(0.0, 0.30)), 0.45, 125.0),
            (18.0 + float(rng.normal(0.0, 0.30)), 0.8, 105.0),
        ):
            start = int(np.clip(day * 24 * STEPS_PER_HOUR + start_hour * STEPS_PER_HOUR, 0, n_steps - 1))
            width = max(1, int(duration * STEPS_PER_HOUR))
            end = min(n_steps, start + width)
            activity[start:end] += np.clip(level + rng.normal(0.0, 18.0, end - start), 0.0, None)
    # Light background movement, with a small individual-specific pattern.
    activity += np.clip(rng.normal(7.0 + 2.0 * (age < 40), 4.0, n_steps), 0.0, None)

    sleep_state = ((hour_of_day >= 22.5) | (hour_of_day < 6.5)).astype(float)
    # Sleep stream is rolling sleep duration in hours, not a hidden sleep score.
    sleep_hours = np.zeros(n_steps, dtype=float)
    running = 0
    for i, asleep in enumerate(sleep_state):
        running = running + 1 if asleep else 0
        sleep_hours[i] = min(8.0, running * STEP_MINUTES / 60.0) if asleep else 0.0

    circadian = circadian_amp * np.sin(2.0 * math.pi * (hour_of_day - 5.0) / 24.0 + circadian_phase)
    latent = baseline + circadian + meal_response - activity_response * activity
    # A bounded synthetic dysregulation component makes the event endpoint
    # observable for a small high-HbA1c subgroup without exposing this hidden
    # simulator term to the feature builder.
    latent += max(0.0, hba1c - 7.2) * 14.0
    latent += 0.6 * np.sin(2.0 * math.pi * time_hours / 3.0 + circadian_phase / 2.0)
    # AR-like noise gives realistic local correlation without exposing its state.
    noise = np.zeros(n_steps, dtype=float)
    for i in range(n_steps):
        innovation = float(rng.normal(0.0, 3.8))
        noise[i] = 0.78 * noise[i - 1] + innovation if i else innovation
    glucose = np.clip(latent + noise, 45.0, 360.0)
    # A modest high-glycemic subgroup creates measurable but not guaranteed events.
    if hba1c > 7.6:
        glucose += np.maximum(0.0, meal_response - 32.0) * 0.10
    glucose = np.clip(glucose + rng.normal(0.0, 2.2, n_steps), 40.0, 400.0)

    hr_base = 66.0 + 0.10 * (age - 45.0) + float(rng.normal(0.0, 3.0))
    heart_rate = hr_base + 0.10 * activity + 0.025 * np.maximum(meal_response, 0.0)
    heart_rate += 4.0 * np.sin(2.0 * math.pi * (hour_of_day - 14.0) / 24.0 + circadian_phase / 3.0)
    heart_rate += rng.normal(0.0, 2.8, n_steps)
    heart_rate = np.clip(heart_rate, 38.0, 190.0)

    hrv_base = 54.0 - 0.25 * (age - 40.0) + float(rng.normal(0.0, 5.0))
    hrv = hrv_base - 0.075 * activity - 0.05 * np.maximum(meal_response, 0.0) + 10.0 * sleep_state
    hrv += rng.normal(0.0, 4.0, n_steps)
    hrv = np.clip(hrv, 8.0, 125.0)

    # Missingness is generated independently per observed stream.  No hidden
    # imputation is performed here; the model-side preprocessor handles it.
    glucose = _inject_missingness(rng, glucose, 0.025, max(1, days // 2), 7)
    heart_rate = _inject_missingness(rng, heart_rate, 0.018, max(1, days // 3), 5)
    hrv = _inject_missingness(rng, hrv, 0.022, max(1, days // 3), 5)
    sleep_hours = _inject_missingness(rng, sleep_hours, 0.012, 1, 4)
    activity = _inject_missingness(rng, activity, 0.012, 1, 4)
    meals = _inject_missingness(rng, meals, 0.008, 1, 3)
    glucose = glucose.astype(float)
    return {
        "glucose": glucose,
        # ``glucose`` is the API-facing name; ``cgm`` is a readable alias for
        # callers inspecting the multivariate simulator payload.
        "cgm": glucose.copy(),
        "heart_rate": heart_rate.astype(float),
        "hrv": hrv.astype(float),
        "sleep_hours": sleep_hours.astype(float),
        "activity": activity.astype(float),
        "meal_carbs": meals.astype(float),
    }


def _medications(rng: np.random.Generator, hba1c: float, diabetes_years: int) -> list[str]:
    values: list[str] = []
    if hba1c >= 6.2 or diabetes_years > 0:
        values.append("metformin")
    if hba1c >= 8.0 and rng.random() < 0.65:
        values.append("basal_insulin")
    if not values and rng.random() < 0.20:
        values.append("none_prescribed")
    return values


def _split_patient_ids(patient_ids: Sequence[str], seed: int) -> dict[str, str]:
    ids = list(patient_ids)
    order = np.random.default_rng(np.random.SeedSequence([int(seed) & 0xFFFFFFFF, 4471])).permutation(len(ids))
    # Keep all three splits non-empty for the validated minimum cohort size.
    n = len(ids)
    if n == 1:
        return {ids[int(order[0])]: "train"}
    if n == 2:
        return {ids[int(order[0])]: "train", ids[int(order[1])]: "test"}
    train_n = max(1, int(math.floor(n * 0.60)))
    train_n = min(train_n, n - 2)
    calibration_n = max(1, int(math.floor(n * 0.20)))
    calibration_n = min(calibration_n, n - train_n - 1)
    assignments: dict[str, str] = {}
    for rank, position in enumerate(order):
        if rank < train_n:
            split = "train"
        elif rank < train_n + calibration_n:
            split = "calibration"
        else:
            split = "test"
        assignments[ids[int(position)]] = split
    return assignments


def generate_cohort(patients: int = 60, days: int = 5, seed: int = 2026) -> dict[str, Any]:
    """Generate a seeded synthetic cohort.

    The returned structure contains only static records and observed streams.  It
    is intentionally plain and joblib-friendly so the pipeline can persist it
    without requiring a database or external data source.
    """

    if isinstance(patients, bool) or not isinstance(patients, (int, np.integer)) or int(patients) < 1:
        raise ValueError("patients must be a positive integer")
    if isinstance(days, bool) or not isinstance(days, (int, np.integer)) or int(days) < 1:
        raise ValueError("days must be a positive integer")
    if isinstance(seed, bool) or not isinstance(seed, (int, np.integer)):
        raise ValueError("seed must be an integer")

    patients = int(patients)
    days = int(days)
    seed = int(seed)
    n_steps = days * 24 * STEPS_PER_HOUR
    patient_ids = [f"PT-{index + 1:03d}" for index in range(patients)]
    splits = _split_patient_ids(patient_ids, seed)
    records: dict[str, dict[str, Any]] = {}
    for index, patient_id in enumerate(patient_ids):
        rng = _rng_for_patient(seed, index)
        age = int(rng.integers(19, 81))
        sex = str(rng.choice(np.array(["F", "M", "X"], dtype=object), p=[0.48, 0.49, 0.03]))
        bmi = float(np.clip(rng.normal(27.0, 4.6), 18.0, 43.0))
        hba1c = float(np.clip(rng.normal(6.7 + 0.25 * (age > 60), 0.9), 5.1, 10.2))
        diabetes_years = int(np.clip(round(rng.normal(max(0.0, (hba1c - 5.8) * 3.0), 4.0)), 0, 25))
        medications = _medications(rng, hba1c, diabetes_years)
        observations = _patient_observations(
            rng,
            age,
            bmi,
            hba1c,
            diabetes_years,
            n_steps,
            days,
        )
        default_index = max(0, min(n_steps - 1, n_steps - EVENT_HORIZON_STEPS - 1))
        # Pick a nearby replay anchor with a fresh enough CGM so the initial
        # dashboard view is useful while preserving the fixed patient timeline.
        cgm = observations["glucose"]
        for candidate in range(default_index, max(-1, default_index - 12), -1):
            finite = np.flatnonzero(np.isfinite(cgm[: candidate + 1]))
            if finite.size and candidate - int(finite[-1]) <= 3:
                default_index = candidate
                break
        records[patient_id] = {
            "id": patient_id,
            "name": f"Synthetic Patient {index + 1:03d}",
            "age": age,
            "sex": sex,
            "bmi": round(bmi, 2),
            "hba1c": round(hba1c, 2),
            "diabetes_years": diabetes_years,
            "medications": medications,
            "split": splits[patient_id],
            "min_step": 0,
            # Public replay steps are elapsed minutes (on the five-minute
            # observation grid), matching the API/UI contract's step=480 style.
            "max_step": (n_steps - 1) * STEP_MINUTES,
            "default_step": default_index * STEP_MINUTES,
            "observations": observations,
        }

    return {
        "simulation_version": SIMULATION_VERSION,
        "base_timestamp": BASE_TIMESTAMP.isoformat(),
        "step_minutes": STEP_MINUTES,
        "days": days,
        "seed": seed,
        "patients": records,
    }


def event_label(
    glucose: Sequence[float] | np.ndarray,
    anchor_step: int,
    *,
    threshold: float = EVENT_THRESHOLD,
    horizon_steps: int = EVENT_HORIZON_STEPS,
    confirmation_readings: int = EVENT_CONFIRMATION_READINGS,
) -> int | None:
    """Return the contract event label, or ``None`` when it is unknowable.

    The anchor must have an observed value at or below the strict threshold.  All
    future readings in the 120-minute label window are required to be observed;
    if any are missing, the sample is excluded rather than counted as negative.
    A positive requires four consecutive readings strictly above 180 mg/dL, which
    spans 15 minutes at the five-minute sampling interval.
    """

    values = np.asarray(glucose, dtype=float)
    anchor_step = int(anchor_step)
    horizon_steps = int(horizon_steps)
    confirmation_readings = int(confirmation_readings)
    if anchor_step < 0 or anchor_step >= values.size:
        return None
    anchor = values[anchor_step]
    if not np.isfinite(anchor) or anchor > threshold:
        return None
    start = anchor_step + 1
    end = start + horizon_steps
    if end > values.size:
        return None
    future = values[start:end]
    if future.size < confirmation_readings or not np.isfinite(future).all():
        return None
    above = future > float(threshold)
    if above.size < confirmation_readings:
        return None
    # A run can begin at any future reading, but all confirmation readings must
    # remain inside the 120-minute window.
    for index in range(0, above.size - confirmation_readings + 1):
        if bool(np.all(above[index : index + confirmation_readings])):
            return 1
    return 0


def _last_finite_index(values: np.ndarray, end_step: int) -> int | None:
    if end_step < 0:
        return None
    upto = np.asarray(values[: end_step + 1], dtype=float)
    finite = np.flatnonzero(np.isfinite(upto))
    return int(finite[-1]) if finite.size else None


def _window(values: np.ndarray, end_step: int, width: int) -> np.ndarray:
    start = max(0, int(end_step) - int(width) + 1)
    return np.asarray(values[start : end_step + 1], dtype=float)


def _last_value(values: np.ndarray, end_step: int) -> float | None:
    index = _last_finite_index(values, end_step)
    return None if index is None else _finite_float(values[index])


def _mean(values: np.ndarray) -> float | None:
    finite = values[np.isfinite(values)]
    return None if finite.size == 0 else float(np.mean(finite))


def _std(values: np.ndarray) -> float | None:
    finite = values[np.isfinite(values)]
    return None if finite.size == 0 else float(np.std(finite))


def _slope_per_hour(values: np.ndarray, end_step: int, width: int = 7) -> float | None:
    start = max(0, end_step - width + 1)
    indices = np.arange(start, end_step + 1, dtype=float)
    segment = np.asarray(values[start : end_step + 1], dtype=float)
    mask = np.isfinite(segment)
    if int(mask.sum()) < 2:
        return None
    x = indices[mask] * STEP_MINUTES / 60.0
    y = segment[mask]
    centered = x - float(np.mean(x))
    denominator = float(np.sum(centered * centered))
    if denominator <= 0.0:
        return None
    return float(np.sum(centered * (y - float(np.mean(y)))) / denominator)


def static_feature_vector(record: Mapping[str, Any]) -> tuple[np.ndarray, list[str]]:
    """Build static-only features from observed demographic/lab fields."""

    sex = str(record.get("sex", ""))
    medications = record.get("medications", [])
    if not isinstance(medications, (list, tuple)):
        medications = []
    values = [
        _finite_float(record.get("age")),
        _finite_float(record.get("bmi")),
        _finite_float(record.get("hba1c")),
        _finite_float(record.get("diabetes_years")),
        1.0 if sex == "M" else 0.0,
        1.0 if sex == "X" else 0.0,
        float(len(medications)),
        1.0 if "basal_insulin" in medications else 0.0,
    ]
    names = [
        "age",
        "bmi",
        "hba1c",
        "diabetes_years",
        "sex_male",
        "sex_other",
        "medication_count",
        "has_basal_insulin",
    ]
    return np.asarray([np.nan if value is None else value for value in values], dtype=float), names


def sensor_feature_vector(
    observations: Mapping[str, Sequence[float] | np.ndarray],
    anchor_step: int,
) -> tuple[np.ndarray, list[str]]:
    """Build sensor/history features using observations up to ``anchor_step`` only."""

    arrays = {name: np.asarray(values, dtype=float) for name, values in observations.items()}
    glucose = arrays.get("glucose", arrays.get("cgm", np.full(anchor_step + 1, np.nan)))
    heart_rate = arrays.get("heart_rate", np.full(anchor_step + 1, np.nan))
    hrv = arrays.get("hrv", np.full(anchor_step + 1, np.nan))
    sleep = arrays.get("sleep_hours", np.full(anchor_step + 1, np.nan))
    activity = arrays.get("activity", np.full(anchor_step + 1, np.nan))
    meals = arrays.get("meal_carbs", np.full(anchor_step + 1, np.nan))
    end = min(
        int(anchor_step),
        *(max(-1, array.size - 1) for array in (glucose, heart_rate, hrv, sleep, activity, meals)),
    )
    if end < 0:
        end = int(anchor_step)

    g60 = _window(glucose, end, 12)
    g120 = _window(glucose, end, 24)
    hr60 = _window(heart_rate, end, 12)
    hrv60 = _window(hrv, end, 12)
    sleep120 = _window(sleep, end, 24)
    activity60 = _window(activity, end, 12)
    activity120 = _window(activity, end, 24)
    meals60 = _window(meals, end, 12)
    meals120 = _window(meals, end, 24)
    latest_index = _last_finite_index(glucose, end)
    cgm_age = float((end - latest_index) * STEP_MINUTES) if latest_index is not None else np.nan
    missing60 = float(1.0 - np.isfinite(g60).mean()) if g60.size else 1.0
    values = [
        _last_value(glucose, end),
        _mean(g60),
        _std(g60),
        _mean(g120),
        _slope_per_hour(glucose, end, 7),
        _slope_per_hour(glucose, end, 13),
        cgm_age,
        missing60,
        _last_value(heart_rate, end),
        _mean(hr60),
        _last_value(hrv, end),
        _mean(hrv60),
        _last_value(sleep, end),
        _mean(sleep120),
        float(np.nansum(activity60)),
        float(np.nansum(activity120)),
        float(np.nansum(meals60)),
        float(np.nansum(meals120)),
        math.sin(2.0 * math.pi * ((end * STEP_MINUTES / 60.0) % 24.0) / 24.0),
        math.cos(2.0 * math.pi * ((end * STEP_MINUTES / 60.0) % 24.0) / 24.0),
    ]
    names = [
        "cgm_last",
        "cgm_mean_60m",
        "cgm_std_60m",
        "cgm_mean_120m",
        "cgm_slope_30m_mg_dl_hour",
        "cgm_slope_60m_mg_dl_hour",
        "cgm_age_minutes",
        "cgm_missing_fraction_60m",
        "heart_rate_last",
        "heart_rate_mean_60m",
        "hrv_last",
        "hrv_mean_60m",
        "sleep_hours_last",
        "sleep_hours_mean_120m",
        "activity_steps_60m",
        "activity_steps_120m",
        "meal_carbs_60m",
        "meal_carbs_120m",
        "time_sin",
        "time_cos",
    ]
    return np.asarray([np.nan if value is None else value for value in values], dtype=float), names


def feature_vectors(
    record: Mapping[str, Any],
    anchor_step: int,
    observations: Mapping[str, Sequence[float] | np.ndarray] | None = None,
) -> dict[str, np.ndarray]:
    """Return static, sensor, and fusion vectors for a past-only anchor."""

    visible = observations if observations is not None else record["observations"]
    static, _ = static_feature_vector(record)
    sensor, _ = sensor_feature_vector(visible, int(anchor_step))
    return {"static": static, "sensor": sensor, "fusion": np.concatenate([static, sensor])}


def feature_names() -> dict[str, list[str]]:
    """Return stable names used in the artifact provenance."""

    _, static_names = static_feature_vector(
        {"age": 0, "bmi": 0, "hba1c": 0, "diabetes_years": 0, "sex": "F", "medications": []}
    )
    _, sensor_names = sensor_feature_vector(
        {name: np.zeros(1, dtype=float) for name in ("glucose", "heart_rate", "hrv", "sleep_hours", "activity", "meal_carbs")},
        0,
    )
    return {"static": static_names, "sensor": sensor_names, "fusion": static_names + sensor_names}


def copy_observations_up_to(
    record: Mapping[str, Any],
    step: int,
    *,
    sensor_dropout: bool = False,
) -> dict[str, np.ndarray]:
    """Copy only observations available at ``step`` and optionally drop recent CGM."""

    end = int(step) + 1
    source = record.get("observations", {})
    visible: dict[str, np.ndarray] = {}
    for name in ("glucose", "heart_rate", "hrv", "sleep_hours", "activity", "meal_carbs"):
        fallback = source.get("cgm", np.full(end, np.nan)) if name == "glucose" else np.full(end, np.nan)
        raw = np.asarray(source.get(name, fallback), dtype=float)
        values = np.full(end, np.nan, dtype=float)
        count = min(end, raw.size)
        if count:
            values[:count] = raw[:count]
        visible[name] = values
    if sensor_dropout and visible["glucose"].size:
        # Six five-minute samples ending at the anchor represent the most recent
        # 30-minute interval (timestamps -25m through now).
        visible["glucose"][max(0, end - 6) : end] = np.nan
    return visible


def last_observed_age_minutes(values: Sequence[float] | np.ndarray, step: int) -> float | None:
    array = np.asarray(values, dtype=float)
    index = _last_finite_index(array, min(int(step), array.size - 1))
    return None if index is None else float((int(step) - index) * STEP_MINUTES)


def history_rows(
    observations: Mapping[str, Sequence[float] | np.ndarray],
    step: int,
    *,
    width: int = 36,
) -> list[dict[str, Any]]:
    """Format a bounded, past-only history for the HTTP contract."""

    end = int(step)
    start = max(0, end - int(width) + 1)
    rows: list[dict[str, Any]] = []
    for index in range(start, end + 1):
        def value(name: str) -> float | None:
            array = np.asarray(observations.get(name, []), dtype=float)
            if index >= array.size or not np.isfinite(array[index]):
                return None
            return float(array[index])

        rows.append(
            {
                "timestamp": timestamp_for_step(index),
                "glucose": value("glucose"),
                "heart_rate": value("heart_rate"),
                "hrv": value("hrv"),
                "steps": value("activity") if value("activity") is not None else 0.0,
                "meal_carbs": value("meal_carbs") if value("meal_carbs") is not None else 0.0,
            }
        )
    return rows


__all__ = [
    "BASE_TIMESTAMP",
    "CohortConfig",
    "EVENT_DEFINITION",
    "EVENT_HORIZON_MINUTES",
    "EVENT_HORIZON_STEPS",
    "EVENT_THRESHOLD",
    "FORECAST_HORIZONS_MINUTES",
    "FORECAST_HORIZON_STEPS",
    "SIMULATION_VERSION",
    "STEP_MINUTES",
    "copy_observations_up_to",
    "event_label",
    "feature_names",
    "feature_vectors",
    "generate_cohort",
    "history_rows",
    "last_observed_age_minutes",
    "sensor_feature_vector",
    "static_feature_vector",
    "timestamp_for_step",
]
