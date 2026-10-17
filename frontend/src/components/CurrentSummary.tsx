import { Activity, Radio } from 'lucide-react';
import type { Snapshot } from '../types';
import { formatNumber, formatOptionalNumber, isFiniteNumber, qualityLabel, statusLabel } from '../utils';
import { MetricTile, StatusPill } from './Primitives';

export function CurrentSummary({ snapshot }: { snapshot: Snapshot }) {
  const qualityTone =
    snapshot.status.data_quality === 'good'
      ? 'good'
      : snapshot.status.data_quality === 'degraded'
        ? 'warn'
        : 'danger';
  const eventTone = snapshot.status.event === 'above_threshold' ? 'danger' : snapshot.status.event === 'at_risk' ? 'warn' : 'neutral';

  return (
    <div className="summary-layout">
      <div className="metric-grid">
        <MetricTile
          label="Current glucose"
          value={formatNumber(snapshot.current.glucose)}
          unit={snapshot.current.glucose === null ? undefined : 'mg/dL'}
          detail={snapshot.current.glucose === null ? 'No current reading' : 'Observed at replay clock'}
          tone="teal"
        />
        <MetricTile
          label="Glucose slope"
          value={formatOptionalNumber(snapshot.current.glucose_slope, 'mg/dL/min', 2)}
          detail="Observed trend, not a causal effect"
          tone="violet"
        />
        <MetricTile
          label="Heart rate"
          value={formatNumber(snapshot.current.heart_rate)}
          unit={snapshot.current.heart_rate === null ? undefined : 'bpm'}
          detail="Most recent available observation"
          tone="slate"
        />
        <MetricTile
          label="Steps · last 60 min"
          value={formatNumber(snapshot.current.steps_60m)}
          detail={`Sleep context: ${formatOptionalNumber(snapshot.current.sleep_hours, 'h', 1)}`}
          tone="amber"
        />
      </div>

      <div className="quality-card">
        <div className="quality-card-heading">
          <div>
            <div className="section-eyebrow">Signal integrity</div>
            <h3>Data quality</h3>
          </div>
          <StatusPill tone={qualityTone}>{qualityLabel(snapshot.status.data_quality)}</StatusPill>
        </div>
        <div className="quality-main-row">
          <div className="quality-ring" data-quality={snapshot.status.data_quality}>
            <Radio size={18} aria-hidden="true" />
          </div>
          <div>
            <strong>{snapshot.status.sensor_dropout ? 'CGM dropout active' : 'CGM stream connected'}</strong>
            <p>
              {snapshot.status.cgm_age_minutes === null
                ? 'CGM age unavailable'
                : `${formatNumber(snapshot.status.cgm_age_minutes)} min since latest CGM observation`}
            </p>
          </div>
        </div>
        <div className="quality-details">
          <div>
            <span>Missingness · 60 min</span>
            <strong>{formatOptionalNumber(isFiniteNumber(snapshot.status.missing_fraction_60m) ? snapshot.status.missing_fraction_60m * 100 : null, '%', 1)}</strong>
          </div>
          <div>
            <span>Twin state</span>
            <strong>{snapshot.status.twin || 'Unavailable'}</strong>
          </div>
          <div>
            <span>Event state</span>
            <strong>
              <StatusPill tone={eventTone}>{statusLabel(snapshot.status.event)}</StatusPill>
            </strong>
          </div>
        </div>
        {snapshot.status.sensor_dropout && (
          <div className="inline-warning">
            <Activity size={14} aria-hidden="true" />
            The latest 30 minutes of CGM observations are intentionally withheld from this snapshot.
          </div>
        )}
      </div>
    </div>
  );
}
