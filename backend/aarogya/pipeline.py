"""Train and persist the CPU-first Day-2 AarogyaTwin-X baselines.

Run from a checkout with ``backend`` on ``PYTHONPATH`` (or with the backend as
the working directory):

    python -m aarogya.pipeline --output artifacts --patients 60 --days 5 --seed 2026

The command is intentionally self-contained and network-free.  It writes a
joblib bundle plus strict-JSON metrics/provenance files.  ``engine.py`` only
loads those files and never invokes this training path.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import math
from pathlib import Path
import platform
from typing import Any, Mapping, Sequence

import joblib
import numpy as np
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    log_loss,
    mean_absolute_error,
    mean_squared_error,
    roc_auc_score,
)

from .modeling import (
    NumericPreprocessor,
    ProbabilityCalibrator,
    ProbabilityEstimator,
    RegressionEstimator,
    json_safe,
    safe_mean,
)
from .simulation import (
    EVENT_DEFINITION,
    EVENT_HORIZON_STEPS,
    FORECAST_HORIZONS_MINUTES,
    FORECAST_HORIZON_STEPS,
    SIMULATION_VERSION,
    STEP_MINUTES,
    copy_observations_up_to,
    event_label,
    feature_names,
    feature_vectors,
    generate_cohort,
)


ARTIFACT_VERSION = "aarogya-day3-bundle-v1"
CONFORMAL_COVERAGE_TARGET = 0.90
SAMPLE_INTERVAL_STEPS = 30 // STEP_MINUTES
MIN_PATIENTS = 3
MIN_DAYS = 1
MAX_PATIENTS = 500
MAX_DAYS = 14
RESIDUAL_ALPHA_GRID = (0.0, 0.25, 0.5, 0.75, 1.0)
RESIDUAL_HISTORY_SIZE = 4
RESIDUAL_ADJUSTMENT_CLIP = 30.0
CALIBRATION_ROLE_SEED = 8711
MIN_CONFORMAL_ROWS = 20
CALIBRATION_METHOD = "patient-disjoint Platt sigmoid on calibration-tuning patients"


@dataclass
class Sample:
    patient_id: str
    split: str
    anchor_step: int
    features: dict[str, np.ndarray]
    patient_mean_glucose: float | None
    event: int | None
    targets: dict[int, float | None]


def _validate_config(patients: int, days: int, seed: int) -> tuple[int, int, int]:
    values = (("patients", patients), ("days", days), ("seed", seed))
    for name, value in values:
        if isinstance(value, bool) or not isinstance(value, (int, np.integer)):
            raise ValueError(f"{name} must be an integer")
    patients = int(patients)
    days = int(days)
    seed = int(seed)
    if patients < MIN_PATIENTS:
        raise ValueError(f"patients must be at least {MIN_PATIENTS} so train/calibration/test are non-empty")
    if patients > MAX_PATIENTS:
        raise ValueError(f"patients must be at most {MAX_PATIENTS} for the CPU-first local bundle")
    if days < MIN_DAYS:
        raise ValueError(f"days must be at least {MIN_DAYS} to provide history and a future horizon")
    if days > MAX_DAYS:
        raise ValueError(f"days must be at most {MAX_DAYS} for the CPU-first local bundle")
    return patients, days, seed


def _calibration_role_ids(cohort: Mapping[str, Any]) -> dict[str, list[str]]:
    """Make deterministic patient-disjoint tuning and interval-calibration roles."""

    calibration_ids = sorted(
        str(patient_id)
        for patient_id, record in cohort["patients"].items()
        if str(record.get("split")) == "calibration"
    )
    if len(calibration_ids) < 2:
        return {"tuning": calibration_ids, "interval": []}
    order = np.random.default_rng(CALIBRATION_ROLE_SEED).permutation(len(calibration_ids))
    tuning_count = max(1, len(calibration_ids) // 2)
    tuning_count = min(tuning_count, len(calibration_ids) - 1)
    tuning = [calibration_ids[int(index)] for index in order[:tuning_count]]
    interval = [calibration_ids[int(index)] for index in order[tuning_count:]]
    return {"tuning": sorted(tuning), "interval": sorted(interval)}


def _build_samples(cohort: Mapping[str, Any]) -> list[Sample]:
    """Create 30-minute, past-only anchors for every patient.

    The maximum future horizon is reserved so regression targets and event labels
    are defined only when their complete future window is in the generated data.
    """

    samples: list[Sample] = []
    max_horizon = max(FORECAST_HORIZON_STEPS)
    for patient_id in sorted(cohort["patients"]):
        record = cohort["patients"][patient_id]
        observations = record["observations"]
        glucose = np.asarray(observations["glucose"], dtype=float)
        last_anchor = glucose.size - max_horizon - 1
        for anchor in range(0, max(0, last_anchor + 1), SAMPLE_INTERVAL_STEPS):
            vectors = feature_vectors(record, anchor, observations)
            past_glucose = glucose[: anchor + 1]
            finite_past_glucose = past_glucose[np.isfinite(past_glucose)]
            patient_mean_glucose = (
                float(np.mean(finite_past_glucose)) if finite_past_glucose.size else None
            )
            label = event_label(glucose, anchor)
            targets: dict[int, float | None] = {}
            for horizon, offset in zip(FORECAST_HORIZONS_MINUTES, FORECAST_HORIZON_STEPS):
                index = anchor + offset
                if index < glucose.size and np.isfinite(glucose[index]):
                    targets[horizon] = float(glucose[index])
                else:
                    targets[horizon] = None
            samples.append(
                Sample(
                    patient_id=patient_id,
                    split=str(record["split"]),
                    anchor_step=anchor,
                    features=vectors,
                    patient_mean_glucose=patient_mean_glucose,
                    event=label,
                    targets=targets,
                )
            )
    return samples


def _rows(
    samples: Sequence[Sample],
    split: str,
    kind: str,
    *,
    target_horizon: int | None = None,
    require_event: bool = False,
    patient_ids: set[str] | None = None,
) -> tuple[np.ndarray, np.ndarray, list[Sample]]:
    selected: list[Sample] = []
    targets: list[float] = []
    for sample in samples:
        if sample.split != split:
            continue
        if patient_ids is not None and sample.patient_id not in patient_ids:
            continue
        if require_event:
            if sample.event is None:
                continue
            selected.append(sample)
            targets.append(float(sample.event))
        elif target_horizon is not None:
            target = sample.targets.get(target_horizon)
            if target is None or not math.isfinite(float(target)):
                continue
            selected.append(sample)
            targets.append(float(target))
        else:
            selected.append(sample)
    names = feature_names()[kind]
    width = len(names)
    if selected:
        matrix = np.vstack([sample.features[kind] for sample in selected]).astype(float)
    else:
        matrix = np.empty((0, width), dtype=float)
    return matrix, np.asarray(targets, dtype=float), selected


def _classification_metrics(target: np.ndarray, probability: np.ndarray, bins: int = 10) -> dict[str, Any]:
    """Return ranking, proper-scoring, and reliability metrics."""

    target = np.asarray(target, dtype=int).reshape(-1)
    probability = np.asarray(probability, dtype=float).reshape(-1)
    finite = np.isfinite(probability) & np.isfinite(target)
    target = target[finite]
    probability = np.clip(probability[finite], 0.0, 1.0)
    result: dict[str, Any] = {
        "auroc": None,
        "auprc": None,
        "brier": None,
        "log_loss": None,
        "expected_calibration_error": None,
        "reliability_bins": [],
        "prevalence": None,
        "n_test": int(target.size),
    }
    if target.size == 0:
        return result
    result["prevalence"] = float(np.mean(target))
    # Both ranking metrics are undefined for a one-class evaluation set. Do not
    # rely on sklearn's warning-and-number fallback for all-negative AUPRC.
    if np.unique(target).size >= 2:
        try:
            result["auroc"] = float(roc_auc_score(target, probability))
        except (ValueError, ArithmeticError):
            result["auroc"] = None
        try:
            result["auprc"] = float(average_precision_score(target, probability))
        except (ValueError, ArithmeticError):
            result["auprc"] = None
    try:
        result["brier"] = float(brier_score_loss(target, probability))
        result["log_loss"] = float(log_loss(target, probability, labels=[0, 1]))
    except (ValueError, ArithmeticError):
        result["brier"] = None
        result["log_loss"] = None

    bin_rows: list[dict[str, Any]] = []
    weighted_gap = 0.0
    edges = np.linspace(0.0, 1.0, int(max(1, bins)) + 1)
    for index in range(edges.size - 1):
        lower = float(edges[index])
        upper = float(edges[index + 1])
        mask = (probability >= lower) & (
            (probability < upper) if index < edges.size - 2 else (probability <= upper)
        )
        count = int(np.sum(mask))
        row: dict[str, Any] = {
            "lower": lower,
            "upper": upper,
            "count": count,
            "mean_predicted": None,
            "observed_rate": None,
            "absolute_gap": None,
        }
        if count:
            mean_predicted = float(np.mean(probability[mask]))
            observed_rate = float(np.mean(target[mask]))
            gap = abs(mean_predicted - observed_rate)
            row.update(
                mean_predicted=mean_predicted,
                observed_rate=observed_rate,
                absolute_gap=float(gap),
            )
            weighted_gap += (count / target.size) * gap
        bin_rows.append(row)
    result["reliability_bins"] = bin_rows
    result["expected_calibration_error"] = float(weighted_gap)
    return result


def _forecast_metrics(
    target: np.ndarray,
    prediction: np.ndarray,
    width: float | None,
) -> dict[str, Any]:
    target = np.asarray(target, dtype=float).reshape(-1)
    prediction = np.asarray(prediction, dtype=float).reshape(-1)
    finite = np.isfinite(target) & np.isfinite(prediction)
    target = target[finite]
    prediction = prediction[finite]
    result: dict[str, Any] = {
        "mae": None,
        "rmse": None,
        "empirical_coverage": None,
        "mean_interval_width": None,
        "n_test": int(target.size),
        "interval_coverage_target": CONFORMAL_COVERAGE_TARGET,
    }
    if target.size == 0:
        return result
    result["mae"] = float(mean_absolute_error(target, prediction))
    result["rmse"] = float(math.sqrt(mean_squared_error(target, prediction)))
    if width is not None and math.isfinite(width):
        result["empirical_coverage"] = float(np.mean((target >= prediction - width) & (target <= prediction + width)))
        result["mean_interval_width"] = float(2.0 * width)
    return result


def _split_conformal_width(
    residuals: np.ndarray,
    coverage: float,
    minimum_rows: int = MIN_CONFORMAL_ROWS,
) -> float | None:
    """Return the finite-sample split-conformal absolute-residual rank.

    A width is withheld when the calibration sample is too small to support a
    useful interval. The rank is explicit so behavior is stable across NumPy
    quantile implementation details.
    """

    values = np.asarray(residuals, dtype=float).reshape(-1)
    values = np.sort(values[np.isfinite(values)])
    if values.size < int(minimum_rows):
        return None
    rank = int(math.ceil((values.size + 1) * float(coverage)))
    rank = max(1, min(rank, values.size))
    return float(values[rank - 1])


def _predict_classifier_raw(
    spec: Mapping[str, Any],
    matrix: np.ndarray,
) -> np.ndarray:
    if matrix.shape[0] == 0:
        return np.empty(0, dtype=float)
    transformed = spec["preprocessor"].transform(matrix)
    return np.asarray(spec["estimator"].predict_probability(transformed), dtype=float)


def _predict_classifier(
    spec: Mapping[str, Any],
    matrix: np.ndarray,
) -> np.ndarray:
    raw = _predict_classifier_raw(spec, matrix)
    calibrator = spec.get("calibrator")
    if isinstance(calibrator, ProbabilityCalibrator):
        return calibrator.predict_probability(raw)
    return raw


def _predict_regressor(spec: Mapping[str, Any], matrix: np.ndarray) -> np.ndarray:
    if matrix.shape[0] == 0:
        return np.empty(0, dtype=float)
    transformed = spec["preprocessor"].transform(matrix)
    return np.clip(np.asarray(spec["estimator"].predict_value(transformed), dtype=float), 40.0, 400.0)


def _online_personalized_predictions(
    spec: Mapping[str, Any],
    samples: Sequence[Sample],
    split: str,
    horizon: int,
    alpha: float,
    history_size: int,
    patient_ids: set[str] | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, list[Sample]]:
    """Predict a split in time order using only matured prior residuals.

    A residual from an earlier anchor becomes eligible only when that earlier
    target timestamp is at or before the current anchor. The global model is
    never refit here, and residual history is maintained separately per patient.
    """

    feature_kind = str(spec.get("feature_kind", "temporal"))
    offset = int(horizon // STEP_MINUTES)
    selected = [
        sample
        for sample in samples
        if sample.split == split
        and (patient_ids is None or sample.patient_id in patient_ids)
        and sample.targets.get(horizon) is not None
        and math.isfinite(float(sample.targets[horizon]))
    ]
    selected.sort(key=lambda sample: (sample.patient_id, sample.anchor_step))
    residual_history: dict[str, list[tuple[int, float]]] = {}
    targets: list[float] = []
    base_predictions: list[float] = []
    adjusted_predictions: list[float] = []

    for sample in selected:
        matrix = np.asarray(sample.features[feature_kind], dtype=float).reshape(1, -1)
        base_values = _predict_regressor(spec, matrix)
        if base_values.size == 0 or not np.isfinite(base_values[0]):
            continue
        base = float(base_values[0])
        history = residual_history.setdefault(sample.patient_id, [])
        matured = [error for ready_at, error in history if ready_at <= sample.anchor_step]
        if history_size > 0:
            matured = matured[-history_size:]
        residual = float(np.mean(matured)) if matured else 0.0
        adjustment = float(np.clip(float(alpha) * residual, -RESIDUAL_ADJUSTMENT_CLIP, RESIDUAL_ADJUSTMENT_CLIP))
        target = float(sample.targets[horizon])
        adjusted = float(np.clip(base + adjustment, 40.0, 400.0))
        targets.append(target)
        base_predictions.append(base)
        adjusted_predictions.append(adjusted)
        # Store a base-model residual only after this forecast's target would be
        # observable. It cannot affect this row or any earlier anchor.
        history.append((sample.anchor_step + offset, target - base))

    return (
        np.asarray(targets, dtype=float),
        np.asarray(base_predictions, dtype=float),
        np.asarray(adjusted_predictions, dtype=float),
        selected,
    )


def _fit_residual_personalization(
    specs: Mapping[int, Mapping[str, Any]],
    samples: Sequence[Sample],
    tuning_ids: set[str],
    interval_ids: set[str],
) -> tuple[dict[str, Any], dict[str, dict[str, Any]], dict[int, float | None]]:
    """Choose shrinkage on calibration patients and evaluate online on test patients."""

    alpha_by_horizon: dict[str, float] = {}
    measured: dict[str, dict[str, Any]] = {}
    widths: dict[int, float | None] = {}
    for horizon in FORECAST_HORIZONS_MINUTES:
        spec = specs[horizon]
        best_alpha = 0.0
        best_mae = math.inf
        for alpha in RESIDUAL_ALPHA_GRID:
            calibration_target, _, calibration_prediction, _ = _online_personalized_predictions(
                spec,
                samples,
                "calibration",
                horizon,
                alpha,
                RESIDUAL_HISTORY_SIZE,
                patient_ids=tuning_ids,
            )
            if calibration_target.size == 0:
                continue
            mae = float(mean_absolute_error(calibration_target, calibration_prediction))
            # Prefer the smaller adjustment on an exact tie.
            if mae < best_mae - 1e-12 or (math.isclose(mae, best_mae) and alpha < best_alpha):
                best_alpha = float(alpha)
                best_mae = mae

        alpha_by_horizon[str(horizon)] = best_alpha
        calibration_target, _, calibration_prediction, _ = _online_personalized_predictions(
            spec,
            samples,
            "calibration",
            horizon,
            best_alpha,
            RESIDUAL_HISTORY_SIZE,
            patient_ids=tuning_ids,
        )
        interval_target, _, interval_prediction, _ = _online_personalized_predictions(
            spec,
            samples,
            "calibration",
            horizon,
            best_alpha,
            RESIDUAL_HISTORY_SIZE,
            patient_ids=interval_ids,
        )
        test_target, _, test_prediction, _ = _online_personalized_predictions(
            spec,
            samples,
            "test",
            horizon,
            best_alpha,
            RESIDUAL_HISTORY_SIZE,
        )
        width = _split_conformal_width(
            np.abs(interval_target - interval_prediction),
            CONFORMAL_COVERAGE_TARGET,
        )
        widths[horizon] = width
        measured[str(horizon)] = _forecast_metrics(test_target, test_prediction, width)
        measured[str(horizon)]["horizon_minutes"] = int(horizon)
        measured[str(horizon)]["model_type"] = "temporal_lags_with_causal_residual"
        measured[str(horizon)]["alpha"] = best_alpha
        measured[str(horizon)]["history_size"] = RESIDUAL_HISTORY_SIZE
        measured[str(horizon)]["n_train"] = int(spec.get("n_train", 0))
        measured[str(horizon)]["n_tuning"] = int(calibration_target.size)
        measured[str(horizon)]["n_calibration"] = int(interval_target.size)

    config = {
        "enabled": True,
        "method": "bounded online per-patient residual correction",
        "alpha_by_horizon": alpha_by_horizon,
        "candidate_alphas": list(RESIDUAL_ALPHA_GRID),
        "history_size": RESIDUAL_HISTORY_SIZE,
        "adjustment_clip_mg_dl": RESIDUAL_ADJUSTMENT_CLIP,
        "fit_split": "training patients only for global model",
        "tuning_split": "calibration-tuning patients only for residual shrinkage",
        "interval_split": "calibration-interval patients only for conformal widths",
        "test_policy": "residuals are eligible only after their target timestamp is observed",
        "clinical_interpretation": "adaptive residual, not a clinically identified insulin-sensitivity model",
    }
    return config, measured, widths


def _fit_classification_models(
    samples: Sequence[Sample],
    seed: int,
    calibration_tuning_ids: set[str],
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    """Fit classifiers on train patients and calibrate on separate patients."""

    model_specs: dict[str, dict[str, Any]] = {}
    measured: dict[str, dict[str, Any]] = {}
    measured_before_calibration: dict[str, dict[str, Any]] = {}
    for offset, kind in enumerate(("static", "sensor", "fusion")):
        train_x, train_y, _ = _rows(samples, "train", kind, require_event=True)
        tuning_x, tuning_y, _ = _rows(
            samples,
            "calibration",
            kind,
            require_event=True,
            patient_ids=calibration_tuning_ids,
        )
        test_x, test_y, _ = _rows(samples, "test", kind, require_event=True)
        fit_x = train_x if train_x.shape[0] else np.zeros((1, len(feature_names()[kind])))
        preprocessor = NumericPreprocessor().fit(fit_x)
        estimator = ProbabilityEstimator(random_state=seed + offset).fit(
            preprocessor.transform(train_x), train_y
        )
        raw_spec = {
            "feature_kind": kind,
            "feature_names": feature_names()[kind],
            "preprocessor": preprocessor,
            "estimator": estimator,
        }
        tuning_raw = _predict_classifier_raw(raw_spec, tuning_x)
        calibrator = ProbabilityCalibrator().fit(tuning_raw, tuning_y)
        spec = {
            **raw_spec,
            "calibrator": calibrator,
            "n_train": int(train_y.size),
            "n_calibration": int(tuning_y.size),
            "calibration_method": CALIBRATION_METHOD,
            "calibration_status": calibrator.status_,
        }
        model_specs[kind] = spec
        raw_test = _predict_classifier_raw(spec, test_x)
        probability = calibrator.predict_probability(raw_test)
        measured_before_calibration[kind] = _classification_metrics(test_y, raw_test)
        measured[kind] = _classification_metrics(test_y, probability)
        for result in (measured_before_calibration[kind], measured[kind]):
            result["model_type"] = (
                "logistic_regression" if estimator.model is not None else "constant_fallback"
            )
            result["n_train"] = int(train_y.size)
            result["n_calibration"] = int(tuning_y.size)
            result["calibration_method"] = calibrator.status_

    # Constant prevalence is the intentionally simple event-probability baseline.
    _, train_y, _ = _rows(samples, "train", "fusion", require_event=True)
    _, test_y, _ = _rows(samples, "test", "fusion", require_event=True)
    prevalence = safe_mean(train_y.tolist())
    persistence_probability = 0.0 if prevalence is None else float(prevalence)
    measured["persistence"] = _classification_metrics(
        test_y,
        np.full(test_y.size, persistence_probability, dtype=float),
    )
    measured["persistence"]["method"] = "constant train-patient event prevalence persistence comparator"
    measured["persistence"]["n_train"] = int(train_y.size)
    measured["persistence"]["n_calibration"] = 0
    measured_before_calibration["persistence"] = dict(measured["persistence"])
    model_specs["persistence"] = {
        "feature_kind": None,
        "train_prevalence": persistence_probability,
        "n_train": int(train_y.size),
    }
    return model_specs, measured, measured_before_calibration


def _fit_regression_family(
    samples: Sequence[Sample],
    seed: int,
    kind: str,
    model_label: str,
    calibration_ids: set[str] | None = None,
) -> tuple[dict[int, dict[str, Any]], dict[str, dict[str, Any]], dict[int, float | None]]:
    """Fit one leakage-safe forecast family and calibrate it on calibration patients."""

    specs: dict[int, dict[str, Any]] = {}
    measured: dict[str, dict[str, Any]] = {}
    widths: dict[int, float | None] = {}
    for offset, horizon in enumerate(FORECAST_HORIZONS_MINUTES):
        train_x, train_y, _ = _rows(samples, "train", kind, target_horizon=horizon)
        calibration_x, calibration_y, _ = _rows(
            samples,
            "calibration",
            kind,
            target_horizon=horizon,
            patient_ids=calibration_ids,
        )
        test_x, test_y, _ = _rows(samples, "test", kind, target_horizon=horizon)
        if train_x.shape[0]:
            fit_x = train_x
        else:
            # Keep the preprocessor structurally valid even for a deliberately
            # tiny/degenerate invocation; the estimator remains unavailable.
            fit_x = np.zeros((1, len(feature_names()[kind])), dtype=float)
        preprocessor = NumericPreprocessor().fit(fit_x)
        estimator = RegressionEstimator(random_state=seed + 100 + offset).fit(
            preprocessor.transform(train_x), train_y
        )
        spec = {
            "feature_kind": kind,
            "horizon_minutes": horizon,
            "feature_names": feature_names()[kind],
            "preprocessor": preprocessor,
            "estimator": estimator,
            "n_train": int(train_y.size),
            "n_calibration": int(calibration_y.size),
        }
        specs[horizon] = spec

        calibration_prediction = _predict_regressor(spec, calibration_x)
        residuals = np.abs(calibration_y - calibration_prediction)
        width = _split_conformal_width(residuals, CONFORMAL_COVERAGE_TARGET)
        widths[horizon] = width
        test_prediction = _predict_regressor(spec, test_x)
        measured[str(horizon)] = _forecast_metrics(test_y, test_prediction, width)
        measured[str(horizon)]["horizon_minutes"] = int(horizon)
        measured[str(horizon)]["model_type"] = (
            model_label if estimator.model is not None else "constant_fallback"
        )
        measured[str(horizon)]["n_train"] = int(train_y.size)
        measured[str(horizon)]["n_calibration"] = int(calibration_y.size)
    return specs, measured, widths


def _fit_regression_models(
    samples: Sequence[Sample],
    seed: int,
    calibration_ids: set[str] | None = None,
) -> tuple[dict[int, dict[str, Any]], dict[str, dict[str, Any]], dict[int, float | None]]:
    return _fit_regression_family(
        samples,
        seed,
        kind="temporal",
        model_label="HistGradientBoostingRegressor_temporal_lags",
        calibration_ids=calibration_ids,
    )


def _fit_baseline_regression_models(
    samples: Sequence[Sample],
    seed: int,
    calibration_ids: set[str] | None = None,
) -> tuple[dict[str, dict[str, Any]], dict[int, float | None]]:
    _, measured, widths = _fit_regression_family(
        samples,
        seed + 500,
        kind="fusion",
        model_label="HistGradientBoostingRegressor_day1_summary",
        calibration_ids=calibration_ids,
    )
    return measured, widths


def _persistence_forecast_metrics(
    samples: Sequence[Sample],
    horizon: int,
    train_fallback: float | None,
) -> dict[str, Any]:
    """Measure a last-observed-CGM persistence forecast on test patients."""

    _, target, selected = _rows(samples, "test", "fusion", target_horizon=horizon)
    if not selected:
        return _forecast_metrics(np.empty(0), np.empty(0), None)
    fallback = 0.0 if train_fallback is None else float(train_fallback)
    prediction = np.asarray(
        [
            float(sample.features["sensor"][0])
            if sample.features["sensor"].size and np.isfinite(sample.features["sensor"][0])
            else fallback
            for sample in selected
        ],
        dtype=float,
    )
    result = _forecast_metrics(target, prediction, None)
    result["horizon_minutes"] = int(horizon)
    result["method"] = "last observed CGM, no learned future information"
    return result


def _patient_mean_forecast_metrics(
    samples: Sequence[Sample],
    horizon: int,
    train_fallback: float | None,
) -> dict[str, Any]:
    """Measure a patient running-mean forecast using anchor-visible glucose only."""

    _, target, selected = _rows(samples, "test", "fusion", target_horizon=horizon)
    if not selected:
        return _forecast_metrics(np.empty(0), np.empty(0), None)
    fallback = 0.0 if train_fallback is None else float(train_fallback)
    prediction = np.asarray(
        [
            float(sample.patient_mean_glucose)
            if sample.patient_mean_glucose is not None and math.isfinite(sample.patient_mean_glucose)
            else fallback
            for sample in selected
        ],
        dtype=float,
    )
    result = _forecast_metrics(target, prediction, None)
    result["horizon_minutes"] = int(horizon)
    result["method"] = "patient running mean of observed glucose through the anchor"
    return result


def _missingness_visible(
    record: Mapping[str, Any],
    anchor_step: int,
    scenario: str,
) -> dict[str, np.ndarray]:
    """Create deterministic synthetic missingness without changing the cohort."""

    visible = copy_observations_up_to(record, anchor_step, sensor_dropout=False)
    if scenario == "recent_cgm_dropout_30m":
        visible["glucose"][max(0, int(anchor_step) - 5) : int(anchor_step) + 1] = np.nan
    elif scenario == "random_recent_stream_missingness_25pct":
        start = max(0, int(anchor_step) - 11)
        recent_indices = [index for index in range(start, int(anchor_step)) if (index - start) % 4 == 1]
        for name, values in visible.items():
            values[recent_indices] = np.nan
    elif scenario != "natural_missingness":
        raise ValueError(f"unknown missingness scenario: {scenario}")
    return visible


def _cgm_age_and_missing_fraction(values: np.ndarray, anchor_step: int) -> tuple[float | None, float]:
    end = min(int(anchor_step), values.size - 1)
    if end < 0:
        return None, 1.0
    finite = np.flatnonzero(np.isfinite(values[: end + 1]))
    age = None if finite.size == 0 else float((end - int(finite[-1])) * STEP_MINUTES)
    window = values[max(0, end - 11) : end + 1]
    missing_fraction = float(1.0 - np.isfinite(window).mean()) if window.size else 1.0
    return age, missing_fraction


def _evaluate_missingness(
    cohort: Mapping[str, Any],
    samples: Sequence[Sample],
    regression_specs: Mapping[int, Mapping[str, Any]],
    widths: Mapping[int, float | None],
) -> dict[str, Any]:
    """Measure prediction degradation and policy abstention under synthetic gaps."""

    scenarios = (
        "natural_missingness",
        "random_recent_stream_missingness_25pct",
        "recent_cgm_dropout_30m",
    )
    result: dict[str, Any] = {
        "evaluation_model": "temporal lag model without residual personalization",
        "prediction_policy": "abstain when latest CGM is absent or older than 15 minutes",
        "scenarios": {},
        "event_label_exclusions": {
            split: {
                "unknown_event_label_rows": int(sum(1 for sample in samples if sample.split == split and sample.event is None)),
                "policy": "unknown or contract-ineligible rows are excluded, never negative",
                "note": "None includes anchors already above threshold and rows with missing future readings.",
            }
            for split in ("train", "calibration", "test")
        },
    }
    test_samples = [sample for sample in samples if sample.split == "test"]
    for scenario in scenarios:
        horizon_results: dict[str, Any] = {}
        for horizon in FORECAST_HORIZONS_MINUTES:
            spec = regression_specs.get(horizon, regression_specs.get(str(horizon)))
            targets: list[float] = []
            predictions: list[float] = []
            ages: list[float] = []
            missing_fractions: list[float] = []
            n_targets = 0
            for sample in test_samples:
                target = sample.targets.get(horizon)
                if target is None or not math.isfinite(float(target)):
                    continue
                n_targets += 1
                record = cohort["patients"][sample.patient_id]
                visible = _missingness_visible(record, sample.anchor_step, scenario)
                age, missing_fraction = _cgm_age_and_missing_fraction(
                    np.asarray(visible["glucose"], dtype=float),
                    sample.anchor_step,
                )
                if age is not None:
                    ages.append(age)
                missing_fractions.append(missing_fraction)
                if age is None or age > 15.0 or not isinstance(spec, Mapping):
                    continue
                vectors = feature_vectors(record, sample.anchor_step, visible)
                matrix = np.asarray(vectors[str(spec.get("feature_kind", "temporal"))], dtype=float).reshape(1, -1)
                prediction = _predict_regressor(spec, matrix)
                if prediction.size and np.isfinite(prediction[0]):
                    targets.append(float(target))
                    predictions.append(float(prediction[0]))
            target_array = np.asarray(targets, dtype=float)
            prediction_array = np.asarray(predictions, dtype=float)
            raw_width = widths.get(horizon, widths.get(str(horizon))) if isinstance(widths, Mapping) else None
            width = float(raw_width) if raw_width is not None and math.isfinite(float(raw_width)) else None
            measured = _forecast_metrics(target_array, prediction_array, width)
            measured.update(
                {
                    "scenario": scenario,
                    "n_targets": n_targets,
                    "n_eligible": len(targets),
                    "n_predicted": len(predictions),
                    "n_abstained": max(0, n_targets - len(predictions)),
                    "abstention_rate": None if n_targets == 0 else float(1.0 - len(predictions) / n_targets),
                    "mean_cgm_age_minutes": None if not ages else float(np.mean(ages)),
                    "mean_missing_fraction_60m": None if not missing_fractions else float(np.mean(missing_fractions)),
                }
            )
            horizon_results[str(horizon)] = measured
        result["scenarios"][scenario] = horizon_results
    return json_safe(result)


def _distribution_shift_visible(
    record: Mapping[str, Any],
    anchor_step: int,
    scenario: str,
) -> tuple[dict[str, np.ndarray], Mapping[str, Any], float]:
    """Apply deterministic synthetic test-only covariate/regime shifts."""

    visible = copy_observations_up_to(record, anchor_step, sensor_dropout=False)
    shifted_record: dict[str, Any] = dict(record)
    target_offset = 0.0
    if scenario == "nominal_test":
        description = "Unshifted held-out synthetic test patients."
    elif scenario == "glucose_level_plus_25":
        visible["glucose"] = visible["glucose"] + 25.0
        target_offset = 25.0
        description = "Glucose level shifted +25 mg/dL in past inputs and future targets; no retraining."
    elif scenario == "meal_carbs_2x_inputs":
        visible["meal_carbs"] = visible["meal_carbs"] * 2.0
        description = "Observed meal carbohydrate inputs doubled; original future glucose target retained."
    elif scenario == "hba1c_plus_1_static":
        shifted_record["hba1c"] = float(shifted_record.get("hba1c", 0.0)) + 1.0
        description = "Static HbA1c input shifted +1.0 percentage point; original future glucose target retained."
    else:
        raise ValueError(f"unknown distribution-shift scenario: {scenario}")
    return visible, {**shifted_record, "shift_description": description}, target_offset


def _evaluate_distribution_shift(
    cohort: Mapping[str, Any],
    samples: Sequence[Sample],
    regression_specs: Mapping[int, Mapping[str, Any]],
    widths: Mapping[int, float | None],
) -> dict[str, Any]:
    """Evaluate the frozen model under explicitly synthetic test-only shifts."""

    scenarios = (
        "nominal_test",
        "glucose_level_plus_25",
        "meal_carbs_2x_inputs",
        "hba1c_plus_1_static",
    )
    result: dict[str, Any] = {
        "evaluation_model": "frozen temporal lag model without retraining or residual personalization",
        "test_policy": "all shifts are applied only to held-out synthetic test inputs; no shift selects model settings",
        "scenarios": {},
    }
    test_samples = [sample for sample in samples if sample.split == "test"]
    descriptions = {
        "nominal_test": "Unshifted held-out synthetic test patients.",
        "glucose_level_plus_25": "Glucose level shifted +25 mg/dL in past inputs and future targets; no retraining.",
        "meal_carbs_2x_inputs": "Observed meal carbohydrate inputs doubled; original future glucose target retained.",
        "hba1c_plus_1_static": "Static HbA1c input shifted +1.0 percentage point; original future glucose target retained.",
    }
    for scenario in scenarios:
        horizon_results: dict[str, Any] = {}
        for horizon in FORECAST_HORIZONS_MINUTES:
            spec = regression_specs.get(horizon, regression_specs.get(str(horizon)))
            targets: list[float] = []
            predictions: list[float] = []
            for sample in test_samples:
                original_target = sample.targets.get(horizon)
                if original_target is None or not math.isfinite(float(original_target)):
                    continue
                record = cohort["patients"][sample.patient_id]
                visible, shifted_record, target_offset = _distribution_shift_visible(
                    record,
                    sample.anchor_step,
                    scenario,
                )
                if not isinstance(spec, Mapping):
                    continue
                vectors = feature_vectors(shifted_record, sample.anchor_step, visible)
                feature_kind = str(spec.get("feature_kind", "temporal"))
                matrix = np.asarray(vectors[feature_kind], dtype=float).reshape(1, -1)
                prediction = _predict_regressor(spec, matrix)
                if prediction.size and np.isfinite(prediction[0]):
                    targets.append(float(original_target) + target_offset)
                    predictions.append(float(prediction[0]))
            width_value = widths.get(horizon, widths.get(str(horizon))) if isinstance(widths, Mapping) else None
            width = float(width_value) if width_value is not None and math.isfinite(float(width_value)) else None
            measured = _forecast_metrics(
                np.asarray(targets, dtype=float),
                np.asarray(predictions, dtype=float),
                width,
            )
            measured.update(
                {
                    "scenario": scenario,
                    "shift_description": descriptions[scenario],
                    "n_test": len(predictions),
                    "target_transform": "+25 mg/dL" if target_offset else "unchanged",
                }
            )
            horizon_results[str(horizon)] = measured
        result["scenarios"][scenario] = horizon_results
    return json_safe(result)


def _event_onsets(glucose: Sequence[float] | np.ndarray) -> list[int]:
    values = np.asarray(glucose, dtype=float)
    finite_above = np.isfinite(values) & (values > EVENT_DEFINITION["threshold_mg_dl"])
    confirmation = int(EVENT_DEFINITION["consecutive_readings"])
    onsets: list[int] = []
    for index in range(0, max(0, values.size - confirmation + 1)):
        if not bool(np.all(finite_above[index : index + confirmation])):
            continue
        if index == 0 or not bool(finite_above[index - 1]):
            onsets.append(index)
    return onsets


def _event_level_alert_metrics(
    cohort: Mapping[str, Any],
    samples: Sequence[Sample],
    classification_specs: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Measure window and unique-episode alert behavior on held-out patients."""

    spec = classification_specs.get("fusion")
    if not isinstance(spec, Mapping):
        return {"status": "unavailable", "reason": "Fusion classifier artifact is unavailable."}
    rows: list[tuple[Sample, float]] = []
    for sample in samples:
        if sample.split != "test" or sample.event is None:
            continue
        matrix = np.asarray(sample.features["fusion"], dtype=float).reshape(1, -1)
        probability = _predict_classifier(spec, matrix)
        if probability.size and np.isfinite(probability[0]):
            rows.append((sample, float(np.clip(probability[0], 0.0, 1.0))))

    thresholds = (0.10, 0.20, 0.50)
    test_patient_ids = sorted(
        str(patient_id)
        for patient_id, record in cohort["patients"].items()
        if str(record.get("split")) == "test"
    )
    event_onsets = {
        patient_id: _event_onsets(cohort["patients"][patient_id]["observations"]["glucose"])
        for patient_id in test_patient_ids
    }
    total_events = sum(len(onsets) for onsets in event_onsets.values())
    denominator_patient_days = max(1, len(test_patient_ids) * int(cohort["days"]))
    results: dict[str, Any] = {}
    for threshold in thresholds:
        labels = np.asarray([int(sample.event) for sample, _ in rows], dtype=int)
        alerts = np.asarray([int(probability >= threshold) for _, probability in rows], dtype=int)
        true_positive = int(np.sum((labels == 1) & (alerts == 1)))
        true_negative = int(np.sum((labels == 0) & (alerts == 0)))
        false_positive = int(np.sum((labels == 0) & (alerts == 1)))
        false_negative = int(np.sum((labels == 1) & (alerts == 0)))
        precision = true_positive / (true_positive + false_positive) if true_positive + false_positive else None
        sensitivity = true_positive / (true_positive + false_negative) if true_positive + false_negative else None
        specificity = true_negative / (true_negative + false_positive) if true_negative + false_positive else None
        f1 = (
            2.0 * precision * sensitivity / (precision + sensitivity)
            if precision is not None and sensitivity is not None and precision + sensitivity
            else None
        )
        detected_events = 0
        lead_times: list[float] = []
        for patient_id, onsets in event_onsets.items():
            patient_rows = [
                sample
                for sample, probability in rows
                if sample.patient_id == patient_id and probability >= threshold
            ]
            for onset in onsets:
                candidate_anchors = [
                    sample.anchor_step
                    for sample in patient_rows
                    if sample.anchor_step < onset
                    and onset - sample.anchor_step <= EVENT_HORIZON_STEPS
                ]
                if candidate_anchors:
                    detected_events += 1
                    latest_anchor = max(candidate_anchors)
                    lead_times.append(float((onset - latest_anchor) * STEP_MINUTES))
        results[f"{threshold:.2f}"] = {
            "threshold": threshold,
            "window_metrics": {
                "n_windows": int(labels.size),
                "prevalence": None if labels.size == 0 else float(np.mean(labels)),
                "true_positive": true_positive,
                "true_negative": true_negative,
                "false_positive": false_positive,
                "false_negative": false_negative,
                "precision": precision,
                "sensitivity": sensitivity,
                "specificity": specificity,
                "f1": f1,
                "alert_rate": None if alerts.size == 0 else float(np.mean(alerts)),
                "false_alert_rate": None
                if true_negative + false_positive == 0
                else float(false_positive / (true_negative + false_positive)),
            },
            "episode_metrics": {
                "n_test_patients": len(test_patient_ids),
                "n_event_episodes": total_events,
                "detected_event_episodes": detected_events,
                "episode_sensitivity": None if total_events == 0 else float(detected_events / total_events),
                "median_lead_minutes": None if not lead_times else float(np.median(lead_times)),
                "false_alerts_per_patient_day": float(false_positive / denominator_patient_days),
            },
        }
    return {
        "status": "measured",
        "event_definition": dict(EVENT_DEFINITION),
        "prediction_model": "calibrated fusion classifier",
        "thresholds": results,
        "test_patient_days": denominator_patient_days,
        "labels_with_missing_future": "excluded before alert metrics; never negative",
    }


def _build_metrics(
    cohort: Mapping[str, Any],
    samples: Sequence[Sample],
    classification_metrics: Mapping[str, Mapping[str, Any]],
    classification_before_calibration: Mapping[str, Mapping[str, Any]],
    regression_metrics: Mapping[str, Mapping[str, Any]],
    widths: Mapping[int, float | None],
    baseline_regression_metrics: Mapping[str, Mapping[str, Any]],
    before_personalization_metrics: Mapping[str, Mapping[str, Any]],
    personalization: Mapping[str, Any],
    calibration_roles: Mapping[str, Sequence[str]],
    missingness: Mapping[str, Any],
    distribution_shift: Mapping[str, Any],
    event_alerts: Mapping[str, Any],
) -> dict[str, Any]:
    records = cohort["patients"]
    split_counts: dict[str, int] = {"train": 0, "calibration": 0, "test": 0}
    for record in records.values():
        split = str(record.get("split"))
        split_counts[split] = split_counts.get(split, 0) + 1

    train_current_values = [
        float(sample.features["sensor"][0])
        for sample in samples
        if sample.split == "train"
        and sample.features["sensor"].size
        and np.isfinite(sample.features["sensor"][0])
    ]
    train_fallback = safe_mean(train_current_values)
    persistence_forecast = {
        str(horizon): _persistence_forecast_metrics(samples, horizon, train_fallback)
        for horizon in FORECAST_HORIZONS_MINUTES
    }
    train_patient_means = [
        float(sample.patient_mean_glucose)
        for sample in samples
        if sample.split == "train"
        and sample.patient_mean_glucose is not None
        and math.isfinite(sample.patient_mean_glucose)
    ]
    train_patient_mean_fallback = safe_mean(train_patient_means)
    patient_mean_forecast = {
        str(horizon): _patient_mean_forecast_metrics(samples, horizon, train_patient_mean_fallback)
        for horizon in FORECAST_HORIZONS_MINUTES
    }

    model_results: dict[str, Any] = {
        "static_only": {"model_type": "logistic_regression", **dict(classification_metrics["static"])},
        "sensor_only": {"model_type": "logistic_regression", **dict(classification_metrics["sensor"])},
        "fusion": {"model_type": "logistic_regression", **dict(classification_metrics["fusion"])},
        "persistence": {"model_type": "constant_train_prevalence", **dict(classification_metrics["persistence"])},
    }

    limitations = [
        "All records and labels are seeded synthetic development data, not clinical evidence.",
        "Windows are sampled every 30 minutes but remain correlated within patients; row counts are not independent subjects.",
        "Train, calibration-tuning, calibration-interval, and test partitions are patient-disjoint; no test rows tune models or calibration.",
        "Future label/target readings with missing CGM are excluded rather than treated as negative or normal.",
        "The event endpoint is a project-specific strict-above-180 mg/dL sustained episode definition, not a universal clinical definition.",
        "No causal treatment effect, medication recommendation, diagnosis, or clinical validation is provided.",
        "The residual correction is an adaptive online residual, not a clinically identified insulin-sensitivity model.",
        "Residual shrinkage is selected on calibration-tuning patients; conformal widths use separate calibration-interval patients; test residuals are used only after their target timestamps are observed.",
        "Naive forecast baselines use only the last observed glucose or the running patient glucose mean through each anchor; they do not use future values.",
    ]
    metrics: dict[str, Any] = {
        "data_mode": "synthetic",
        "seed": int(cohort["seed"]),
        "cohort": {
            "patients": int(len(records)),
            "days": int(cohort["days"]),
            "step_minutes": STEP_MINUTES,
            "replay_step_unit": "elapsed_minutes",
            "sample_interval_minutes": SAMPLE_INTERVAL_STEPS * STEP_MINUTES,
            "split_counts": split_counts,
            "calibration_role_counts": {
                role: int(sum(1 for patient_id in calibration_roles.get(role, []) if patient_id in records))
                for role in ("tuning", "interval")
            },
            "sample_counts": {
                split: int(sum(1 for sample in samples if sample.split == split))
                for split in ("train", "calibration", "test")
            },
        },
        "event_definition": dict(EVENT_DEFINITION),
        "models": model_results,
        "models_before_probability_calibration": {
            str(key): dict(value) for key, value in classification_before_calibration.items()
        },
        "forecast": {str(key): dict(value) for key, value in regression_metrics.items()},
        "forecast_before_personalization": {str(key): dict(value) for key, value in before_personalization_metrics.items()},
        "forecast_baseline": {str(key): dict(value) for key, value in baseline_regression_metrics.items()},
        "forecast_persistence": persistence_forecast,
        "forecast_naive_baselines": {
            "last_observed_glucose": persistence_forecast,
            "patient_mean_glucose": patient_mean_forecast,
        },
        "ablations": {
            "event_classification": {str(key): dict(value) for key, value in model_results.items()},
            "forecast": {
                "day1_summary": {str(key): dict(value) for key, value in baseline_regression_metrics.items()},
                "temporal_lags_no_personalization": {str(key): dict(value) for key, value in before_personalization_metrics.items()},
                "temporal_lags_causal_residual": {str(key): dict(value) for key, value in regression_metrics.items()},
                "last_observed_glucose": persistence_forecast,
                "patient_mean_glucose": patient_mean_forecast,
            },
        },
        "forecast_model": "temporal lag features plus causal-in-time residual correction",
        "missingness": dict(missingness),
        "distribution_shift": dict(distribution_shift),
        "event_alerts": dict(event_alerts),
        "personalization": dict(personalization),
        "personalized": bool(personalization.get("enabled", False)),
        "calibration": {
            "probability_method": CALIBRATION_METHOD,
            "probability_tuning_patients": len(calibration_roles.get("tuning", [])),
            "interval_calibration_patients": len(calibration_roles.get("interval", [])),
            "roles_are_patient_disjoint": not bool(set(calibration_roles.get("tuning", [])) & set(calibration_roles.get("interval", []))),
        },
        "conformal": {
            "coverage_target": CONFORMAL_COVERAGE_TARGET,
            "absolute_residual_widths": {str(key): value for key, value in widths.items()},
            "calibration_population": "calibration-interval patients only",
            "minimum_rows": MIN_CONFORMAL_ROWS,
        },
        "limitations": limitations,
    }
    return json_safe(metrics)


def _build_provenance(
    cohort: Mapping[str, Any],
    metrics: Mapping[str, Any],
    output: Path,
) -> dict[str, Any]:
    # Keep provenance deterministic apart from package/runtime metadata; no
    # external URL or data source is consulted.
    return json_safe(
        {
            "artifact_version": ARTIFACT_VERSION,
            "data": "seeded synthetic demographics, labs, and five-minute observations",
            "data_mode": "synthetic",
            "seed": int(cohort["seed"]),
            "simulation_version": SIMULATION_VERSION,
            "cohort": {
                "patients": int(len(cohort["patients"])),
                "days": int(cohort["days"]),
                "step_minutes": STEP_MINUTES,
            },
            "splits": metrics.get("cohort", {}).get("split_counts", {}),
            "split_policy": "patient-disjoint deterministic approximately 60/20/20 train/calibration/test assignment (rounded with non-empty splits)",
            "sample_policy": "anchors every 30 minutes; feature rows use observations at or before anchor; public replay steps are elapsed minutes on a five-minute grid",
            "preprocessing": "median imputation, missing indicators, and standardization fit on train rows only",
            "feature_names": feature_names(),
            "observed_streams": ["cgm", "heart_rate", "hrv", "sleep_hours", "activity", "meal_carbs"],
            "hidden_simulator_parameters_as_features": False,
            "calibration": metrics.get("calibration", {}),
            "conformal": "finite-sample absolute-residual rank from calibration-interval patients only",
            "personalization": metrics.get("personalization", {}),
            "ablations": "event feature-group and forecast baseline comparisons are measured on the held-out test split",
            "network_dependency": False,
            "python": platform.python_version(),
            "platform": platform.platform(),
            "cli_output": str(output),
        }
    )


def build_artifacts(
    output: str | Path,
    patients: int = 60,
    days: int = 5,
    seed: int = 2026,
) -> dict[str, Any]:
    """Generate, train, and persist a reloadable Day-3 artifact bundle."""

    patients, days, seed = _validate_config(patients, days, seed)
    output_path = Path(output)
    if output_path.exists() and not output_path.is_dir():
        raise ValueError(f"output path is not a directory: {output_path}")
    output_path.mkdir(parents=True, exist_ok=True)

    cohort = generate_cohort(patients=patients, days=days, seed=seed)
    calibration_roles = _calibration_role_ids(cohort)
    tuning_ids = set(calibration_roles.get("tuning", []))
    interval_ids = set(calibration_roles.get("interval", []))
    samples = _build_samples(cohort)
    classification_specs, classification_metrics, classification_before_calibration = _fit_classification_models(
        samples,
        seed,
        tuning_ids,
    )
    regression_specs, before_personalization_metrics, base_widths = _fit_regression_models(
        samples,
        seed,
        calibration_ids=interval_ids,
    )
    personalization, regression_metrics, widths = _fit_residual_personalization(
        regression_specs,
        samples,
        tuning_ids,
        interval_ids,
    )
    baseline_regression_metrics, _ = _fit_baseline_regression_models(
        samples,
        seed,
        calibration_ids=interval_ids,
    )
    missingness = _evaluate_missingness(cohort, samples, regression_specs, widths)
    distribution_shift = _evaluate_distribution_shift(cohort, samples, regression_specs, widths)
    event_alerts = _event_level_alert_metrics(cohort, samples, classification_specs)
    metrics = _build_metrics(
        cohort,
        samples,
        classification_metrics,
        classification_before_calibration,
        regression_metrics,
        widths,
        baseline_regression_metrics,
        before_personalization_metrics,
        personalization,
        calibration_roles,
        missingness,
        distribution_shift,
        event_alerts,
    )
    provenance = _build_provenance(cohort, metrics, output_path)

    bundle = {
        "artifact_version": ARTIFACT_VERSION,
        "calibration_roles": calibration_roles,
        "config": {
            "patients": patients,
            "days": days,
            "seed": seed,
            "step_minutes": STEP_MINUTES,
            "sample_interval_minutes": SAMPLE_INTERVAL_STEPS * STEP_MINUTES,
            "forecast_horizons_minutes": list(FORECAST_HORIZONS_MINUTES),
            "event_horizon_minutes": 120,
        },
        "cohort": cohort,
        "test_patient_ids": sorted(
            patient_id
            for patient_id, record in cohort["patients"].items()
            if record.get("split") == "test"
        ),
        "classification_models": classification_specs,
        "regression_models": regression_specs,
        "conformal_widths": {int(key): value for key, value in widths.items()},
        "base_conformal_widths": {int(key): value for key, value in base_widths.items()},
        "residual_personalization": personalization,
        "metrics": metrics,
        "provenance": provenance,
    }
    # joblib is used only for local, reloadable artifacts; all user-facing JSON
    # is separately written with allow_nan=False below.
    joblib.dump(bundle, output_path / "bundle.joblib", compress=3)
    for filename, payload in (("metrics.json", metrics), ("provenance.json", provenance)):
        (output_path / filename).write_text(
            json.dumps(json_safe(payload), indent=2, sort_keys=True, allow_nan=False) + "\n",
            encoding="utf-8",
        )
    manifest = {
        "artifact_version": ARTIFACT_VERSION,
        "bundle": "bundle.joblib",
        "metrics": "metrics.json",
        "provenance": "provenance.json",
        "test_patients": len(bundle["test_patient_ids"]),
        "engine_loads_without_training": True,
    }
    (output_path / "manifest.json").write_text(
        json.dumps(json_safe(manifest), indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return metrics


def _positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an integer") from exc
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build seeded CPU-first AarogyaTwin-X artifacts")
    parser.add_argument("--output", type=Path, default=Path("artifacts"), help="artifact directory")
    parser.add_argument("--patients", type=_positive_int, default=60, help="synthetic patient count (3–500)")
    parser.add_argument("--days", type=_positive_int, default=5, help="observation days per patient (1–14)")
    parser.add_argument("--seed", type=int, default=2026, help="deterministic simulator seed")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        metrics = build_artifacts(args.output, args.patients, args.days, args.seed)
    except (ValueError, OSError, RuntimeError) as exc:
        parser.error(str(exc))
    # Keep CLI output short and machine-readable; the complete report is in
    # metrics.json and provenance.json.
    cohort = metrics.get("cohort", {})
    print(
        json.dumps(
            {
                "status": "ready",
                "output": str(args.output),
                "patients": cohort.get("patients"),
                "days": cohort.get("days"),
                "seed": metrics.get("seed"),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised by the CLI
    raise SystemExit(main())


__all__ = ["ARTIFACT_VERSION", "build_artifacts", "build_parser", "main"]
