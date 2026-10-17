import { AlertTriangle, BookOpen, FileCheck2, LockKeyhole } from 'lucide-react';
import type { Snapshot } from '../types';
import { Panel, SectionHeading, StatusPill } from './Primitives';

export function EvidencePanel({ snapshot }: { snapshot: Snapshot }) {
  const provenance = [
    ['Data', snapshot.provenance.data],
    ['Model version', snapshot.provenance.model_version],
    ['Simulation version', snapshot.provenance.simulation_version],
    ['Calibration split', snapshot.provenance.calibration_split],
    ['Risk semantics', snapshot.provenance.risk_semantics],
  ];

  return (
    <Panel id="evidence" className="evidence-panel">
      <SectionHeading
        eyebrow="Traceability"
        title="Evidence brief"
        description="A deterministic summary assembled by the API for reproducible review."
        action={<StatusPill tone="violet"><FileCheck2 size={13} aria-hidden="true" /> Not LLM-generated</StatusPill>}
      />
      <div className="evidence-brief">
        <BookOpen size={18} aria-hidden="true" />
        <p>{snapshot.evidence_summary || 'No deterministic evidence summary was returned.'}</p>
      </div>
      <div className="evidence-note">
        <LockKeyhole size={14} aria-hidden="true" />
        <span>Interpretation is constrained to the returned observations, forecast heads, and project endpoint semantics.</span>
      </div>
      <div className="provenance-grid">
        {provenance.map(([label, value]) => (
          <div className="provenance-item" key={label}>
            <span>{label}</span>
            <strong>{value || 'Unavailable'}</strong>
          </div>
        ))}
      </div>
      {snapshot.provenance.explanation && (
        <div className="provenance-explanation"><strong>Explanation note</strong><p>{snapshot.provenance.explanation}</p></div>
      )}
      {snapshot.warnings.length > 0 && (
        <div className="evidence-warnings">
          <div className="warning-list-title"><AlertTriangle size={15} aria-hidden="true" /> Review before interpreting</div>
          <ul>{snapshot.warnings.map((warning, index) => <li key={`${warning}-${index}`}>{warning}</li>)}</ul>
        </div>
      )}
    </Panel>
  );
}
