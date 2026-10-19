# AarogyaTwin-X: Clinician Research Digital Twin for Longitudinal Glucose Forecasting & Conformal Risk Estimation

> **Important Boundary & Clinical Disclaimer:**  
> **Not a diagnostic device. Not clinical validation. Not medical advice.**  
> AarogyaTwin-X is a local-only clinician research prototype for replaying longitudinal synthetic patient timelines, forecasting glucose at 30, 60, and 120 minutes with mathematical uncertainty bounds, and estimating the project-defined risk of new sustained high-glucose episodes. Do not use the scenario sandbox for dosing, medication changes, diagnosis, or care decisions.

---

## 📋 Hackathon Submission Compliance Checklist

| Mandatory Item | Status in Repository / README | Link / Location |
| :--- | :---: | :--- |
| **Team Details** | ✅ Included | [See Team Details Section](#-team-details) |
| **College / Incubator Information** | ✅ Included | [See College / Incubator Section](#-college--incubator-information) |
| **Project Title** | ✅ Included | [See Project Title & Overview](#-project-title--overview) |
| **Problem Statement** | ✅ Included | [See Problem Statement Section](#-problem-statement) |
| **Healthcare Use Case** | ✅ Included | [See Healthcare Use Case Section](#-healthcare-use-case) |
| **Technical Stack** | ✅ Included | [See Technical Stack Section](#-technical-stack) |
| **AI/ML Model / Framework Details** | ✅ Included | [See AI/ML Model Details](#-aiml-model-and-framework-details) |
| **15–20 Minute Demo Video (Unlisted YouTube)** | ✅ Included | [🎥 Watch on YouTube](https://youtu.be/3ck4XbOvc_Y) |
| **Open-source License Details** | ✅ MIT License | [LICENSE](LICENSE) ([Details](#-open-source-license-details)) |
| **Architecture Diagram in PDF/PPT Format** | ✅ Included | [📊 Architecture PPTX](docs/AarogyaTwin-X_System_Architecture.pptx) |
| **Presentation in PDF/PPT Format** | ✅ Included | [📊 Presentation PPTX](docs/AarogyaTwin-X.pptx) |
| **Publicly Accessible Without Extra Permissions** | ✅ Verified | Public GitHub repository, all local assets self-contained |

---

## 👥 Team Details

* **Team Name:** Team Aarogya
* **Team Lead / Members:**
  * Member 1: *AMIT KUMAR* 
  * Member 2: *HANSRAJ PANDEY*


---

## 🏫 College / Incubator Information

* **College / University / Institute:** *ARYA COLLEGE OF ENGINEERING AND IT*
* **Department / Center:** Department of Computer Science & Engineering
* **Incubator / Innovation Cell:** *• Arya Incubation Centre (AIC)*
* **City & State:** *[JAIPUR, RAJASTHAN, India]*

---

## 🏷️ Project Title & Overview

**Project Title:** **AarogyaTwin-X: Clinician Research Prototype for Longitudinal Glucose Forecasting & Conformal Risk Estimation**

AarogyaTwin-X bridges continuous glucose telemetry, machine learning, and clinician decision support. Unlike black-box algorithms that emit overconfident point estimates, AarogyaTwin-X equips clinicians with **statistically calibrated conformal uncertainty bands (90% target coverage)**, a **causal-in-time personalization engine**, **safety abstention under sensor dropout**, and an **interactive What-If scenario sandbox**.

---

## ❗ Problem Statement

Continuous Glucose Monitoring (CGM) streams telemetry at 5-minute intervals, offering an unprecedented opportunity for early diabetes interventions. However, prevailing healthcare AI systems suffer from three critical bottlenecks:

1. **Dangerous Point-Estimate Overconfidence:** Standard regression models produce a single number (e.g. *"185 mg/dL"*). If a clinician or patient acts on an uncalibrated point forecast with corrective insulin, mispredictions cause life-threatening hypoglycemic shock or ketoacidosis.
2. **Alarm Fatigue from Uncalibrated Classifiers:** Hospital alert systems experience false alarm rates exceeding 80–90%, leading clinicians to ignore critical warnings.
3. **Reckless Imputation on Degraded Streams:** When sensors drop out or report stale telemetry (>15 mins), traditional pipelines interpolate or hallucinate values rather than acknowledging missingness.
4. **Data Leakage in Research Prototypes:** Shuffling row-level time-series data allows models to peek into patient identities or future states, leading to artificially inflated benchmark claims that fail in the clinic.

---

## 🩺 Healthcare Use Case

AarogyaTwin-X serves as a **Longitudinal Clinician Digital Twin Research Workbench**:

* **Multi-Horizon Prospective Forecasting:** Provides named forecast heads at **30, 60, and 120 minutes** with split-conformal prediction intervals.
* **Sustained Event Risk Estimation:** Predicts the calibrated probability of a new sustained hyperglycemia event (>180 mg/dL for ≥4 consecutive 5-min intervals) over a 2-hour window.
* **Interactive Scenario Sandbox ("What-If" Exploration):** Clinicians can adjust carbohydrate assumptions (0–100g) and physical activity levels (0–30 min) to observe prospective glucose trajectory adjustments before making care decisions.
* **Responsible Safety Abstention:** When CGM telemetry drops out or is stale (>15 min), the engine **strictly abstains from forecasting**, returning verified null states and explicit provenance warnings instead of guessing.

---

## 🛠️ Technical Stack

### Frontend (Clinician Dashboard)
* **Framework:** React 18 with TypeScript 5.7
* **Build Tooling:** Vite 6 (sub-second HMR, optimized production build)
* **Visualization:** Recharts (SVG telemetry charts with past observations & conformal bands)
* **Icons & Styling:** Lucide React, Custom Responsive Medical Theme (WCAG compliant)

### Backend (Local API Engine)
* **Framework:** FastAPI (Python 3.11, asynchronous REST API)
* **Server:** Uvicorn (ASGI high-performance server)
* **Data Validation:** Pydantic v2 (strict typed contracts for snapshots, telemetry, and scenarios)
* **Privacy & Isolation:** 100% Local-first; zero patient telemetry leaves the machine.

### Machine Learning & Mathematics
* **Frameworks:** Scikit-learn 1.9, NumPy 2.x, Joblib
* **Modeling Paradigm:** HistGradientBoostingRegressor (temporal past-only lag vectors)
* **Calibration:** Platt sigmoid probability scaling (evaluated via Brier score, log loss, and ECE)
* **Uncertainty Quantification:** Inductive Split-Conformal Prediction (distribution-free finite-sample guarantees)

---

## 🧠 AI/ML Model and Framework Details

### 1. Leakage-Free Cohort Design
* **Cohort Size:** 60 synthetic patients × 5 days @ 5-minute sampling (1,440 steps/day).
* **Patient-Disjoint Splits:** 36 Training / 6 Probability-Tuning / 6 Interval-Calibration / 12 Held-Out Test Patients. Patient records are never mixed across splits.

### 2. Temporal Architecture & Causal-in-Time Personalization
* **Feature Representation:** Past-only temporal lags across glucose, glucose velocity/slope, heart rate, sleep context, and meal intake over rolling historical windows. Future data is strictly unreachable.
* **Causal Adaptive Residual:** Patient personalization adjusts for individual baseline drifts using **only matured past errors** (never peeking into the target forecast horizon).

### 3. Evaluation Snapshot (Held-Out Test Cohort)

| Forecast Horizon | MAE | RMSE | Conformal Coverage (90% Target) | Mean Interval Width |
| :---: | :---: | :---: | :---: | :---: |
| **30 minutes** | **7.21 mg/dL** | 9.76 mg/dL | **89.95%** | 30.04 mg/dL |
| **60 minutes** | **7.85 mg/dL** | 10.42 mg/dL | **89.36%** | 32.08 mg/dL |
| **120 minutes** | **8.38 mg/dL** | 11.00 mg/dL | **90.00%** | 34.93 mg/dL |

* **Calibrated Fusion Classifier Metrics (Valid Held-Out Windows):**
  * **AUROC:** `0.94330` | **AUPRC:** `0.27652`
  * **Brier Score:** Reduced from `0.05035` → **`0.02437`** post-calibration
  * **Log Loss:** Reduced from `0.18466` → **`0.13559`**
  * **Expected Calibration Error (ECE):** **`0.02387`**

---

## 🎥 15–20 Minute Demo Video

* **Video Title:** AarogyaTwin-X: Clinician Digital Twin & Conformal Glucose Forecasting
* **YouTube Unlisted Link:** [Watch Demo Video on YouTube (15–20 Mins)](https://youtu.be/3ck4XbOvc_Y)
* **Video Demonstration:** Live walkthrough demonstrating patient timeline replay, multi-horizon conformal forecast heads (30m, 60m, 120m), sensor dropout safety abstention, and What-If scenario sandbox.

---

## 🏛️ Architecture & Presentation Deliverables

The architecture and presentation decks are fully accessible in PPTX format:

| Deliverable | Presentation File | Description |
| :--- | :--- | :--- |
| **System Architecture Diagram & Data Flow** | [📊 Architecture PPTX](docs/AarogyaTwin-X_System_Architecture.pptx) | Complete end-to-end architecture diagram, data flow layers, and safety gates |
| **Comprehensive Presentation Deck** | [📊 Presentation PPTX](docs/AarogyaTwin-X.pptx) | 12-slide comprehensive presentation covering problem, solution, telemetry, and evaluation |

---

## 📜 Open-source License Details

AarogyaTwin-X is licensed under the permissive **MIT License**.  
See the full license terms in the [LICENSE](LICENSE) file.

---

## 💻 Quickstart: Local Setup & Reproduction

### Prerequisites
* Python 3.11+
* Node.js v18+ & npm

### 1. Backend Setup
```bash
# Clone the repository
git clone https://github.com/Amit-kumar-Yadav14/AarogyaTwin-X.git
cd AarogyaTwin-X

# Create and activate Python virtual environment
python -m venv .venv
# On Windows (PowerShell):
.\.venv\Scripts\Activate.ps1
# On Linux/macOS:
source .venv/bin/activate

# Install backend dependencies
python -m pip install -r backend/requirements.txt

# Run backend unit & integration tests
pytest backend/tests
```

### 2. Start Services
```bash
# Terminal 1: Launch Backend API (port 8000)
# Windows:
$env:PYTHONPATH="backend"; .\.venv\Scripts\python -m uvicorn aarogya.api:app --host 127.0.0.1 --port 8000
# Linux/macOS:
PYTHONPATH=backend python -m uvicorn aarogya.api:app --host 127.0.0.1 --port 8000

# Terminal 2: Launch Frontend Dashboard (port 5173)
cd frontend
npm install
npm run dev
```

Open [http://127.0.0.1:5173](http://127.0.0.1:5173) in your browser.
