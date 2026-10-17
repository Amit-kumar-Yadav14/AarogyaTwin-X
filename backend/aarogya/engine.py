"""Reloadable inference/replay engine for the AarogyaTwin-X API contract."""

from __future__ import annotations

from copy import deepcopy
import math
from pathlib import Path
from typing import Any, Mapping

import joblib
import numpy as np

from .modeling import json_safe
from .simulation import (
    EVENT_THRESHOLD,
    FORECAST_HORIZONS_MINUTES,
    copy_observations_up_to,
    feature_vectors,
    history_rows,
    last_observed_age_minutes,
    timestamp_for_step,
)


MODEL_VERSION = "day3-calibrated-temporal-residual-v1"
INTERVAL_METHOD = "split-conformal absolute residual rank (90%; calibration-interval patients only)"
RISK_SEMANTICS = (
    "Estimated probability of the contract-defined new sustained >180 mg/dL event within 120 minutes; "
    "not a diagnosis or treatment recommendation."
)


def _number(value: Any, default: float | None = None) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    return result if math.isfinite(result) else default


def _integer_step(value: Any, *, field: str = "step") -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field} must be an integer")
    try:
        integer = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be an integer") from exc
    if isinstance(value, float) and not value.is_integer():
        raise ValueError(f"{field} must be an integer")
    return integer


class TwinEngine:
    """Serve held-out synthetic patients from a previously built artifact.

    Construction performs only local artifact loading and validation. It never
    generates data or fits a model; callers must run ``aarogya.pipeline`` first.
    """

    def __init__(self, artifact_dir: Path):
        self.artifact_dir = Path(artifact_dir)
        bundle_path = self.artifact_dir / "bundle.joblib"
        if not bundle_path.is_file():
            raise FileNotFoundError(
                f"AarogyaTwin-X artifacts are not built at {self.artifact_dir}; "
                "run python -m aarogya.pipeline --output <path> first"
            )
        try:
            bundle = joblib.load(bundle_path)
        except FileNotFoundError:
            raise
        except Exception as exc:
            raise FileNotFoundError(f"Could not load AarogyaTwin-X artifact bundle: {bundle_path}") from exc
        if not isinstance(bundle, dict) or not isinstance(bundle.get("cohort"), dict):
            raise FileNotFoundError(f"Invalid AarogyaTwin-X artifact bundle: {bundle_path}")
        self._bundle = bundle
        cohort = bundle["cohort"]
        patients = cohort.get("patients")
        if not isinstance(patients, dict):
            raise FileNotFoundError(f"Artifact bundle has no patient data: {bundle_path}")
        test_ids = bundle.get("test_patient_ids", [])
        self._test_ids = tuple(sorted(str(patient_id) for patient_id in test_ids if str(patient_id) in patients))
        if not self._test_ids:
            raise FileNotFoundError(f"Artifact bundle has no held-out test patients: {bundle_path}")
        self._patients: dict[str, Mapping[str, Any]] = {
            patient_id: patients[patient_id] for patient_id in self._test_ids
        }
        self._classification_models = bundle.get("classification_models", {})
        self._regression_models = bundle.get("regression_models", {})
        self._conformal_widths = bundle.get("conformal_widths", {})
        self._residual_personalization = bundle.get("residual_personalization", {})
        self._metrics = json_safe(bundle.get("metrics", {}))
        self._provenance = bundle.get("provenance", {})
        self._step_minutes = int(bundle.get("config", {}).get("step_minutes", 5))
        if self._step_minutes <= 0:
            raise FileNotFoundError(f"Invalid observation step in artifact bundle: {bundle_path}")

    def _record(self, patient_id: str) -> Mapping[str, Any]:
        if patient_id not in self._patients:
            raise KeyError(patient_id)
        return self._patients[patient_id]

    @staticmethod
    def _public_patient(record: Mapping[str, Any]) -> dict[str, Any]:
        medications = record.get("medications", []) or []
        return {
            "id": str(record.get("id")),
            "name": str(record.get("name")),
            "age": int(record.get("age", 0)),
            "sex": str(record.get("sex", "")),
            "bmi": float(record.get("bmi", 0.0)),
            "hba1c": float(record.get("hba1c", 0.0)),
            "diabetes_years": int(record.get("diabetes_years", 0)),
            "medications": [str(item) for item in medications],
            "split": str(record.get("split", "test")),
            "min_step": int(record.get("min_step", 0)),
            "max_step": int(record.get("max_step", 0)),
            "default_step": int(record.get("default_step", 0)),
        }

    def _resolve_step(self, record: Mapping[str, Any], step: int | None) -> int:
        resolved = int(record.get("default_step", 0)) if step is None else _integer_step(step)
        minimum = int(record.get("min_step", 0))
        maximum = int(record.get("max_step", -1))
        if resolved < minimum or resolved > maximum:
            raise ValueError(f"step must be between {minimum} and {maximum}")
        if resolved % self._step_minutes != 0:
            raise ValueError(f"step must be on the {self._step_minutes}-minute observation grid")
        return resolved

    @staticmethod
    def _latest(values: Any, step: int) -> float | None:
        array = np.asarray(values, dtype=float)
        if array.size == 0:
            return None
        end = min(int(step), array.size - 1)
        finite = np.flatnonzero(np.isfinite(array[: end + 1]))
        return None if finite.size == 0 else _number(array[int(finite[-1])])

    @staticmethod
    def _slope(values: Any, step: int, width: int = 7, step_minutes: int = 5) -> float | None:
        array = np.asarray(values, dtype=float)
        end = min(int(step), array.size - 1)
        if end < 0:
            return None
        start = max(0, end - width + 1)
        indices = np.arange(start, end + 1, dtype=float)
        segment = array[start : end + 1]
        mask = np.isfinite(segment)
        if int(mask.sum()) < 2:
            return None
        x = indices[mask] * float(step_minutes)
        y = segment[mask]
        centered = x - float(np.mean(x))
        denominator = float(np.sum(centered * centered))
        if denominator <= 0.0:
            return None
        return _number(float(np.sum(centered * (y - float(np.mean(y)))) / denominator))

    def list_patients(self) -> list[dict]:
        """Return only held-out/test patients in deterministic ID order."""

        return [json_safe(deepcopy(self._public_patient(self._patients[patient_id]))) for patient_id in self._test_ids]

    def _past_residual_adjustment(
        self,
        record: Mapping[str, Any],
        current_step: int,
        observations: Mapping[str, np.ndarray],
        horizon: int,
        spec: Mapping[str, Any],
    ) -> float:
        """Reconstruct a bounded residual using only matured past targets."""

        config = self._residual_personalization
        if not isinstance(config, Mapping) or not bool(config.get("enabled", False)):
            return 0.0
        alpha_values = config.get("alpha_by_horizon", {})
        alpha = _number(alpha_values.get(horizon, alpha_values.get(str(horizon))) if isinstance(alpha_values, Mapping) else None, 0.0)
        history_size = int(_number(config.get("history_size"), 0.0) or 0)
        adjustment_clip = _number(config.get("adjustment_clip_mg_dl"), 30.0) or 30.0
        if history_size <= 0 or alpha is None or abs(alpha) <= 1e-12:
            return 0.0

        offset = int(horizon // self._step_minutes)
        anchor_interval = max(1, 30 // self._step_minutes)
        glucose = np.asarray(observations.get("glucose", np.empty(0, dtype=float)), dtype=float)
        residual_history: list[tuple[int, float]] = []
        for prior_anchor in range(0, int(current_step) + 1, anchor_interval):
            target_index = prior_anchor + offset
            if target_index > int(current_step) or target_index >= glucose.size:
                continue
            target = glucose[target_index]
            if not np.isfinite(target):
                continue
            prior_vectors = feature_vectors(record, prior_anchor, observations)
            feature_kind = str(spec.get("feature_kind", "fusion"))
            raw_vector = prior_vectors.get(feature_kind, prior_vectors["fusion"])
            try:
                matrix = np.asarray(raw_vector, dtype=float).reshape(1, -1)
                transformed = spec["preprocessor"].transform(matrix)
                values = spec["estimator"].predict_value(transformed)
                if not len(values) or not math.isfinite(float(values[0])):
                    continue
                base = float(np.clip(values[0], 40.0, 400.0))
            except (KeyError, TypeError, ValueError, RuntimeError, AttributeError):
                continue
            residual_history.append((target_index, float(target) - base))

        matured = [error for ready_at, error in residual_history if ready_at <= int(current_step)]
        if not matured:
            return 0.0
        residual = float(np.mean(matured[-history_size:]))
        return float(np.clip(float(alpha) * residual, -adjustment_clip, adjustment_clip))

    def _model_outputs(
        self,
        record: Mapping[str, Any],
        step: int,
        observations: Mapping[str, np.ndarray],
    ) -> tuple[dict[int, float], float | None, str | None]:
        """Compute fusion risk and regression heads from past-only vectors."""

        vectors = feature_vectors(record, step, observations)
        fusion = np.asarray(vectors["fusion"], dtype=float).reshape(1, -1)
        classification = self._classification_models.get("fusion")
        risk: float | None = None
        if isinstance(classification, Mapping):
            try:
                transformed = classification["preprocessor"].transform(fusion)
                raw_values = classification["estimator"].predict_probability(transformed)
                calibrator = classification.get("calibrator")
                values = (
                    calibrator.predict_probability(raw_values)
                    if calibrator is not None and hasattr(calibrator, "predict_probability")
                    else raw_values
                )
                if len(values) and math.isfinite(float(values[0])):
                    risk = float(np.clip(values[0], 0.0, 1.0))
            except (KeyError, TypeError, ValueError, RuntimeError, AttributeError):
                risk = None

        predictions: dict[int, float] = {}
        for horizon in FORECAST_HORIZONS_MINUTES:
            spec = self._regression_models.get(horizon)
            if spec is None:
                spec = self._regression_models.get(str(horizon))
            if not isinstance(spec, Mapping):
                continue
            try:
                feature_kind = str(spec.get("feature_kind", "fusion"))
                raw_vector = vectors.get(feature_kind, vectors["fusion"])
                forecast_matrix = np.asarray(raw_vector, dtype=float).reshape(1, -1)
                transformed = spec["preprocessor"].transform(forecast_matrix)
                values = spec["estimator"].predict_value(transformed)
                if len(values) and math.isfinite(float(values[0])):
                    base_prediction = float(np.clip(values[0], 40.0, 400.0))
                    adjustment = self._past_residual_adjustment(
                        record,
                        step,
                        observations,
                        horizon,
                        spec,
                    )
                    predictions[horizon] = float(np.clip(base_prediction + adjustment, 40.0, 400.0))
            except (KeyError, TypeError, ValueError, RuntimeError, AttributeError):
                continue
        reason = None
        if len(predictions) != len(FORECAST_HORIZONS_MINUTES):
            reason = "One or more forecast heads are unavailable in the artifact bundle."
        return predictions, risk, reason

    @staticmethod
    def _interval_width(widths: Mapping[Any, Any], horizon: int) -> float | None:
        value = widths.get(horizon, widths.get(str(horizon))) if isinstance(widths, Mapping) else None
        number = _number(value)
        return None if number is None or number < 0 else number

    def snapshot(self, patient_id: str, step: int | None = None, sensor_dropout: bool = False) -> dict:
        record = self._record(patient_id)
        resolved_step = self._resolve_step(record, step)
        observation_index = resolved_step // self._step_minutes
        visible = copy_observations_up_to(record, observation_index, sensor_dropout=bool(sensor_dropout))
        glucose = visible.get("glucose", np.empty(0, dtype=float))
        heart_rate = visible.get("heart_rate", np.empty(0, dtype=float))
        hrv = visible.get("hrv", np.empty(0, dtype=float))
        activity = visible.get("activity", np.empty(0, dtype=float))
        sleep = visible.get("sleep_hours", np.empty(0, dtype=float))
        age_minutes = last_observed_age_minutes(glucose, observation_index)
        last_glucose = self._latest(glucose, observation_index)
        last_hr = self._latest(heart_rate, observation_index)
        last_hrv = self._latest(hrv, observation_index)
        last_sleep = self._latest(sleep, observation_index)
        activity_window = activity[max(0, observation_index - 11) : observation_index + 1]
        missing_window = glucose[max(0, observation_index - 11) : observation_index + 1]
        missing_fraction = float(1.0 - np.isfinite(missing_window).mean()) if missing_window.size else 1.0

        predictions_available = age_minutes is not None and age_minutes <= 15.0
        unavailable_reason: str | None = None
        if age_minutes is None:
            predictions_available = False
            unavailable_reason = "No observed CGM is available at or before this replay step."
        elif age_minutes > 15.0:
            predictions_available = False
            unavailable_reason = "CGM is older than 15 minutes; the engine abstains."

        point_predictions: dict[int, float] = {}
        risk: float | None = None
        if predictions_available:
            point_predictions, risk, model_reason = self._model_outputs(record, observation_index, visible)
            if model_reason is not None:
                predictions_available = False
                unavailable_reason = model_reason
        if last_glucose is not None and last_glucose > EVENT_THRESHOLD:
            # A new-event probability is not defined for an already-above-threshold anchor.
            risk = None
        elif last_glucose is None or age_minutes is None or age_minutes > 15.0:
            risk = None

        forecast: list[dict[str, Any]] = []
        if predictions_available:
            for horizon in FORECAST_HORIZONS_MINUTES:
                point = point_predictions.get(horizon)
                width = self._interval_width(self._conformal_widths, horizon)
                if point is None or width is None:
                    predictions_available = False
                    unavailable_reason = "Calibrated interval is unavailable for one or more horizons."
                    forecast = []
                    break
                forecast.append(
                    {
                        "minutes_ahead": int(horizon),
                        "timestamp": timestamp_for_step(observation_index + horizon // self._step_minutes),
                        "glucose": _number(point),
                        "lower": _number(max(0.0, point - width)),
                        "upper": _number(point + width),
                    }
                )
        if not predictions_available:
            forecast = []
            point_predictions = {}
            risk = None

        if last_glucose is not None and last_glucose > EVENT_THRESHOLD:
            event_state = "above_threshold"
        elif risk is not None and risk >= 0.5:
            event_state = "at_risk"
        else:
            event_state = "unknown"
        if age_minutes is None or age_minutes > 15.0:
            quality = "insufficient"
        elif age_minutes > 5.0 or missing_fraction > 0.25:
            quality = "degraded"
        else:
            quality = "good"

        warnings = ["Synthetic held-out data; not for clinical use."]
        if bool(sensor_dropout):
            warnings.append("The most recent 30 minutes of CGM were removed before feature computation.")
        if age_minutes is None or age_minutes > 15.0:
            warnings.append("CGM freshness is insufficient for a prediction; the engine abstained.")
        elif age_minutes > 5.0:
            warnings.append("Recent CGM readings contain a short gap; prediction quality is degraded.")
        if missing_fraction > 0.25:
            warnings.append("More than 25% of the last 60 minutes of CGM is missing.")
        if last_glucose is not None and last_glucose > EVENT_THRESHOLD:
            warnings.append("The anchor is already above 180 mg/dL, so new-event risk is not defined.")
        if unavailable_reason is not None:
            warnings.append(unavailable_reason)
        if predictions_available:
            warnings.append("Predicted peak is the maximum of sampled 30/60/120-minute heads, not a guaranteed future peak.")
        warnings.append("Context drivers are observations, not causal attribution.")
        if bool(self._residual_personalization.get("enabled", False)):
            warnings.append("A bounded causal-in-time residual adjustment may use matured past forecast errors; it is not a clinical insulin-sensitivity model.")

        steps_60m = float(np.nansum(np.nan_to_num(activity_window, nan=0.0))) if activity_window.size else 0.0
        sleep_value = 0.0 if last_sleep is None else last_sleep
        meal_values = visible.get("meal_carbs", np.empty(0, dtype=float))
        meal_window = meal_values[max(0, observation_index - 23) : observation_index + 1]
        meals_120m = float(np.nansum(np.nan_to_num(meal_window, nan=0.0))) if meal_window.size else 0.0
        current = {
            "glucose": _number(last_glucose),
            "heart_rate": _number(last_hr),
            "hrv": _number(last_hrv),
            "steps_60m": _number(steps_60m, 0.0),
            "sleep_hours": _number(sleep_value, 0.0),
            "glucose_slope": _number(self._slope(glucose, observation_index, step_minutes=self._step_minutes)),
        }

        forecast_values = [point["glucose"] for point in forecast if point.get("glucose") is not None]
        predicted_peak = max(forecast_values) if forecast_values else None
        predictions = {
            "available": bool(predictions_available),
            "reason": None if predictions_available else (unavailable_reason or "Prediction unavailable."),
            "risk_120m": _number(risk),
            "glucose_30m": _number(point_predictions.get(30)),
            "glucose_60m": _number(point_predictions.get(60)),
            "glucose_120m": _number(point_predictions.get(120)),
            "predicted_peak": _number(predicted_peak),
            "interval_coverage_target": 0.90,
            "interval_method": INTERVAL_METHOD
            if all(self._interval_width(self._conformal_widths, horizon) is not None for horizon in FORECAST_HORIZONS_MINUTES)
            else "split-conformal interval unavailable for one or more horizons",
            "personalized": bool(self._residual_personalization.get("enabled", False)),
        }

        drivers = [
            {
                "label": "Recent CGM",
                "value": _number(last_glucose),
                "unit": "mg/dL",
                "interpretation": "Observed current-context value; not causal attribution.",
            },
            {
                "label": "Glucose slope",
                "value": _number(current["glucose_slope"]),
                "unit": "mg/dL/min",
                "interpretation": "Observed recent trend; not a treatment effect.",
            },
            {
                "label": "Activity, last 60m",
                "value": _number(steps_60m, 0.0),
                "unit": "steps",
                "interpretation": "Observed activity context; not causal attribution.",
            },
            {
                "label": "Meal history, last 120m",
                "value": _number(meals_120m, 0.0),
                "unit": "g carbohydrate",
                "interpretation": "Observed meal history; not a dosing recommendation.",
            },
            {
                "label": "Heart rate",
                "value": _number(last_hr),
                "unit": "bpm",
                "interpretation": "Observed context; not causal attribution.",
            },
        ]

        timestamp = timestamp_for_step(observation_index)
        summary_risk = "unavailable" if risk is None else f"{risk:.3f}"
        age_text = "unknown" if age_minutes is None else f"{age_minutes:.0f} minutes"
        evidence_summary = (
            f"Synthetic held-out replay at {timestamp}; observed CGM age {age_text}. "
            f"Forecast available: {'yes' if predictions_available else 'no'}; contract event risk: {summary_risk}. "
            "The summary is deterministic evidence formatting. Context drivers are observations, not causal explanations."
        )
        provenance = {
            "data": str(self._provenance.get("data", "seeded synthetic observations")),
            "model_version": MODEL_VERSION,
            "simulation_version": str(self._provenance.get("simulation_version", "synthetic-day1-v1")),
            "calibration_split": "patient-disjoint calibration-tuning patients for probability calibration; separate calibration-interval patients for split-conformal widths",
            "risk_semantics": RISK_SEMANTICS,
            "explanation": "Day-2 CPU temporal lag model with bounded causal-in-time residual personalization; this is an adaptive residual, not a clinically identified insulin-sensitivity model. Drivers remain observed context only.",
        }
        result = {
            "patient": self._public_patient(record),
            "timestamp": timestamp,
            "step": int(resolved_step),
            "status": {
                "twin": "ready",
                "event": event_state,
                "data_quality": quality,
                "sensor_dropout": bool(sensor_dropout),
                "cgm_age_minutes": _number(age_minutes),
                "missing_fraction_60m": _number(missing_fraction, 1.0),
            },
            "current": current,
            "predictions": predictions,
            "history": history_rows(visible, observation_index),
            "forecast": forecast,
            "drivers": drivers,
            "warnings": warnings,
            "evidence_summary": evidence_summary,
            "provenance": provenance,
        }
        return json_safe(result)

    def simulate(
        self,
        patient_id: str,
        step: int | None = None,
        activity_minutes: int = 15,
        meal_carbs: int = 0,
        sensor_dropout: bool = False,
    ) -> dict:
        """Return an assumption-based scenario band without changing artifacts."""

        activity = _integer_step(activity_minutes, field="activity_minutes")
        meal = _integer_step(meal_carbs, field="meal_carbs")
        if activity < 0 or activity > 30:
            raise ValueError("activity_minutes must be between 0 and 30")
        if meal < 0 or meal > 100:
            raise ValueError("meal_carbs must be between 0 and 100")
        baseline_snapshot = self.snapshot(patient_id, step=step, sensor_dropout=bool(sensor_dropout))
        baseline = deepcopy(baseline_snapshot.get("forecast", []))
        scenario: list[dict[str, Any]] = []
        for point in baseline:
            horizon = float(point.get("minutes_ahead", 0.0))
            # Transparent sandbox perturbation; coefficients are assumptions, not
            # learned causal effects or intervention uncertainty bounds.
            activity_delta = -0.55 * float(activity) * (1.0 - math.exp(-horizon / 90.0))
            meal_delta = 0.70 * float(meal) * math.exp(-horizon / 180.0)
            delta = activity_delta + meal_delta
            glucose = _number(float(point["glucose"]) + delta)
            inherited_width = max(0.0, float(point["upper"]) - float(point["lower"])) / 2.0
            scenario_width = max(5.0, inherited_width * 1.15)
            scenario.append(
                {
                    "minutes_ahead": int(point["minutes_ahead"]),
                    "timestamp": str(point["timestamp"]),
                    "glucose": glucose,
                    "lower": _number(max(0.0, float(glucose or 0.0) - scenario_width)),
                    "upper": _number(float(glucose or 0.0) + scenario_width),
                }
            )
        assumptions = [
            "This is an assumption-based sandbox perturbation of the displayed forecast, not a causal treatment estimate.",
            "Activity and meal effects are illustrative fixed heuristics; the scenario bands are unvalidated and not clinical intervention effects.",
            "No medication change or dosing instruction is represented.",
            "Scenario bands inherit illustrative model bands and are not calibrated intervention uncertainty.",
        ]
        disclaimer = (
            "For synthetic research exploration only. This what-if is not medical advice, does not predict a treatment effect, "
            "and must not be used for dosing, diagnosis, or care decisions."
        )
        return json_safe(
            {
                "baseline": baseline,
                "scenario": scenario,
                "activity_minutes": activity,
                "meal_carbs": meal,
                "assumptions": assumptions,
                "disclaimer": disclaimer,
            }
        )

    def metrics(self) -> dict:
        return deepcopy(json_safe(self._metrics))


__all__ = ["TwinEngine"]
