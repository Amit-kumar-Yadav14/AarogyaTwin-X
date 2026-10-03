# AarogyaTwin-X

A local-only clinician research prototype for replaying a **synthetic** patient timeline,
forecasting glucose at 30, 60, and 120 minutes, and estimating the project-defined risk
of a new sustained high-glucose episode.

> **Not a diagnostic device. Not clinical validation. Not medical advice.**
> Do not use the scenario sandbox for dosing, medication changes, diagnosis, or care decisions.

## What is included

- Seeded synthetic cohort: 60 patients × 5 days at a 5-minute observation grid.
- Synthetic static records, CGM/glucose, heart rate, HRV, sleep, activity, and meal data.
- Patient-disjoint train/calibration/test evaluation: 36 / 12 / 12 patients.
- CPU-friendly temporal lag model with 30/60/120-minute forecast heads.
- Bounded causal-in-time per-patient residual adjustment. This is an adaptive residual,
  not a clinically identified insulin-sensitivity model.
- Split-conformal forecast intervals and separately calibrated event probabilities.
- Local FastAPI API and React/Vite dashboard with replay, dropout abstention, provenance,
  scenario sandbox, structured metrics, and safety/error states.
- Day-3 synthetic evidence for calibration, missingness, distribution shift, and alert behavior.

## Day-5 deliverables

- `docs/EVIDENCE_SUMMARY.md` — structured saved evidence from the Day-3 artifact.
- `docs/ARCHITECTURE.md` — implementation and data-flow description.
- `docs/PRESENTATION.md` — slide-by-slide presentation source.
- `docs/VIDEO_RUNBOOK.md` — reproducible demonstration script and timing.
- `docs/AarogyaTwinX_Architecture.pptx` / `.pdf` — generated architecture deck.
- `docs/AarogyaTwinX_Presentation.pptx` / `.pdf` — generated presentation deck.

The decks are generated locally by `scripts/build_decks.py` using only Python's standard
library. No network, public benchmark, or large model is needed. The PPTX files are
editable; the matching PDFs are printable exports of the same concise content.

## Local WSL setup

Run from `/home/xking/projects/health`:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r backend/requirements.txt
./scripts/train.sh
```

`./scripts/train.sh` generates the seeded synthetic artifact bundle under `artifacts/`.
The engine loads artifacts; it never trains automatically during API requests.

Start the API in one terminal:

```bash
source .venv/bin/activate
./scripts/run_api.sh
```

Start the dashboard in a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Open `http://127.0.0.1:5173`. The API listens on `127.0.0.1:8000`, and the Vite proxy
forwards `/api` requests locally. No patient data is transmitted externally.

Synthetic-only training overrides:

```bash
AAROGYA_PATIENTS=60 AAROGYA_DAYS=5 AAROGYA_SEED=2026 ./scripts/train.sh
```

Set `AAROGYA_ARTIFACT_DIR` to use another local artifact directory. The default is
`/home/xking/projects/health/artifacts`.

## API surface

- `GET /api/health`
- `GET /api/patients`
- `GET /api/twin/{patient_id}?step=480&sensor_dropout=false`
- `POST /api/twin/{patient_id}/simulate`
- `GET /api/metrics`

See `docs/API_CONTRACT.md` for the typed response contract.

## Evaluation snapshot

These are saved synthetic held-out results, not clinical performance:

| Horizon | MAE | RMSE | Interval coverage | Mean interval width |
|---:|---:|---:|---:|---:|
| 30 min | 7.21 mg/dL | 9.76 mg/dL | 89.95% | 30.04 mg/dL |
| 60 min | 7.85 mg/dL | 10.42 mg/dL | 89.36% | 32.08 mg/dL |
| 120 min | 8.38 mg/dL | 11.00 mg/dL | 90.00% | 34.93 mg/dL |

The calibrated fusion event classifier has AUROC `0.94330`, AUPRC `0.27652`, Brier
score `0.02437`, log loss `0.13559`, and expected calibration error `0.02387` on
valid held-out synthetic event windows. Alert metrics are reported separately because
ranking metrics do not describe alert burden or episode detection.

## Checks

With the project environment active:

```bash
PYTHONPATH=backend pytest -q backend/tests
cd frontend && npm run build
```

The local API smoke path should verify health, held-out patients, a forecast snapshot,
CGM-dropout abstention, metrics, and invalid-input behavior. Null metrics and null
prediction fields mean unavailable or undefined; they are not zero performance.

## Safety and interpretation boundaries

- The event threshold is strictly above `180 mg/dL` for four consecutive 5-minute readings.
- Anchors already above threshold do not receive a new-event probability.
- Missing future labels are excluded, never treated as negative events.
- Forecast lines connect only the calibrated 30/60/120-minute heads; they are not extra
  calibrated predictions, and sampled peak is not a guaranteed future peak.
- Drivers are observed context, not SHAP explanations or causal attribution.
- Scenario activity/carbohydrate controls are bounded sandbox assumptions, not recommendations
  or treatment effects.
- Distribution-shift tests demonstrate known failure modes; they do not establish robustness.

For a concise evidence and limitation record, see `docs/EVIDENCE_SUMMARY.md`.
