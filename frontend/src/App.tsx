import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Activity, AlertOctagon, ArrowUpRight, CheckCircle2, RefreshCw, ServerCog, ShieldAlert } from 'lucide-react';
import { ApiRequestError, getHealth, getMetrics, getPatients, getSnapshot, simulate } from './api';
import type { HealthResponse, MetricsPayload, Patient, Scenario, Snapshot } from './types';
import { formatDateTime, formatNumber } from './utils';
import { CurrentSummary } from './components/CurrentSummary';
import { DriversPanel } from './components/DriversPanel';
import { EvidencePanel } from './components/EvidencePanel';
import { ForecastPanel } from './components/ForecastPanel';
import { Header } from './components/Header';
import { HistoryPanel } from './components/HistoryPanel';
import { MetricsPanel } from './components/MetricsPanel';
import { PatientSelector } from './components/PatientSelector';
import { ErrorState, LoadingState, Panel, SectionHeading, StatusPill } from './components/Primitives';
import { ScenarioPanel } from './components/ScenarioPanel';
import { Sidebar } from './components/Sidebar';

type LoadState<T> = {
  data: T | null;
  loading: boolean;
  error: string | null;
};

const EMPTY_PATIENTS: Patient[] = [];

function isAbortError(error: unknown): boolean {
  return (typeof DOMException !== 'undefined' && error instanceof DOMException && error.name === 'AbortError') ||
    (error instanceof Error && error.name === 'AbortError');
}

function errorMessage(error: unknown): string {
  if (error instanceof ApiRequestError) {
    const setupHint =
      error.status === 0 ||
      error.status === 404 ||
      error.status === 503 ||
      /artifact|train|not.?ready|not available/i.test(error.message)
        ? ' If artifacts are missing, run scripts/train.sh from the project root, then restart the local API.'
        : '';
    return `${error.message}${setupHint}`;
  }
  if (error instanceof Error && error.message) {
    return `${error.message} If the local API is unavailable or artifacts are missing, start it and run scripts/train.sh from the project root.`;
  }
  return 'The local API returned an unexpected response. Start it and run scripts/train.sh from the project root if artifacts are missing.';
}

function clamp(value: number, minimum: number, maximum: number): number {
  return Math.min(maximum, Math.max(minimum, value));
}

function toReplayStep(value: number, patient: Patient): number {
  if (!Number.isFinite(value)) return patient.default_step;
  const stepped = patient.min_step + Math.round((value - patient.min_step) / 5) * 5;
  return clamp(stepped, patient.min_step, patient.max_step);
}

function SetupNotice({ health }: { health: HealthResponse | null }) {
  if (!health || health.status === 'ready') return null;
  return (
    <div className="setup-notice" role="status">
      <div className="setup-notice-icon" aria-hidden="true"><ServerCog size={20} /></div>
      <div>
        <strong>Local prediction artifacts are not ready</strong>
        <p>{health.message || 'The API is running without a trained artifact bundle.'}</p>
        <div className="setup-command-row">
          <span>Build the seeded synthetic bundle with</span>
          <code>scripts/train.sh</code>
          <span>then reload this dashboard.</span>
        </div>
      </div>
    </div>
  );
}

function WorkspaceStatus({ health, patients, snapshot }: { health: LoadState<HealthResponse>; patients: LoadState<{ patients: Patient[] }>; snapshot: Snapshot | null }) {
  const ready = health.data?.status === 'ready';
  const patientCount = patients.data?.patients.length;
  return (
    <div className="workspace-status" aria-label="Workspace status">
      <div className="workspace-status-item">
        <span className={`status-dot ${ready ? 'status-dot-good' : health.error || health.data ? 'status-dot-warn' : ''}`} aria-hidden="true" />
        <span>{ready ? 'Local API ready' : health.loading ? 'Checking local API' : 'API needs attention'}</span>
      </div>
      <div className="workspace-status-item">
        <Activity size={14} aria-hidden="true" />
        <span>{patientCount === undefined ? 'Patients pending' : `${formatNumber(patientCount)} synthetic records`}</span>
      </div>
      {snapshot && <div className="workspace-status-item"><CheckCircle2 size={14} aria-hidden="true" /><span>Snapshot at step {formatNumber(snapshot.step)}</span></div>}
    </div>
  );
}

export default function App() {
  const [mobileOpen, setMobileOpen] = useState(false);
  const [workspaceRefresh, setWorkspaceRefresh] = useState(0);
  const [health, setHealth] = useState<LoadState<HealthResponse>>({ data: null, loading: true, error: null });
  const [patients, setPatients] = useState<LoadState<{ patients: Patient[] }>>({ data: null, loading: true, error: null });
  const [metrics, setMetrics] = useState<LoadState<MetricsPayload>>({ data: null, loading: true, error: null });
  const [selectedPatientId, setSelectedPatientId] = useState<string | null>(null);
  const [step, setStep] = useState<number | null>(null);
  const [sensorDropout, setSensorDropout] = useState(false);
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [snapshotLoading, setSnapshotLoading] = useState(false);
  const [snapshotError, setSnapshotError] = useState<string | null>(null);
  const [snapshotRefresh, setSnapshotRefresh] = useState(0);
  const [scenario, setScenario] = useState<Scenario | null>(null);
  const [scenarioLoading, setScenarioLoading] = useState(false);
  const [scenarioError, setScenarioError] = useState<string | null>(null);
  const [activityMinutes, setActivityMinutes] = useState(0);
  const [mealCarbs, setMealCarbs] = useState(0);

  const snapshotRequestId = useRef(0);
  const scenarioRequestId = useRef(0);
  const scenarioController = useRef<AbortController | null>(null);

  const patientList = patients.data?.patients ?? EMPTY_PATIENTS;
  const selectedPatient = useMemo(
    () => patientList.find((patient) => patient.id === selectedPatientId) ?? null,
    [patientList, selectedPatientId],
  );

  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    setHealth({ data: null, loading: true, error: null });
    getHealth(controller.signal)
      .then((data) => {
        if (active) setHealth({ data, loading: false, error: null });
      })
      .catch((error: unknown) => {
        if (!active || isAbortError(error)) return;
        setHealth({ data: null, loading: false, error: errorMessage(error) });
      });
    return () => {
      active = false;
      controller.abort();
    };
  }, [workspaceRefresh]);

  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    setPatients({ data: null, loading: true, error: null });
    getPatients(controller.signal)
      .then((data) => {
        if (active) setPatients({ data, loading: false, error: null });
      })
      .catch((error: unknown) => {
        if (!active || isAbortError(error)) return;
        setPatients({ data: null, loading: false, error: errorMessage(error) });
      });
    return () => {
      active = false;
      controller.abort();
    };
  }, [workspaceRefresh]);

  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    setMetrics({ data: null, loading: true, error: null });
    getMetrics(controller.signal)
      .then((data) => {
        if (active) setMetrics({ data, loading: false, error: null });
      })
      .catch((error: unknown) => {
        if (!active || isAbortError(error)) return;
        setMetrics({ data: null, loading: false, error: errorMessage(error) });
      });
    return () => {
      active = false;
      controller.abort();
    };
  }, [workspaceRefresh]);

  useEffect(() => {
    if (patientList.length === 0) {
      setSelectedPatientId(null);
      setStep(null);
      return;
    }
    setSelectedPatientId((current) => (current && patientList.some((patient) => patient.id === current) ? current : patientList[0].id));
  }, [patientList]);

  useEffect(() => {
    if (!selectedPatient) {
      setStep(null);
      return;
    }
    setStep((current) => (current === null ? selectedPatient.default_step : clamp(current, selectedPatient.min_step, selectedPatient.max_step)));
  }, [selectedPatient]);

  useEffect(() => {
    const requestId = ++snapshotRequestId.current;
    if (!selectedPatientId || step === null) {
      setSnapshot(null);
      setSnapshotLoading(false);
      setSnapshotError(null);
      return;
    }
    const controller = new AbortController();
    setSnapshot(null);
    setSnapshotLoading(true);
    setSnapshotError(null);
    getSnapshot(selectedPatientId, step, sensorDropout, controller.signal)
      .then((data) => {
        if (requestId !== snapshotRequestId.current) return;
        setSnapshot(data);
        setSnapshotLoading(false);
      })
      .catch((error: unknown) => {
        if (isAbortError(error) || requestId !== snapshotRequestId.current) return;
        setSnapshotLoading(false);
        setSnapshotError(errorMessage(error));
      });
    return () => controller.abort();
  }, [selectedPatientId, sensorDropout, snapshotRefresh, step]);

  const resetScenario = useCallback(() => {
    scenarioRequestId.current += 1;
    scenarioController.current?.abort();
    scenarioController.current = null;
    setScenario(null);
    setScenarioLoading(false);
    setScenarioError(null);
    setActivityMinutes(0);
    setMealCarbs(0);
  }, []);

  useEffect(() => {
    resetScenario();
  }, [resetScenario, selectedPatientId, sensorDropout, step]);

  useEffect(() => () => {
    scenarioRequestId.current += 1;
    scenarioController.current?.abort();
  }, []);

  const handlePatientChange = (patientId: string) => {
    const nextPatient = patientList.find((patient) => patient.id === patientId);
    if (!nextPatient) return;
    setSelectedPatientId(nextPatient.id);
    setStep(nextPatient.default_step);
    resetScenario();
  };

  const handleStepChange = (nextStep: number) => {
    if (!selectedPatient) return;
    setStep(toReplayStep(nextStep, selectedPatient));
  };

  const handleReplay = () => {
    if (!selectedPatient || step === null || snapshotLoading || step >= selectedPatient.max_step) return;
    setStep(Math.min(selectedPatient.max_step, step + 5));
  };

  const handleDropoutChange = (enabled: boolean) => {
    setSensorDropout(enabled);
    resetScenario();
  };

  const retrySnapshot = () => setSnapshotRefresh((value) => value + 1);

  const handleScenarioRun = () => {
    if (!selectedPatientId || step === null || !snapshot || scenarioLoading) return;
    scenarioController.current?.abort();
    const controller = new AbortController();
    scenarioController.current = controller;
    const requestId = ++scenarioRequestId.current;
    setScenarioLoading(true);
    setScenarioError(null);
    simulate(
      selectedPatientId,
      {
        step,
        activity_minutes: clamp(activityMinutes, 0, 30),
        meal_carbs: clamp(mealCarbs, 0, 100),
        sensor_dropout: sensorDropout,
      },
      controller.signal,
    )
      .then((data) => {
        if (requestId !== scenarioRequestId.current) return;
        setScenario(data);
        setScenarioLoading(false);
        scenarioController.current = null;
      })
      .catch((error: unknown) => {
        if (isAbortError(error) || requestId !== scenarioRequestId.current) return;
        setScenarioLoading(false);
        setScenarioError(errorMessage(error));
        scenarioController.current = null;
      });
  };

  const refreshWorkspace = () => {
    resetScenario();
    setWorkspaceRefresh((value) => value + 1);
  };
  const replayDisabled = !selectedPatient || step === null || step >= selectedPatient.max_step || snapshotLoading;
  const canRunScenario = Boolean(selectedPatientId && step !== null && snapshot && !snapshotLoading);
  const apiReady = health.data ? health.data.status === 'ready' : health.error ? false : null;

  return (
    <div className="app-shell">
      <Sidebar mobileOpen={mobileOpen} onClose={() => setMobileOpen(false)} />
      <div className="app-main">
        <Header onMenu={() => setMobileOpen(true)} lastUpdated={snapshot?.timestamp ?? null} apiReady={apiReady} />
        <main className="main-content">
          <div className="research-ribbon" role="note" aria-label="Synthetic data and clinical-use warning">
            <div className="research-ribbon-title"><ShieldAlert size={16} aria-hidden="true" /><strong>SYNTHETIC RESEARCH</strong></div>
            <span>All records, streams, forecasts, and metrics are synthetic.</span>
            <strong className="research-ribbon-warning">NOT FOR CLINICAL USE</strong>
          </div>

          <section className="page-intro" aria-labelledby="page-title">
            <div>
              <div className="section-eyebrow">Clinician research workspace · longitudinal twin</div>
              <h2 id="page-title">Inspect the evidence before the estimate.</h2>
              <p>Replay a synthetic patient timeline, review observed signal quality, and compare forecast heads without turning model output into medical advice.</p>
            </div>
            <WorkspaceStatus health={health} patients={patients} snapshot={snapshot} />
          </section>

          <SetupNotice health={health.data} />
          {health.error && <Panel className="state-panel"><ErrorState message={health.error} onRetry={refreshWorkspace} /></Panel>}

          <Panel id="overview" className="control-panel">
            <SectionHeading
              eyebrow="Patient twin"
              title="Choose a synthetic record"
              description="The selected replay clock controls which observations are sent to the local API."
              action={<button className="button button-quiet" type="button" onClick={refreshWorkspace}><RefreshCw size={14} aria-hidden="true" /> Refresh API data</button>}
            />
            {patients.loading && <LoadingState label="Loading synthetic patient index" />}
            {patients.error && <ErrorState message={patients.error} onRetry={refreshWorkspace} />}
            {!patients.loading && !patients.error && patientList.length === 0 && <ErrorState message="No synthetic patients were returned. Build the local artifacts with scripts/train.sh, then retry." onRetry={refreshWorkspace} />}
            <PatientSelector
              patients={patientList}
              selectedPatient={selectedPatient}
              step={step}
              loading={snapshotLoading}
              replayDisabled={replayDisabled}
              onPatientChange={handlePatientChange}
              onStepChange={handleStepChange}
              onReplay={handleReplay}
              sensorDropout={sensorDropout}
              onSensorDropoutChange={handleDropoutChange}
            />
            {selectedPatient && (
              <div className="demographics-strip" aria-label="Selected patient demographics">
                <div><span>Diabetes duration</span><strong>{formatNumber(selectedPatient.diabetes_years)} years</strong></div>
                <div><span>Medications</span><strong>{selectedPatient.medications.length ? selectedPatient.medications.join(', ') : 'None returned'}</strong></div>
                <div><span>Evaluation split</span><strong>{selectedPatient.split || 'Unavailable'}</strong></div>
                <div><span>Replay range</span><strong>{formatNumber(selectedPatient.min_step)}–{formatNumber(selectedPatient.max_step)} steps</strong></div>
              </div>
            )}
          </Panel>

          {snapshotLoading && <Panel className="state-panel"><LoadingState label="Loading twin snapshot for this replay position" /></Panel>}
          {!snapshotLoading && snapshotError && <Panel className="state-panel"><ErrorState message={snapshotError} onRetry={retrySnapshot} /></Panel>}

          {!snapshotLoading && !snapshotError && snapshot && (
            <>
              <section className="snapshot-heading" aria-labelledby="snapshot-title">
                <div>
                  <div className="section-eyebrow">Snapshot · {formatDateTime(snapshot.timestamp)}</div>
                  <h2 id="snapshot-title">{snapshot.patient.name}<span> / {snapshot.patient.id}</span></h2>
                </div>
                <div className="snapshot-heading-meta">
                  <StatusPill tone={snapshot.status.data_quality === 'good' ? 'good' : snapshot.status.data_quality === 'degraded' ? 'warn' : 'danger'}>{snapshot.status.data_quality} signal</StatusPill>
                  <span>Replay step {formatNumber(snapshot.step)}</span>
                </div>
              </section>
              <CurrentSummary snapshot={snapshot} />
              <div className="dashboard-two-column">
                <HistoryPanel snapshot={snapshot} />
                <DriversPanel snapshot={snapshot} />
              </div>
              <ForecastPanel snapshot={snapshot} />
              <div className="dashboard-two-column dashboard-two-column-bottom">
                <ScenarioPanel
                  scenario={scenario}
                  loading={scenarioLoading}
                  error={scenarioError}
                  activityMinutes={activityMinutes}
                  mealCarbs={mealCarbs}
                  canRun={canRunScenario}
                  onActivityMinutesChange={(value) => setActivityMinutes(clamp(value, 0, 30))}
                  onMealCarbsChange={(value) => setMealCarbs(clamp(value, 0, 100))}
                  onRun={handleScenarioRun}
                  onReset={resetScenario}
                />
                <EvidencePanel snapshot={snapshot} />
              </div>
            </>
          )}

          <MetricsPanel metrics={metrics.data} loading={metrics.loading} error={metrics.error} onRetry={refreshWorkspace} />

          <footer className="app-footer">
            <div><AlertOctagon size={15} aria-hidden="true" /><strong>Research prototype</strong><span>Not a diagnostic device. No real patient data is transmitted.</span></div>
            <a href="#evaluation">View measured evaluation <ArrowUpRight size={14} aria-hidden="true" /></a>
          </footer>
        </main>
      </div>
    </div>
  );
}
