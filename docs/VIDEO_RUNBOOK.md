# AarogyaTwin-X video runbook

## Goal

Record a reproducible 20–24 minute demonstration of the local synthetic research prototype. Do not claim clinical validity, treatment effects, dosing support, or real-patient performance.

## Before recording

- Use the current saved synthetic artifact bundle, seed `2026`.
- Close unrelated windows and hide personal/account information.
- Confirm that no real patient data is visible.
- Open the presentation deck and `docs/EVIDENCE_SUMMARY.md`.
- Start the local API and dashboard using the README commands.
- Keep a terminal ready to show `/api/health` and launch commands.
- Do not rerun full training just for recording if the saved artifact is already verified; explain the reproducible command instead.

## Timing and actions

| Time | Segment | Show / say |
|---|---|---|
| 0:00–1:15 | Opening | Title; synthetic-only research boundary; not clinical use |
| 1:15–2:45 | Problem | Why forecasts need uncertainty, freshness, and provenance |
| 2:45–4:15 | Data | 60 synthetic patients, five days, five-minute grid; streams |
| 4:15–5:45 | Split | 36 train, 6 tuning, 6 interval calibration, 12 held-out test |
| 5:45–7:15 | Model | Temporal lags, CPU model, calibrated event probability |
| 7:15–8:30 | Residual | Matured past errors only; bounded adjustment; no physiology claim |
| 8:30–10:00 | Launch | README commands and ready API; explain artifact loading |
| 10:00–11:30 | Patient replay | Select held-out record; demographics; replay +5 minutes |
| 11:30–13:15 | Forecast | Current context, three heads, uncertainty, sampled-peak caveat |
| 13:15–14:45 | Dropout | Enable 30-minute CGM dropout; show warning, null estimates, abstention |
| 14:45–16:00 | Scenario | Show bounded inputs, assumptions, inherited bands, non-medical disclaimer |
| 16:00–18:00 | Evidence | Baselines, calibration, missingness, shift results |
| 18:00–19:15 | Alerts | Distinguish AUROC from episode detection and false-alert burden |
| 19:15–20:45 | Limitations | Single simulator, correlated windows, small cohort, shift failures |
| 20:45–22:00 | Close | Reproducibility, local-only architecture, honest next validation needs |

## Launch sequence

From `/home/xking/projects/health`:

```bash
source .venv/bin/activate
./scripts/run_api.sh
```

In another terminal:

```bash
cd /home/xking/projects/health/frontend
npm run dev
```

Open `http://127.0.0.1:5173`.

The reproducible synthetic build command is:

```bash
PYTHON_BIN="$PWD/.venv/bin/python" ./scripts/train.sh
```

Do not imply that the API trains on startup: it only loads existing artifacts.

## Demo checkpoints

1. **Warning visible:** “SYNTHETIC RESEARCH” and “NOT FOR CLINICAL USE.”
2. **Held-out patient:** patient record says `test` split.
3. **Replay:** advance exactly five minutes and point out the timestamp.
4. **History:** observed values are separated from future forecast heads.
5. **Forecast:** show 30/60/120 minutes and interval target; explain that lines are interpolation.
6. **Event risk:** explain the strict >180 mg/dL sustained-event definition; no new-event risk when already above threshold.
7. **Dropout:** enable the toggle and show unavailable forecast with reason.
8. **Scenario:** read the assumption and non-medical disclaimer; no medication changes.
9. **Evidence:** show measured results and limitations, not only favorable metrics.
10. **Failure case:** explain missing-artifact/not-ready behavior without deleting artifacts during the recording.

## Suggested concise narration

> “All records in this demonstration are synthetic. The system only uses observations available at the replay clock. It returns three named forecast heads, intervals, data-quality warnings, and provenance. When CGM is too stale, it abstains. The scenario comparison is an assumption-based sandbox, not treatment advice. Our evaluation is patient-disjoint, but it is still one synthetic simulator and does not establish clinical validity.”

## If something fails live

- API unavailable: show the clear error state and the README launch command.
- Artifacts not ready: explain `scripts/train.sh`; do not insert fallback medical numbers.
- Forecast unavailable: read the actual reason; this may be intentional abstention.
- Metric null: explain undefined/unmeasured rather than interpreting it as zero.
- Browser or network issue: use the saved local evidence summary and clearly label it as saved evidence.

## Final review before submission

- Confirm the video is at least 20 minutes.
- Confirm audio is intelligible and text is readable.
- Confirm no private data, account details, or secrets are visible.
- Confirm every performance statement says synthetic/held-out where appropriate.
- Confirm no medical, dosing, causal, or clinical-validation claim was added.
- Confirm the video link is accessible under the organizer's requirements.
