import type { ForecastPoint, Patient, Snapshot } from './types';

export function isFiniteNumber(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value);
}

export function formatNumber(value: number | null | undefined, digits = 0): string {
  if (!isFiniteNumber(value)) return 'Unavailable';
  return new Intl.NumberFormat('en-US', {
    maximumFractionDigits: digits,
    minimumFractionDigits: digits,
  }).format(value);
}

export function formatOptionalNumber(
  value: number | null | undefined,
  unit = '',
  digits = 0,
): string {
  const formatted = formatNumber(value, digits);
  return formatted === 'Unavailable' ? formatted : `${formatted}${unit ? ` ${unit}` : ''}`;
}

export function formatPercent(value: number | null | undefined, digits = 0): string {
  if (!isFiniteNumber(value)) return 'Unavailable';
  return `${formatNumber(value * 100, digits)}%`;
}

export function formatTimestamp(timestamp: string | null | undefined, withDate = false): string {
  if (!timestamp) return 'Timestamp unavailable';
  const parsed = new Date(timestamp);
  if (Number.isNaN(parsed.getTime())) return 'Timestamp unavailable';
  return new Intl.DateTimeFormat('en-US', {
    month: withDate ? 'short' : undefined,
    day: withDate ? 'numeric' : undefined,
    hour: 'numeric',
    minute: '2-digit',
  }).format(parsed);
}

export function formatDateTime(timestamp: string | null | undefined): string {
  if (!timestamp) return 'Timestamp unavailable';
  const parsed = new Date(timestamp);
  if (Number.isNaN(parsed.getTime())) return 'Timestamp unavailable';
  return new Intl.DateTimeFormat('en-US', {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(parsed);
}

export function formatStepRange(patient: Patient | null, step: number | null): string {
  if (!patient || step === null) return 'Replay position unavailable';
  return `Step ${formatNumber(step)} · ${formatTimestamp(
    new Date(Date.UTC(2026, 0, 1, 0, 0, step)).toISOString(),
  )}`;
}

export function patientInitials(name: string): string {
  const initials = name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? '')
    .join('');
  return initials || 'PT';
}

export function statusLabel(status: Snapshot['status']['event']): string {
  switch (status) {
    case 'at_risk':
      return 'At risk';
    case 'above_threshold':
      return 'Above threshold';
    default:
      return 'Unknown';
  }
}

export function qualityLabel(quality: Snapshot['status']['data_quality']): string {
  switch (quality) {
    case 'good':
      return 'Good';
    case 'degraded':
      return 'Degraded';
    default:
      return 'Insufficient';
  }
}

export function shortUnit(unit: string): string {
  return unit.trim();
}

export function asRecord(value: unknown): Record<string, unknown> | null {
  return typeof value === 'object' && value !== null ? (value as Record<string, unknown>) : null;
}

export function displayJson(value: unknown): string {
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return 'The API returned a value that could not be rendered.';
  }
}

export function hasMeaningfulObject(value: unknown): value is Record<string, unknown> {
  const record = asRecord(value);
  return record !== null && Object.keys(record).length > 0;
}

export function forecastChartData(points: ForecastPoint[]) {
  return points
    .filter(
      (point) =>
        isFiniteNumber(point.minutes_ahead) &&
        isFiniteNumber(point.glucose) &&
        isFiniteNumber(point.lower) &&
        isFiniteNumber(point.upper),
    )
    .map((point) => ({
      ...point,
      minutes: point.minutes_ahead,
      band: Math.max(0, point.upper - point.lower),
    }));
}

export function historyChartData(snapshot: Snapshot) {
  return snapshot.history
    .map((point) => ({
      ...point,
      time: formatTimestamp(point.timestamp),
      glucoseValue: isFiniteNumber(point.glucose) ? point.glucose : null,
    }))
    .filter((point) => point.glucoseValue !== null);
}

export function metricKeyLabel(key: string): string {
  return key
    .replace(/[_-]+/g, ' ')
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}
