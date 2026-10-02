import type { ReactNode } from 'react';
import { AlertCircle, CheckCircle2, LoaderCircle, RefreshCw } from 'lucide-react';

export function Panel({
  children,
  className = '',
  id,
}: {
  children: ReactNode;
  className?: string;
  id?: string;
}) {
  return (
    <section id={id} className={`panel ${className}`}>
      {children}
    </section>
  );
}

export function SectionHeading({
  eyebrow,
  title,
  description,
  action,
}: {
  eyebrow?: string;
  title: string;
  description?: string;
  action?: ReactNode;
}) {
  return (
    <div className="section-heading">
      <div>
        {eyebrow && <div className="section-eyebrow">{eyebrow}</div>}
        <h2>{title}</h2>
        {description && <p>{description}</p>}
      </div>
      {action && <div className="section-heading-action">{action}</div>}
    </div>
  );
}

export function StatusPill({
  children,
  tone = 'neutral',
}: {
  children: ReactNode;
  tone?: 'good' | 'warn' | 'danger' | 'neutral' | 'violet';
}) {
  return <span className={`status-pill status-pill-${tone}`}>{children}</span>;
}

export function LoadingState({ label = 'Loading data' }: { label?: string }) {
  return (
    <div className="state-block state-loading" role="status" aria-live="polite">
      <LoaderCircle className="spin" size={20} aria-hidden="true" />
      <span>{label}</span>
    </div>
  );
}

export function ErrorState({
  message,
  onRetry,
}: {
  message: string;
  onRetry?: () => void;
}) {
  return (
    <div className="state-block state-error" role="alert">
      <AlertCircle size={20} aria-hidden="true" />
      <div>
        <strong>Could not load this view</strong>
        <p>{message}</p>
        {onRetry && (
          <button className="button button-quiet" type="button" onClick={onRetry}>
            <RefreshCw size={14} aria-hidden="true" />
            Retry
          </button>
        )}
      </div>
    </div>
  );
}

export function EmptyState({ title, description }: { title: string; description: string }) {
  return (
    <div className="state-block state-empty">
      <CheckCircle2 size={20} aria-hidden="true" />
      <div>
        <strong>{title}</strong>
        <p>{description}</p>
      </div>
    </div>
  );
}

export function MetricTile({
  label,
  value,
  unit,
  detail,
  tone = 'teal',
}: {
  label: string;
  value: string;
  unit?: string;
  detail?: string;
  tone?: 'teal' | 'violet' | 'slate' | 'amber';
}) {
  return (
    <div className={`metric-tile metric-tile-${tone}`}>
      <div className="metric-label">{label}</div>
      <div className="metric-value">
        {value}
        {unit && <span>{unit}</span>}
      </div>
      {detail && <div className="metric-detail">{detail}</div>}
    </div>
  );
}
