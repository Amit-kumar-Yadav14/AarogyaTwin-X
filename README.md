# AarogyaTwin-X Day-1 prototype

A local-only clinician research prototype built from **synthetic data**. It provides
patient-disjoint CPU baselines, a replayable FastAPI API, and a React dashboard for
30/60/120-minute glucose forecast heads and a project-specific sustained high-glucose
event endpoint.

This is not a diagnostic device, clinical validation, medical advice, or a treatment
recommendation. Do not use the scenario sandbox for dosing or care decisions.

## WSL launch

Run these commands from `/home/xking/projects/health`:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r backend/requirements.txt
./scripts/train.sh
```

Start the local API in one terminal:

```bash
source .venv/bin/activate
./scripts/run_api.sh
```

Install and start the dashboard in a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Open `http://127.0.0.1:5173`. The API is bound to `127.0.0.1:8000` and reads the
local `artifacts/` bundle without training automatically.

The training script accepts synthetic-only overrides through environment variables:

```bash
AAROGYA_PATIENTS=60 AAROGYA_DAYS=5 AAROGYA_SEED=2026 ./scripts/train.sh
```

Set `AAROGYA_ARTIFACT_DIR` to use a different local artifact directory. No network
patient-data source is used by the simulator, pipeline, engine, or API.

## Checks

From the project root, with the virtual environment active:

```bash
PYTHONPATH=backend pytest -q backend/tests
cd frontend && npm run build
```

The API's `/api/metrics` response is the source of measured synthetic evaluation
results. Null metrics mean the quantity was undefined or unavailable; they are not
reported as zero performance.
