from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from aarogya.api import create_app
from aarogya.engine import TwinEngine
from aarogya.pipeline import build_artifacts
from aarogya.simulation import event_label


def test_event_label_obeys_strict_threshold_and_unknown_missing_data() -> None:
    below_threshold = [100.0] + [180.0] * 4 + [100.0] * 25
    above_threshold = [100.0] + [180.01] * 4 + [100.0] * 25
    missing_future = [100.0, 181.0, 182.0, float("nan"), 184.0] + [100.0] * 25
    already_above = [181.0] + [181.0] * 29

    assert event_label(below_threshold, 0) == 0
    assert event_label(above_threshold, 0) == 1
    assert event_label(missing_future, 0) is None
    assert event_label(already_above, 0) is None


def test_pipeline_persists_reloadable_held_out_engine(tmp_path: Path) -> None:
    artifact_dir = tmp_path / "artifacts"
    metrics = build_artifacts(artifact_dir, patients=6, days=2, seed=2026)

    assert (artifact_dir / "bundle.joblib").is_file()
    assert (artifact_dir / "metrics.json").is_file()
    assert metrics["data_mode"] == "synthetic"
    assert metrics["cohort"]["split_counts"]["test"] == 2

    engine = TwinEngine(artifact_dir)
    patients = engine.list_patients()
    assert len(patients) == 2
    assert all(patient["split"] == "test" for patient in patients)

    snapshot = engine.snapshot(patients[0]["id"], step=patients[0]["default_step"])
    assert snapshot["patient"]["split"] == "test"
    assert snapshot["status"]["twin"] == "ready"
    assert [point["minutes_ahead"] for point in snapshot["forecast"]] == [30, 60, 120]
    assert snapshot["predictions"]["available"] is True

    dropout = engine.snapshot(
        patients[0]["id"],
        step=patients[0]["default_step"],
        sensor_dropout=True,
    )
    assert dropout["status"]["sensor_dropout"] is True
    assert dropout["predictions"]["available"] is False
    assert dropout["forecast"] == []
    assert dropout["predictions"]["risk_120m"] is None


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
