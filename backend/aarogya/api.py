"""Local-only FastAPI surface for the AarogyaTwin-X synthetic prototype."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .engine import TwinEngine
from .modeling import json_safe


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ARTIFACT_DIR = PROJECT_ROOT / "artifacts"


class ScenarioRequest(BaseModel):
    """Validated bounds for the assumption-based sandbox endpoint."""

    step: int | None = Field(default=None, ge=0)
    activity_minutes: int = Field(..., ge=0, le=30)
    meal_carbs: int = Field(..., ge=0, le=100)
    sensor_dropout: bool = False


class ArtifactUnavailable(RuntimeError):
    """Raised when the API has not been given a usable local artifact bundle."""


class ArtifactProvider:
    """Load and refresh the engine without ever training inside an API request."""

    def __init__(self, artifact_dir: Path):
        self.artifact_dir = artifact_dir
        self._engine: TwinEngine | None = None
        self._signature: tuple[int, int] | None = None

    @property
    def bundle_path(self) -> Path:
        return self.artifact_dir / "bundle.joblib"

    def get(self) -> TwinEngine:
        bundle_path = self.bundle_path
        try:
            stat = bundle_path.stat()
        except FileNotFoundError as exc:
            self._engine = None
            self._signature = None
            raise ArtifactUnavailable(
                f"Synthetic artifacts are not built at {self.artifact_dir}. "
                "Run scripts/train.sh before using prediction endpoints."
            ) from exc
        signature = (int(stat.st_mtime_ns), int(stat.st_size))
        if self._engine is None or self._signature != signature:
            try:
                self._engine = TwinEngine(self.artifact_dir)
            except (FileNotFoundError, OSError, ValueError, RuntimeError) as exc:
                self._engine = None
                self._signature = None
                raise ArtifactUnavailable(str(exc)) from exc
            self._signature = signature
        return self._engine


def _artifact_dir(value: str | Path | None) -> Path:
    configured = value if value is not None else os.environ.get("AAROGYA_ARTIFACT_DIR")
    path = Path(configured) if configured else DEFAULT_ARTIFACT_DIR
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def _unavailable(provider: ArtifactProvider) -> HTTPException:
    try:
        provider.get()
    except ArtifactUnavailable as exc:
        return HTTPException(status_code=503, detail=str(exc))
    return HTTPException(status_code=503, detail="Synthetic API is not ready.")


def _engine_or_503(provider: ArtifactProvider) -> TwinEngine:
    try:
        return provider.get()
    except ArtifactUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def _call_engine(call: Any) -> Any:
    try:
        return call()
    except KeyError as exc:
        patient_id = str(exc.args[0]) if exc.args else "unknown"
        raise HTTPException(status_code=404, detail=f"Unknown synthetic patient: {patient_id}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def create_app(artifact_dir: str | Path | None = None) -> FastAPI:
    """Create the local API app.

    The default artifact location is ``<project>/artifacts``.  Set
    ``AAROGYA_ARTIFACT_DIR`` or pass ``artifact_dir`` for an isolated test/demo
    bundle.  The API only loads artifacts; it never generates or trains them.
    """

    provider = ArtifactProvider(_artifact_dir(artifact_dir))
    app = FastAPI(
        title="AarogyaTwin-X Synthetic Research API",
        version="day1",
        docs_url="/docs",
        redoc_url=None,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
        allow_methods=["GET", "POST"],
        allow_headers=["Accept", "Content-Type"],
    )

    @app.get("/api/health")
    def health() -> dict[str, str]:
        try:
            provider.get()
        except ArtifactUnavailable as exc:
            return {
                "status": "not_ready",
                "data_mode": "synthetic",
                "message": str(exc),
            }
        return {
            "status": "ready",
            "data_mode": "synthetic",
            "message": "Synthetic held-out artifacts are loaded; the API is local-only.",
        }

    @app.get("/api/patients")
    def patients() -> dict[str, Any]:
        engine = _engine_or_503(provider)
        return json_safe({"patients": engine.list_patients()})

    @app.get("/api/twin/{patient_id}")
    def snapshot(
        patient_id: str,
        step: int | None = Query(default=None, ge=0),
        sensor_dropout: bool = False,
    ) -> dict[str, Any]:
        engine = _engine_or_503(provider)
        return json_safe(_call_engine(lambda: engine.snapshot(patient_id, step, sensor_dropout)))

    @app.post("/api/twin/{patient_id}/simulate")
    def simulate(patient_id: str, payload: ScenarioRequest) -> dict[str, Any]:
        engine = _engine_or_503(provider)
        return json_safe(
            _call_engine(
                lambda: engine.simulate(
                    patient_id,
                    step=payload.step,
                    activity_minutes=payload.activity_minutes,
                    meal_carbs=payload.meal_carbs,
                    sensor_dropout=payload.sensor_dropout,
                )
            )
        )

    @app.get("/api/metrics")
    def metrics() -> dict[str, Any]:
        engine = _engine_or_503(provider)
        return json_safe(engine.metrics())

    return app


app = create_app()


__all__ = ["ArtifactProvider", "ScenarioRequest", "app", "create_app"]
