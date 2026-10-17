# AarogyaTwin-X — five-day build plan

## Goal and constraints

Build a clinician-facing, reproducible **research prototype**, not a diagnostic device.
Combine synthetic static patient records with synthetic CGM, heart rate, HRV, sleep,
activity and meal observations. Forecast glucose at 30, 60 and 120 minutes and estimate
a new sustained high-glucose event in the next 120 minutes.

The user requested a 4–5 day build and all project storage under `E:\health`.
Detected hardware: i7-13620H, approximately 16 GiB RAM, Intel UHD graphics; no NVIDIA
GPU detected; approximately 31 GiB free on E: at kickoff. Use CPU-friendly baselines
first. Do not download large model weights or install CUDA without reassessing capacity.
Existing Python 3.11 and Node 22 executables are on C:; project environments, caches,
temporary files, datasets and outputs are configured locally on E:. OS/app internal
storage is outside the project's control. No real patient data is needed.

## First user flow / acceptance criteria

1. Run setup, generate a seeded synthetic cohort and train a real baseline locally.
2. Open a dashboard, select a held-out synthetic patient and inspect observed history,
   a three-horizon forecast, uncertainty intervals and a 120-minute event estimate.
3. Advance a replay clock. Only observations available at that clock may be features.
4. Disconnect recent CGM data. Show data-quality warnings and abstain when too stale.
5. Compare an explicitly assumption-based activity/meal scenario with the forecast.
   It is not a causal treatment estimate or medical recommendation.
6. View actual held-out metrics and provenance. No fabricated accuracy, patients,
   attribution, LLM responses, clinical validation or public-dataset claims.
7. Missing artifacts, unavailable API and invalid inputs have useful failure states.

## Operational event definition

The threshold is **strictly above 180 mg/dL**. A sustained episode requires four
consecutive 5-minute readings above the threshold, spanning 15 minutes. For the first
baseline, a positive 120-minute label requires onset AND its 15-minute confirmation
inside the forecast window. Anchors already above 180 are not eligible for a new-event
probability; glucose forecasting can still be displayed. This is a project endpoint,
not a universal clinical definition. Missing future labels are not negative events.

## Stack and boundaries

- Python 3.11, NumPy, pandas, scikit-learn: seeded simulator and measured baselines.
- FastAPI + Pydantic: typed, local-only API; no external patient-data transmissions.
- React + TypeScript + Vite + Recharts: clinician dashboard, no mock medical numbers.
- Project-local virtual environment; locked frontend dependencies; Python versions pinned.
- Independent ownership: `backend/aarogya/` prediction implementation and `frontend/`
  UI implementation. Main session owns API, scripts, tests, integration and docs.
- The prediction engine and API share `docs/API_CONTRACT.md`.

## Five-day priorities (timeboxes, not completion claims)

| Day | Must ship | Stretch / gated on evidence |
| --- | --- | --- |
| 1 | Synthetic cohort, patient-disjoint baseline, API, dashboard, replay, checks | Scenario panel |
| 2 | Better temporal model, causal-in-time residual personalization, ablations | CPU-sized neural model if justified |
| 3 | Calibration, missingness and distribution-shift tests, event-level alert metrics | License-checked public CGM benchmark |
| 4 | Polish demo; structured evidence summary and safety tests | Small local LLM copilot if memory/storage permit |
| 5 | Fresh setup audit, README, architecture/presentation PDFs, >=20-minute video preparation | Final polish only |

Day 1 results are synthetic development evidence. A simulator-generated hidden
parameter is not a measured physiological state. An adaptive residual is not a
clinically identified insulin-sensitivity model. Do not imply otherwise.

## Submission checklist still requiring user input

- Team name, college/incubator and verified full-time student members (1–4).
- Public repository creation/publication approval; never publish automatically.
- Team leader contact details belong on the submission platform, not in public code.
- Required final folder: `Team Name_College Name` (choose once names are supplied).
- README: team details, title, problem, stack, model, video link and open-source license.
- Architecture PDF/PPT, presentation PDF/PPT, accessible >=20-minute demonstration.
- Submission deadline in the supplied brief: 20 October 2026, 19:00 IST.
- Organizer clarification: the brief inconsistently says top 5 versus top 10 at screening.

No ranking or selection guarantee. No medicine dosing, diagnosis or patient advice.
