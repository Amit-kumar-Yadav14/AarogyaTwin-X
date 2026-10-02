import { Activity, CircleHelp, HeartPulse, Info } from 'lucide-react';
import type { Snapshot } from '../types';
import { formatOptionalNumber } from '../utils';
import { EmptyState, Panel, SectionHeading, StatusPill } from './Primitives';

export function DriversPanel({ snapshot }: { snapshot: Snapshot }) {
  return (
    <Panel id="drivers" className="drivers-panel">
      <SectionHeading
        eyebrow="Context window"
        title="Observed drivers"
        description="Context surfaced by the API for review alongside the forecast."
        action={<StatusPill tone="neutral">Noncausal context</StatusPill>}
      />
      <div className="driver-disclaimer">
        <Info size={15} aria-hidden="true" />
        <span>These are observed context signals, not SHAP explanations, causal attributions, or treatment effects.</span>
      </div>
      {snapshot.drivers.length === 0 ? (
        <EmptyState title="No context drivers returned" description="The API did not provide context signals for this snapshot." />
      ) : (
        <div className="driver-list">
          {snapshot.drivers.map((driver, index) => {
            const icon = index % 3 === 0 ? Activity : index % 3 === 1 ? HeartPulse : CircleHelp;
            const Icon = icon;
            return (
              <article className="driver-row" key={`${driver.label}-${index}`}>
                <div className="driver-icon" aria-hidden="true"><Icon size={16} /></div>
                <div className="driver-copy">
                  <div className="driver-label">{driver.label || 'Unnamed signal'}</div>
                  <div className="driver-interpretation">{driver.interpretation || 'Interpretation unavailable'}</div>
                </div>
                <div className="driver-value">{formatOptionalNumber(driver.value, driver.unit || '', 1)}</div>
              </article>
            );
          })}
        </div>
      )}
    </Panel>
  );
}
