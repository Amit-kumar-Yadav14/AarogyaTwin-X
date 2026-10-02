import { ChevronDown, Clock3, Database, Play, UserRound } from 'lucide-react';
import type { Patient } from '../types';
import { formatNumber, formatOptionalNumber, patientInitials } from '../utils';

type PatientSelectorProps = {
  patients: Patient[];
  selectedPatient: Patient | null;
  step: number | null;
  loading: boolean;
  replayDisabled: boolean;
  onPatientChange: (patientId: string) => void;
  onStepChange: (step: number) => void;
  onReplay: () => void;
  sensorDropout: boolean;
  onSensorDropoutChange: (enabled: boolean) => void;
};

export function PatientSelector({
  patients,
  selectedPatient,
  step,
  loading,
  replayDisabled,
  onPatientChange,
  onStepChange,
  onReplay,
  sensorDropout,
  onSensorDropoutChange,
}: PatientSelectorProps) {
  return (
    <div className="workspace-controls">
      <div className="patient-picker-block">
        <label className="field-label" htmlFor="patient-select">
          <UserRound size={15} aria-hidden="true" />
          Synthetic patient
        </label>
        <div className="select-wrap">
          <select
            id="patient-select"
            value={selectedPatient?.id ?? ''}
            onChange={(event) => onPatientChange(event.target.value)}
            disabled={patients.length === 0}
          >
            <option value="" disabled>
              {patients.length ? 'Select a patient' : 'No patients available'}
            </option>
            {patients.map((patient) => (
              <option key={patient.id} value={patient.id}>
                {patient.name} · {patient.id}
              </option>
            ))}
          </select>
          <ChevronDown size={16} aria-hidden="true" />
        </div>
      </div>

      {selectedPatient ? (
        <div className="patient-identity">
          <div className="avatar" aria-hidden="true">
            {patientInitials(selectedPatient.name)}
          </div>
          <div>
            <div className="patient-name">{selectedPatient.name}</div>
            <div className="patient-meta">
              {selectedPatient.age} years · {selectedPatient.sex} · BMI {formatNumber(selectedPatient.bmi, 1)}
            </div>
          </div>
          <div className="patient-tags">
            <span>{selectedPatient.split} split</span>
            <span>HbA1c {formatOptionalNumber(selectedPatient.hba1c, '%', 1)}</span>
          </div>
        </div>
      ) : (
        <div className="patient-identity patient-identity-empty">
          <div className="avatar avatar-muted" aria-hidden="true">
            —
          </div>
          <div>
            <div className="patient-name">Choose a synthetic record</div>
            <div className="patient-meta">Patient demographics will appear here.</div>
          </div>
        </div>
      )}

      <div className="replay-controls">
        <div className="clock-label-row">
          <label className="field-label" htmlFor="replay-step">
            <Clock3 size={15} aria-hidden="true" />
            Replay clock
          </label>
          <span className="step-readout">
            {step === null ? 'Unavailable' : `Step ${formatNumber(step)} / ${formatNumber(selectedPatient?.max_step)}`}
          </span>
        </div>
        <div className="slider-row">
          <input
            id="replay-step"
            type="range"
            min={selectedPatient?.min_step ?? 0}
            max={selectedPatient?.max_step ?? 0}
            step={5}
            value={step ?? selectedPatient?.min_step ?? 0}
            onChange={(event) => onStepChange(Number(event.target.value))}
            disabled={!selectedPatient || loading}
            aria-label="Replay position in five-minute steps"
          />
          <button
            className="button button-primary replay-button"
            type="button"
            onClick={onReplay}
            disabled={replayDisabled}
            title={replayDisabled ? 'Replay is at the patient boundary or loading' : 'Advance one five-minute step'}
          >
            <Play size={14} fill="currentColor" aria-hidden="true" />
            Replay +5 min
          </button>
        </div>
        <div className="slider-endpoints" aria-hidden="true">
          <span>{selectedPatient ? `Start ${formatNumber(selectedPatient.min_step)}` : 'Start'}</span>
          <span>{selectedPatient ? `End ${formatNumber(selectedPatient.max_step)}` : 'End'}</span>
        </div>
      </div>

      <label className={`toggle-control ${sensorDropout ? 'is-on' : ''}`}>
        <input
          type="checkbox"
          checked={sensorDropout}
          onChange={(event) => onSensorDropoutChange(event.target.checked)}
        />
        <span className="toggle-track" aria-hidden="true">
          <span />
        </span>
        <span className="toggle-copy">
          <strong>Simulate CGM dropout</strong>
          <small>
            <Database size={12} aria-hidden="true" />
            Removes the latest 30 minutes from model input
          </small>
        </span>
      </label>
    </div>
  );
}
