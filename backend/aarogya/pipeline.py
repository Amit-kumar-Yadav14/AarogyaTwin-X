"""Train and persist the CPU-first Day-1 AarogyaTwin-X baselines.

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
from sklearn.metrics import average_precision_score, brier_score_loss, mean_absolute_error, mean_squared_error, roc_auc_score

from .modeling import (
    NumericPreprocessor,
    ProbabilityEstimator,
    RegressionEstimator,
    json_safe,
    safe_mean,
)
from .simulation import (
    EVENT_DEFINITION,
    FORECAST_HORIZONS_MINUTES,
    FORECAST_HORIZON_STEPS,
    SIMULATION_VERSION,
    STEP_MINUTES,
    event_label,
    feature_names,
    feature_vectors,
    generate_cohort,
)


ARTIFACT_VERSION = "aarogya-day1-bundle-v1"
CONFORMAL_COVERAGE_TARGET = 0.90
SAMPLE_INTERVAL_STEPS = 30 // STEP_MINUTES
MIN_PATIENTS = 3
MIN_DAYS = 1
MAX_PATIENTS = 500
MAX_DAYS = 14


@dataclass
class Sample:
    patient_id: str
    split: str
    anchor_step: int
    features: dict[str, np.ndarray]
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
) -> tuple[np.ndarray, np.ndarray, list[Sample]]:
    selected: list[Sample] = []
    targets: list[float] = []
    for sample in samples:
        if sample.split != split:
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


def _classification_metrics(target: np.ndarray, probability: np.ndarray) -> dict[str, Any]:
    target = np.asarray(target, dtype=int).reshape(-1)
    probability = np.asarray(probability, dtype=float).reshape(-1)
    finite = np.isfinite(probability)
    target = target[finite]
    probability = np.clip(probability[finite], 0.0, 1.0)
    result: dict[str, Any] = {
        "auroc": None,
        "auprc": None,
        "brier": None,
        "prevalence": None,
        "n_test": int(target.size),
    }
    if target.size == 0:
        return result
    result["prevalence"] = float(np.mean(target))
    # Both ranking metrics are undefined for a one-class evaluation set.  Do
    # not rely on sklearn's warning-and-number fallback for all-negative AUPRC;
    # the JSON contract requires null for undefined metrics.
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
    except (ValueError, ArithmeticError):
        result["brier"] = None
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


def _split_conformal_width(residuals: np.ndarray, coverage: float) -> float | None:
    """Finite-sample absolute-residual split-conformal width."""

    values = np.asarray(residuals, dtype=float).reshape(-1)
    values = values[np.isfinite(values)]
    if values.size == 0:
        return None
    quantile = min(1.0, math.ceil((values.size + 1) * float(coverage)) / values.size)
    return float(np.quantile(values, quantile, method="higher"))


def _predict_classifier(
    spec: Mapping[str, Any],
    matrix: np.ndarray,
) -> np.ndarray:
    if matrix.shape[0] == 0:
        return np.empty(0, dtype=float)
    transformed = spec["preprocessor"].transform(matrix)
    return np.asarray(spec["estimator"].predict_probability(transformed), dtype=float)


def _predict_regressor(spec: Mapping[str, Any], matrix: np.ndarray) -> np.ndarray:
    if matrix.shape[0] == 0:
        return np.empty(0, dtype=float)
    transformed = spec["preprocessor"].transform(matrix)
    return np.clip(np.asarray(spec["estimator"].predict_value(transformed), dtype=float), 40.0, 400.0)


def _fit_classification_models(
    samples: Sequence[Sample],
    seed: int,
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    model_specs: dict[str, dict[str, Any]] = {}
    measured: dict[str, dict[str, Any]] = {}
    for offset, kind in enumerate(("static", "sensor", "fusion")):
        train_x, train_y, _ = _rows(samples, "train", kind, require_event=True)
        calibration_x, calibration_y, _ = _rows(samples, "calibration", kind, require_event=True)
        test_x, test_y, _ = _rows(samples, "test", kind, require_event=True)
        preprocessor = NumericPreprocessor().fit(train_x if train_x.shape[0] else np.zeros((1, train_x.shape[1])))
        estimator = ProbabilityEstimator(random_state=seed + offset).fit(
            preprocessor.transform(train_x), train_y
        )
        spec = {
            "feature_kind": kind,
            "feature_names": feature_names()[kind],
            "preprocessor": preprocessor,
            "estimator": estimator,
            "n_train": int(train_y.size),
            "n_calibration": int(calibration_y.size),
        }
        model_specs[kind] = spec
        probability = _predict_classifier(spec, test_x)
        measured[kind] = _classification_metrics(test_y, probability)
        measured[kind]["model_type"] = (
            "logistic_regression" if estimator.model is not None else "constant_fallback"
        )
        measured[kind]["n_train"] = int(train_y.size)
        measured[kind]["n_calibration"] = int(calibration_y.size)

    # Constant prevalence is the intentionally simple persistence comparison for
    # event probability.  It is estimated from train patients only.
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
    model_specs["persistence"] = {
        "feature_kind": None,
        "train_prevalence": persistence_probability,
        "n_train": int(train_y.size),
    }
    return model_specs, measured


def _fit_regression_models(
    samples: Sequence[Sample],
    seed: int,
) -> tuple[dict[int, dict[str, Any]], dict[str, dict[str, Any]], dict[int, float | None]]:
    specs: dict[int, dict[str, Any]] = {}
    measured: dict[str, dict[str, Any]] = {}
    widths: dict[int, float | None] = {}
    kind = "fusion"
    for offset, horizon in enumerate(FORECAST_HORIZONS_MINUTES):
        train_x, train_y, _ = _rows(samples, "train", kind, target_horizon=horizon)
        calibration_x, calibration_y, _ = _rows(samples, "calibration", kind, target_horizon=horizon)
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
            "HistGradientBoostingRegressor"
            if estimator.model is not None
            else "constant_fallback"
        )
        measured[str(horizon)]["n_train"] = int(train_y.size)
        measured[str(horizon)]["n_calibration"] = int(calibration_y.size)
    return specs, measured, widths


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


def _build_metrics(
    cohort: Mapping[str, Any],
    samples: Sequence[Sample],
    classification_metrics: Mapping[str, Mapping[str, Any]],
    regression_metrics: Mapping[str, Mapping[str, Any]],
    widths: Mapping[int, float | None],
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

    model_results: dict[str, Any] = {
        "static_only": {"model_type": "logistic_regression", **dict(classification_metrics["static"])},
        "sensor_only": {"model_type": "logistic_regression", **dict(classification_metrics["sensor"])},
        "fusion": {"model_type": "logistic_regression", **dict(classification_metrics["fusion"])},
        "persistence": {"model_type": "constant_train_prevalence", **dict(classification_metrics["persistence"])},
    }

    limitations = [
        "All records and labels are seeded synthetic development data, not clinical evidence.",
        "Windows are sampled every 30 minutes but remain correlated within patients; row counts are not independent subjects.",
        "Train, calibration, and test partitions are patient-disjoint; split-conformal widths use calibration patients only.",
        "Future label/target readings with missing CGM are excluded rather than treated as negative or normal.",
        "The event endpoint is a project-specific strict-above-180 mg/dL sustained episode definition, not a universal clinical definition.",
        "No causal treatment effect, medication recommendation, diagnosis, or clinical validation is provided.",
        "Personalized residual calibration is disabled for Day 1 because a separately validated past-only calibration path is not established.",
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
            "sample_counts": {
                split: int(sum(1 for sample in samples if sample.split == split))
                for split in ("train", "calibration", "test")
            },
        },
        "event_definition": dict(EVENT_DEFINITION),
        "models": model_results,
        "forecast": {str(key): dict(value) for key, value in regression_metrics.items()},
        "forecast_persistence": persistence_forecast,
        "personalized": False,
        "conformal": {
            "coverage_target": CONFORMAL_COVERAGE_TARGET,
            "absolute_residual_widths": {str(key): value for key, value in widths.items()},
            "calibration_population": "calibration patients only",
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
            "calibration": "split-conformal absolute residual widths from calibration patients only",
            "personalization": False,
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
    """Generate, train, and persist a reloadable Day-1 artifact bundle."""

    patients, days, seed = _validate_config(patients, days, seed)
    output_path = Path(output)
    if output_path.exists() and not output_path.is_dir():
        raise ValueError(f"output path is not a directory: {output_path}")
    output_path.mkdir(parents=True, exist_ok=True)

    cohort = generate_cohort(patients=patients, days=days, seed=seed)
    samples = _build_samples(cohort)
    classification_specs, classification_metrics = _fit_classification_models(samples, seed)
    regression_specs, regression_metrics, widths = _fit_regression_models(samples, seed)
    metrics = _build_metrics(cohort, samples, classification_metrics, regression_metrics, widths)
    provenance = _build_provenance(cohort, metrics, output_path)

    bundle = {
        "artifact_version": ARTIFACT_VERSION,
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
