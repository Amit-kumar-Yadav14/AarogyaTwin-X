from __future__ import annotations

from pathlib import Path

import numpy as np
from fastapi.testclient import TestClient

from aarogya.api import create_app
from aarogya.engine import TwinEngine
from aarogya.modeling import ProbabilityCalibrator
from aarogya.pipeline import build_artifacts
from aarogya.simulation import event_label, feature_vectors, generate_cohort


def test_event_label_obeys_strict_threshold_and_unknown_missing_data() -> None:
    below_threshold = [100.0] + [180.0] * 4 + [100.0] * 25
    above_threshold = [100.0] + [180.01] * 4 + [100.0] * 25
    missing_future = [100.0, 181.0, 182.0, float("nan"), 184.0] + [100.0] * 25
    already_above = [181.0] + [181.0] * 29

    assert event_label(below_threshold, 0) == 0
    assert event_label(above_threshold, 0) == 1
    assert event_label(missing_future, 0) is None
    assert event_label(already_above, 0) is None


def test_temporal_features_are_past_only() -> None:
    cohort = generate_cohort(patients=3, days=2, seed=2026)
    record = next(iter(cohort["patients"].values()))
    anchor = 120
    original = {name: np.asarray(values, dtype=float).copy() for name, values in record["observations"].items()}
    altered = {name: values.copy() for name, values in original.items()}
    for values in altered.values():
        values[anchor + 1 :] = 999999.0

    before = feature_vectors(record, anchor, original)
    after = feature_vectors(record, anchor, altered)
    assert np.array_equal(before["temporal"], after["temporal"], equal_nan=True)


def test_probability_calibrator_handles_single_class_and_empty_inputs() -> None:
    empty = ProbabilityCalibrator().fit([], [])
    assert empty.status_ == "unavailable_no_rows"
    assert empty.predict_probability([0.2, 0.8]).tolist() == [0.2, 0.8]

    single = ProbabilityCalibrator().fit([0.2, 0.8], [0, 0])
    assert single.status_ == "constant_single_class_fallback"
    assert single.predict_probability([0.2, 0.8]).tolist() == [0.0, 0.0]


def test_pipeline_persists_reloadable_held_out_engine(tmp_path: Path) -> None:
    artifact_dir = tmp_path / "artifacts"
    # Ten patients yield two calibration patients, allowing separate tuning and
    # interval-calibration roles in the Day-3 artifact.
    metrics = build_artifacts(artifact_dir, patients=10, days=2, seed=2026)

    assert (artifact_dir / "bundle.joblib").is_file()
    assert (artifact_dir / "metrics.json").is_file()
    assert metrics["data_mode"] == "synthetic"
    assert metrics["cohort"]["split_counts"]["test"] == 2
    assert metrics["forecast"]["30"]["model_type"] == "temporal_lags_with_causal_residual"
    assert metrics["forecast_before_personalization"]["30"]["model_type"] == "HistGradientBoostingRegressor_temporal_lags"
    assert metrics["forecast_baseline"]["30"]["model_type"] == "HistGradientBoostingRegressor_day1_summary"
    assert metrics["personalized"] is True
    assert metrics["personalization"]["tuning_split"] == "calibration-tuning patients only for residual shrinkage"
    assert metrics["personalization"]["interval_split"] == "calibration-interval patients only for conformal widths"
    assert metrics["calibration"]["roles_are_patient_disjoint"] is True
    assert metrics["calibration"]["probability_tuning_patients"] >= 1
    assert metrics["calibration"]["interval_calibration_patients"] >= 1
    assert "log_loss" in metrics["models"]["fusion"]
    assert "expected_calibration_error" in metrics["models"]["fusion"]
    assert "models_before_probability_calibration" in metrics
    missingness = metrics["missingness"]["scenarios"]
    assert set(missingness) == {
        "natural_missingness",
        "random_recent_stream_missingness_25pct",
        "recent_cgm_dropout_30m",
    }
    assert missingness["natural_missingness"]["30"]["n_predicted"] > 0
    assert missingness["recent_cgm_dropout_30m"]["30"]["n_predicted"] == 0
    assert missingness["recent_cgm_dropout_30m"]["30"]["abstention_rate"] == 1.0
    shifts = metrics["distribution_shift"]["scenarios"]
    assert set(shifts) == {
        "nominal_test",
        "glucose_level_plus_25",
        "meal_carbs_2x_inputs",
        "hba1c_plus_1_static",
    }
    assert shifts["nominal_test"]["30"]["n_test"] > 0
    assert shifts["glucose_level_plus_25"]["30"]["target_transform"] == "+25 mg/dL"
    alerts = metrics["event_alerts"]
    assert alerts["status"] == "measured"
    assert set(alerts["thresholds"]) == {"0.10", "0.20", "0.50"}
    assert alerts["thresholds"]["0.20"]["episode_metrics"]["n_event_episodes"] >= 0
    assert "false_alerts_per_patient_day" in alerts["thresholds"]["0.20"]["episode_metrics"]
    naive = metrics["forecast_naive_baselines"]
    assert set(naive) == {"last_observed_glucose", "patient_mean_glucose"}
    assert all(set(results) == {"30", "60", "120"} for results in naive.values())
    assert set(metrics["ablations"]["forecast"]) == {
        "day1_summary",
        "temporal_lags_no_personalization",
        "temporal_lags_causal_residual",
        "last_observed_glucose",
        "patient_mean_glucose",
    }

    engine = TwinEngine(artifact_dir)
    patients = engine.list_patients()
    assert len(patients) == 2
    assert all(patient["split"] == "test" for patient in patients)

    snapshot = engine.snapshot(patients[0]["id"], step=patients[0]["default_step"])
    assert snapshot["patient"]["split"] == "test"
    assert snapshot["status"]["twin"] == "ready"
    assert [point["minutes_ahead"] for point in snapshot["forecast"]] == [30, 60, 120]
    assert snapshot["predictions"]["available"] is True
    assert snapshot["predictions"]["personalized"] is True

    dropout = engine.snapshot(
        patients[0]["id"],
        step=patients[0]["default_step"],
        sensor_dropout=True,
    )
    assert dropout["status"]["sensor_dropout"] is True
    assert dropout["predictions"]["available"] is False
    assert dropout["forecast"] == []
    assert dropout["predictions"]["risk_120m"] is None
    assert dropout["predictions"]["glucose_30m"] is None
    assert dropout["predictions"]["glucose_60m"] is None
    assert dropout["predictions"]["glucose_120m"] is None
    assert any("abstained" in warning.lower() for warning in dropout["warnings"])

    scenario = engine.simulate(
        patients[0]["id"],
        step=patients[0]["default_step"],
        activity_minutes=15,
        meal_carbs=30,
    )
    assert scenario["baseline"] == snapshot["forecast"]
    assert "not medical advice" in scenario["disclaimer"].lower()
    assert any("dosing" in assumption.lower() for assumption in scenario["assumptions"])


def test_personalization_ignores_future_observations(tmp_path: Path) -> None:
    artifact_dir = tmp_path / "future-isolation-artifacts"
    build_artifacts(artifact_dir, patients=6, days=2, seed=2026)
    engine = TwinEngine(artifact_dir)
    patient = engine.list_patients()[0]
    step = patient["default_step"]
    before = engine.snapshot(patient["id"], step=step)

    record = engine._patients[patient["id"]]
    future_index = step // 5 + 1
    for values in record["observations"].values():
        values[future_index:] = 999999.0

    after = engine.snapshot(patient["id"], step=step)
    assert before["forecast"] == after["forecast"]
    assert before["predictions"]["risk_120m"] == after["predictions"]["risk_120m"]


def test_api_exposes_local_contract_and_failure_state(tmp_path: Path) -> None:
    missing_client = TestClient(create_app(tmp_path / "missing"))
    not_ready = missing_client.get("/api/health")
    assert not_ready.status_code == 200
    assert not_ready.json()["status"] == "not_ready"
    assert not_ready.json()["data_mode"] == "synthetic"
    assert missing_client.get("/api/patients").status_code == 503

    artifact_dir = tmp_path / "api-artifacts"
    build_artifacts(artifact_dir, patients=6, days=2, seed=2026)
    client = TestClient(create_app(artifact_dir))

    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ready"

    patients = client.get("/api/patients")
    assert patients.status_code == 200
    patient = patients.json()["patients"][0]
    patient_id = patient["id"]

    snapshot = client.get(
        f"/api/twin/{patient_id}",
        params={"step": patient["default_step"], "sensor_dropout": "false"},
    )
    assert snapshot.status_code == 200
    assert snapshot.json()["patient"]["id"] == patient_id

    scenario = client.post(
        f"/api/twin/{patient_id}/simulate",
        json={
            "step": patient["default_step"],
            "activity_minutes": 15,
            "meal_carbs": 30,
            "sensor_dropout": False,
        },
    )
    assert scenario.status_code == 200
    assert scenario.json()["activity_minutes"] == 15
    assert scenario.json()["meal_carbs"] == 30

    invalid_scenario = client.post(
        f"/api/twin/{patient_id}/simulate",
        json={"activity_minutes": 31, "meal_carbs": 0},
    )
    assert invalid_scenario.status_code == 422

    metrics = client.get("/api/metrics")
    assert metrics.status_code == 200
    assert metrics.json()["data_mode"] == "synthetic"

    assert client.get("/api/twin/not-a-patient").status_code == 404
    assert client.get(f"/api/twin/{patient_id}", params={"step": 1}).status_code == 400
