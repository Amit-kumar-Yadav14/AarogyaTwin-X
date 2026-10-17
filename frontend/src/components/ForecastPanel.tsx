import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { AlertTriangle, Info, ShieldAlert, Target } from 'lucide-react';
import type { ForecastPoint, Snapshot } from '../types';
import { formatDateTime, formatNumber, formatOptionalNumber, formatPercent, isFiniteNumber } from '../utils';
import { EmptyState, MetricTile, Panel, SectionHeading, StatusPill } from './Primitives';

type ChartPoint = ForecastPoint & {
  minutes: number;
  band: number;
};

function validForecast(points: ForecastPoint[]): ChartPoint[] {
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
    }))
    .sort((left, right) => left.minutes - right.minutes);
}

function riskCopy(snapshot: Snapshot): { value: string; detail: string; tone: 'good' | 'warn' | 'danger' | 'neutral' } {
  const { predictions } = snapshot;
  if (snapshot.status.event === 'above_threshold') {
    return {
      value: 'Not estimable',
      detail: 'The anchor is already above 180 mg/dL; no new-event probability is assigned.',
      tone: 'danger',
    };
  }
  if (predictions.risk_120m === null || !isFiniteNumber(predictions.risk_120m)) {
    return {
      value: 'Not estimable',
      detail: predictions.reason || 'The model did not provide a 120-minute event estimate.',
      tone: 'neutral',
    };
  }
  return {
    value: formatPercent(predictions.risk_120m, 1),
    detail: 'Estimated new sustained high-glucose event within 120 minutes.',
    tone: 'neutral',
  };
}

function ForecastTooltip({ active, payload, label }: { active?: boolean; payload?: Array<{ payload?: ChartPoint }>; label?: number }) {
  if (!active || !payload?.length || !payload[0]?.payload) return null;
  const point = payload[0].payload;
  return (
    <div className="chart-tooltip">
      <strong>{label} min ahead</strong>
      <span>Forecast {formatNumber(point.glucose)} mg/dL</span>
      <span>Interval {formatNumber(point.lower)}–{formatNumber(point.upper)} mg/dL</span>
    </div>
  );
}

function HorizonCard({ point, expectedHorizon }: { point: ChartPoint | undefined; expectedHorizon: number }) {
  return (
    <article className="horizon-card">
      <div className="horizon-card-topline">
        <span className="horizon-label">{expectedHorizon} min</span>
        {point ? <StatusPill tone="violet">Calibrated head</StatusPill> : <StatusPill>Unavailable</StatusPill>}
      </div>
      {point ? (
        <>
          <div className="horizon-value">{formatNumber(point.glucose)} <small>mg/dL</small></div>
          <div className="horizon-range">Interval {formatNumber(point.lower)}–{formatNumber(point.upper)} mg/dL</div>
          <div className="horizon-time">{formatDateTime(point.timestamp)}</div>
        </>
      ) : (
        <>
          <div className="horizon-value horizon-value-muted">Unavailable</div>
          <div className="horizon-range">No calibrated point returned</div>
          <div className="horizon-time">Estimates remain null</div>
        </>
      )}
    </article>
  );
}

export function ForecastPanel({ snapshot }: { snapshot: Snapshot }) {
  const chartData = validForecast(snapshot.forecast);
  const pointsByHorizon = new Map(chartData.map((point) => [point.minutes_ahead, point]));
  const risk = riskCopy(snapshot);
  const yValues = chartData.flatMap((point) => [point.lower, point.upper]);
  const yDomain: [number | 'auto', number | 'auto'] = yValues.length
    ? [Math.floor(Math.min(180, ...yValues) / 10) * 10 - 10, Math.ceil(Math.max(180, ...yValues) / 10) * 10 + 10]
    : ['auto', 'auto'];

  return (
    <Panel id="forecast" className="forecast-panel">
      <SectionHeading
        eyebrow="Forward view"
        title="Glucose forecast"
        description="Three calibrated horizon heads with an illustrative interval band."
        action={
          <div className="heading-badges">
            <StatusPill tone={snapshot.predictions.available ? 'good' : 'neutral'}>
              {snapshot.predictions.available ? 'Prediction available' : 'Prediction withheld'}
            </StatusPill>
            {snapshot.predictions.personalized && <StatusPill tone="violet">Personalized</StatusPill>}
          </div>
        }
      />

      <div className="forecast-metrics">
        <MetricTile
          label="120 min incident risk"
          value={risk.value}
          detail={risk.detail}
          tone={risk.tone === 'danger' ? 'amber' : risk.tone === 'warn' ? 'violet' : 'teal'}
        />
        <MetricTile
          label="Sampled peak"
          value={formatOptionalNumber(snapshot.predictions.predicted_peak, 'mg/dL')}
          detail="Maximum of sampled 30/60/120-minute heads; not a guaranteed future peak."
          tone="violet"
        />
        <MetricTile
          label="Interval target"
          value={formatPercent(snapshot.predictions.interval_coverage_target, 0)}
          detail={snapshot.predictions.interval_method || 'Method unavailable'}
          tone="slate"
        />
      </div>

      {!snapshot.predictions.available || chartData.length === 0 ? (
        <EmptyState
          title="Forecast is not available at this replay position"
          description={
            snapshot.predictions.reason ||
            'The API returned no calibrated forecast points. Current observations may still be available.'
          }
        />
      ) : (
        <>
          <div className="forecast-chart-wrap">
            <div className="chart-heading-row">
              <div>
                <h3>Forecast heads and interval</h3>
                <p>Threshold reference: strictly above 180 mg/dL.</p>
              </div>
              <div className="chart-legend" aria-label="Forecast chart legend">
                <span><i className="legend-swatch legend-line-teal" />Forecast head</span>
                <span><i className="legend-swatch legend-band" />Interval</span>
                <span><i className="legend-swatch legend-line-threshold" />180 threshold</span>
              </div>
            </div>
            <div className="chart-canvas" role="img" aria-label="Glucose forecast at 30, 60, and 120 minutes with interval bounds">
              <ResponsiveContainer width="100%" height={290}>
                <ComposedChart data={chartData} margin={{ top: 12, right: 16, bottom: 4, left: 0 }}>
                  <defs>
                    <linearGradient id="forecastBand" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#7667e8" stopOpacity={0.24} />
                      <stop offset="100%" stopColor="#7667e8" stopOpacity={0.06} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid stroke="#e8edf4" vertical={false} />
                  <XAxis
                    dataKey="minutes"
                    tickLine={false}
                    axisLine={false}
                    tick={{ fill: '#718096', fontSize: 12 }}
                    tickFormatter={(value: number) => `${value}m`}
                  />
                  <YAxis
                    domain={yDomain}
                    tickLine={false}
                    axisLine={false}
                    width={42}
                    tick={{ fill: '#718096', fontSize: 12 }}
                    tickFormatter={(value: number) => `${value}`}
                  />
                  <Tooltip content={<ForecastTooltip />} />
                  <ReferenceLine
                    y={180}
                    stroke="#d58a36"
                    strokeDasharray="5 5"
                    label={{ value: '180', position: 'insideTopRight', fill: '#a8671f', fontSize: 11 }}
                  />
                  <Area type="linear" dataKey="lower" stackId="interval" stroke="none" fill="transparent" isAnimationActive={false} />
                  <Area type="linear" dataKey="band" stackId="interval" stroke="none" fill="url(#forecastBand)" isAnimationActive={false} />
                  <Line
                    type="linear"
                    dataKey="glucose"
                    stroke="#159b9a"
                    strokeWidth={3}
                    dot={{ r: 5, fill: '#ffffff', stroke: '#159b9a', strokeWidth: 3 }}
                    activeDot={{ r: 7, fill: '#159b9a', stroke: '#ffffff', strokeWidth: 2 }}
                    isAnimationActive={false}
                  />
                </ComposedChart>
              </ResponsiveContainer>
            </div>
            <div className="chart-footnote">
              <Info size={14} aria-hidden="true" />
              <span>Only the 30, 60, and 120-minute heads are calibrated. Lines between heads are visual interpolation, not independently calibrated forecasts.</span>
            </div>
          </div>

          <div className="horizon-grid" aria-label="Forecast horizon details">
            {[30, 60, 120].map((horizon) => (
              <HorizonCard key={horizon} expectedHorizon={horizon} point={pointsByHorizon.get(horizon)} />
            ))}
          </div>
        </>
      )}

      <div className="forecast-explanation">
        <div className="explanation-icon" aria-hidden="true"><Target size={18} /></div>
        <div>
          <strong>How to read this view</strong>
          <p>
            The point estimate is the model head at each named horizon. The shaded interval communicates the returned range, while the connecting line helps compare direction only. It does not create extra forecast points.
          </p>
        </div>
        <div className="risk-definition">
          <ShieldAlert size={15} aria-hidden="true" />
          <span>Risk is a project endpoint for a new sustained episode; an anchor already above threshold is not assigned a new-event probability.</span>
        </div>
      </div>

      {snapshot.warnings.length > 0 && (
        <div className="warning-list" role="note">
          <div className="warning-list-title"><AlertTriangle size={15} aria-hidden="true" /> Snapshot warnings</div>
          <ul>
            {snapshot.warnings.map((warning, index) => <li key={`${warning}-${index}`}>{warning}</li>)}
          </ul>
        </div>
      )}
    </Panel>
  );
}
