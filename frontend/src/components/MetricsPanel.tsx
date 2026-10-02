import { BarChart3, Braces, Database, Info, ListChecks } from 'lucide-react';
import type { MetricsPayload } from '../types';
import { asRecord, displayJson, formatNumber, metricKeyLabel } from '../utils';
import { EmptyState, ErrorState, LoadingState, Panel, SectionHeading, StatusPill } from './Primitives';

type MetricsPanelProps = {
  metrics: MetricsPayload | null;
  loading: boolean;
  error: string | null;
  onRetry: () => void;
};

type FlatMetric = { label: string; value: unknown };

function flatten(value: unknown, prefix: string, output: FlatMetric[], depth = 0): void {
  if (output.length >= 80) return;
  if (value === null || value === undefined) {
    output.push({ label: prefix, value: null });
    return;
  }
  if (typeof value !== 'object' || depth >= 3) {
    output.push({ label: prefix, value });
    return;
  }
  if (Array.isArray(value)) {
    if (value.length === 0) {
      output.push({ label: prefix, value: 'No rows' });
      return;
    }
    value.forEach((item, index) => flatten(item, `${prefix} ${index + 1}`, output, depth + 1));
    return;
  }
  Object.entries(value as Record<string, unknown>).forEach(([key, child]) => {
    flatten(child, prefix ? `${prefix} · ${metricKeyLabel(key)}` : metricKeyLabel(key), output, depth + 1);
  });
}

function metricValue(value: unknown): string {
  if (value === null || value === undefined) return 'Not measured';
  if (typeof value === 'number') return Number.isFinite(value) ? formatNumber(value, 4) : 'Not measured';
  if (typeof value === 'boolean') return value ? 'Yes' : 'No';
  if (typeof value === 'string') return value;
  return displayJson(value);
}

function topValue(metrics: MetricsPayload, key: string): unknown {
  return metrics[key];
}

export function MetricsPanel({ metrics, loading, error, onRetry }: MetricsPanelProps) {
  const rows: FlatMetric[] = [];
  if (metrics) {
    flatten(metrics.models ?? null, 'Models', rows);
    flatten(metrics.forecast ?? null, 'Forecast', rows);
  }
  const cohort = asRecord(metrics?.cohort);
  const cohortRows = cohort ? Object.entries(cohort).slice(0, 6) : [];
  const limitations = Array.isArray(metrics?.limitations) ? metrics.limitations : [];

  return (
    <Panel id="evaluation" className="metrics-panel">
      <SectionHeading
        eyebrow="Held-out evaluation"
        title="Measured metrics"
        description="Values are read from the local /api/metrics artifact; no alert performance is invented here."
        action={<StatusPill tone="neutral"><BarChart3 size={13} aria-hidden="true" /> API evidence</StatusPill>}
      />
      {loading && <LoadingState label="Loading measured evaluation" />}
      {!loading && error && <ErrorState message={error} onRetry={onRetry} />}
      {!loading && !error && !metrics && <EmptyState title="Metrics are unavailable" description="The API did not return an evaluation payload." />}
      {!loading && !error && metrics && (
        <>
          <div className="metrics-meta-grid">
            <div className="metrics-meta-card"><Database size={15} aria-hidden="true" /><span>Data mode</span><strong>{String(topValue(metrics, 'data_mode') ?? 'Unavailable')}</strong></div>
            <div className="metrics-meta-card"><Braces size={15} aria-hidden="true" /><span>Seed</span><strong>{metricValue(topValue(metrics, 'seed'))}</strong></div>
            <div className="metrics-meta-card"><ListChecks size={15} aria-hidden="true" /><span>Event definition</span><strong>{metricValue(topValue(metrics, 'event_definition'))}</strong></div>
          </div>
          {cohortRows.length > 0 && (
            <div className="cohort-strip">
              {cohortRows.map(([key, value]) => <div key={key}><span>{metricKeyLabel(key)}</span><strong>{metricValue(value)}</strong></div>)}
            </div>
          )}
          <div className="metrics-disclaimer"><Info size={15} aria-hidden="true" /><span>Null metric values mean the quantity was undefined or not measured. They are not zero performance.</span></div>
          {rows.length > 0 ? (
            <div className="metrics-table-wrap">
              <table className="data-table metrics-table">
                <caption className="sr-only">Measured model and forecast metrics</caption>
                <thead><tr><th scope="col">Metric</th><th scope="col">Returned value</th></tr></thead>
                <tbody>{rows.map((row, index) => <tr key={`${row.label}-${index}`}><td>{row.label}</td><td>{metricValue(row.value)}</td></tr>)}</tbody>
              </table>
            </div>
          ) : (
            <EmptyState title="No model result rows returned" description="Use the raw JSON below to inspect the flexible metrics payload." />
          )}
          {limitations.length > 0 && (
            <div className="limitations-box"><strong>Declared limitations</strong><ul>{limitations.map((item, index) => <li key={`${String(item)}-${index}`}>{typeof item === 'string' ? item : metricValue(item)}</li>)}</ul></div>
          )}
          <details className="raw-json">
            <summary>Show complete metrics JSON fallback</summary>
            <pre>{displayJson(metrics)}</pre>
          </details>
        </>
      )}
    </Panel>
  );
}
