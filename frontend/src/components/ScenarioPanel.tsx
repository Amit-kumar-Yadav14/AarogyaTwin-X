import {
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { AlertTriangle, Beaker, Info, RotateCcw, SlidersHorizontal } from 'lucide-react';
import type { ForecastPoint, Scenario } from '../types';
import { formatDateTime, formatNumber, isFiniteNumber } from '../utils';
import { EmptyState, ErrorState, LoadingState, Panel, SectionHeading, StatusPill } from './Primitives';

type ScenarioPanelProps = {
  scenario: Scenario | null;
  loading: boolean;
  error: string | null;
  activityMinutes: number;
  mealCarbs: number;
  canRun: boolean;
  onActivityMinutesChange: (value: number) => void;
  onMealCarbsChange: (value: number) => void;
  onRun: () => void;
  onReset: () => void;
};

type ScenarioChartPoint = {
  minutes: number;
  baseline: number | null;
  baselineLower: number | null;
  baselineUpper: number | null;
  scenario: number | null;
  scenarioLower: number | null;
  scenarioUpper: number | null;
  timestamp: string;
};

function pointMap(points: ForecastPoint[]): Map<number, ForecastPoint> {
  return new Map(points.filter((point) => isFiniteNumber(point.minutes_ahead)).map((point) => [point.minutes_ahead, point]));
}

function chartRows(scenario: Scenario): ScenarioChartPoint[] {
  const baseline = pointMap(scenario.baseline);
  const simulated = pointMap(scenario.scenario);
  const horizons = [...new Set([...baseline.keys(), ...simulated.keys()])].sort((left, right) => left - right);
  return horizons.map((minutes) => {
    const baselinePoint = baseline.get(minutes);
    const scenarioPoint = simulated.get(minutes);
    return {
      minutes,
      baseline: baselinePoint && isFiniteNumber(baselinePoint.glucose) ? baselinePoint.glucose : null,
      baselineLower: baselinePoint && isFiniteNumber(baselinePoint.lower) ? baselinePoint.lower : null,
      baselineUpper: baselinePoint && isFiniteNumber(baselinePoint.upper) ? baselinePoint.upper : null,
      scenario: scenarioPoint && isFiniteNumber(scenarioPoint.glucose) ? scenarioPoint.glucose : null,
      scenarioLower: scenarioPoint && isFiniteNumber(scenarioPoint.lower) ? scenarioPoint.lower : null,
      scenarioUpper: scenarioPoint && isFiniteNumber(scenarioPoint.upper) ? scenarioPoint.upper : null,
      timestamp: scenarioPoint?.timestamp || baselinePoint?.timestamp || '',
    };
  });
}

function ScenarioTooltip({ active, payload, label }: { active?: boolean; payload?: Array<{ payload?: ScenarioChartPoint }>; label?: number }) {
  if (!active || !payload?.length || !payload[0]?.payload) return null;
  const row = payload[0].payload;
  return (
    <div className="chart-tooltip">
      <strong>{label} min ahead</strong>
      <span>Baseline {row.baseline === null ? 'Unavailable' : `${formatNumber(row.baseline)} mg/dL`}</span>
      <span>Scenario {row.scenario === null ? 'Unavailable' : `${formatNumber(row.scenario)} mg/dL`}</span>
    </div>
  );
}

function RangeText({ lower, upper }: { lower: number | null; upper: number | null }) {
  if (!isFiniteNumber(lower) || !isFiniteNumber(upper)) return <>Unavailable</>;
  return <>{formatNumber(lower)}–{formatNumber(upper)} mg/dL</>;
}

export function ScenarioPanel({
  scenario,
  loading,
  error,
  activityMinutes,
  mealCarbs,
  canRun,
  onActivityMinutesChange,
  onMealCarbsChange,
  onRun,
  onReset,
}: ScenarioPanelProps) {
  const rows = scenario ? chartRows(scenario) : [];

  return (
    <Panel id="sandbox" className="scenario-panel">
      <SectionHeading
        eyebrow="Sandbox"
        title="Scenario comparison"
        description="Compare an assumption-based input change with the current twin snapshot."
        action={<StatusPill tone="violet"><Beaker size={13} aria-hidden="true" /> Unvalidated sandbox</StatusPill>}
      />

      <div className="scenario-warning">
        <AlertTriangle size={17} aria-hidden="true" />
        <div>
          <strong>Not medical advice · not a treatment estimate</strong>
          <p>Activity and carbohydrate inputs are bounded sandbox assumptions. Do not modify medication or use this comparison to make care decisions.</p>
        </div>
      </div>

      <div className="scenario-controls">
        <div className="scenario-field">
          <div className="scenario-field-label-row">
            <label htmlFor="scenario-activity"><SlidersHorizontal size={14} aria-hidden="true" /> Activity assumption</label>
            <output htmlFor="scenario-activity">{activityMinutes} min</output>
          </div>
          <input
            id="scenario-activity"
            type="range"
            min={0}
            max={30}
            step={1}
            value={activityMinutes}
            disabled={loading}
            onChange={(event) => onActivityMinutesChange(Number(event.target.value))}
            aria-describedby="scenario-input-limit"
          />
          <div className="range-endpoints"><span>0 min</span><span>30 min</span></div>
        </div>
        <div className="scenario-field">
          <div className="scenario-field-label-row">
            <label htmlFor="scenario-carbs"><SlidersHorizontal size={14} aria-hidden="true" /> Carbohydrate assumption</label>
            <output htmlFor="scenario-carbs">{mealCarbs} g</output>
          </div>
          <input
            id="scenario-carbs"
            type="range"
            min={0}
            max={100}
            step={1}
            value={mealCarbs}
            disabled={loading}
            onChange={(event) => onMealCarbsChange(Number(event.target.value))}
            aria-describedby="scenario-input-limit"
          />
          <div className="range-endpoints"><span>0 g</span><span>100 g</span></div>
        </div>
        <div className="scenario-actions">
          <button className="button button-primary" type="button" onClick={onRun} disabled={!canRun || loading}>
            <Beaker size={15} aria-hidden="true" />
            {loading ? 'Running simulation…' : 'Run comparison'}
          </button>
          <button className="button button-quiet" type="button" onClick={onReset}>
            <RotateCcw size={14} aria-hidden="true" /> Reset
          </button>
        </div>
      </div>
      <p className="scenario-input-limit" id="scenario-input-limit">
        Limits are 0–30 minutes and 0–100 g for this research sandbox only; they are not recommendations.
      </p>

      {error && <ErrorState message={error} onRetry={onRun} />}
      {loading && !scenario && <LoadingState label="Running assumption-based comparison" />}
      {!loading && !error && !scenario && (
        <EmptyState title="No scenario run yet" description="Choose bounded assumptions and run the local API comparison to populate this view." />
      )}

      {scenario && (
        <div className="scenario-result" aria-live="polite">
          <div className="scenario-result-heading">
            <div>
              <h3>Baseline versus assumption-based scenario</h3>
              <p>Scenario request: {scenario.activity_minutes} min activity · {scenario.meal_carbs} g carbohydrate</p>
            </div>
            <StatusPill tone="warn">Bands not calibrated for interventions</StatusPill>
          </div>
          {rows.length === 0 ? (
            <EmptyState title="No scenario forecast points returned" description="The API returned the scenario envelope without usable horizon points." />
          ) : (
            <>
              <div className="scenario-chart" role="img" aria-label="Baseline and assumption-based scenario forecast comparison">
                <ResponsiveContainer width="100%" height={260}>
                  <ComposedChart data={rows} margin={{ top: 12, right: 12, bottom: 4, left: 0 }}>
                    <CartesianGrid stroke="#e8edf4" vertical={false} />
                    <XAxis dataKey="minutes" tickLine={false} axisLine={false} tick={{ fill: '#718096', fontSize: 12 }} tickFormatter={(value: number) => `${value}m`} />
                    <YAxis tickLine={false} axisLine={false} width={42} tick={{ fill: '#718096', fontSize: 12 }} tickFormatter={(value: number) => `${value}`} />
                    <Tooltip content={<ScenarioTooltip />} />
                    <Line type="linear" dataKey="baseline" name="Baseline" stroke="#159b9a" strokeWidth={2.8} dot={{ r: 4, fill: '#fff', stroke: '#159b9a', strokeWidth: 2 }} isAnimationActive={false} />
                    <Line type="linear" dataKey="scenario" name="Scenario" stroke="#7667e8" strokeWidth={2.8} dot={{ r: 4, fill: '#fff', stroke: '#7667e8', strokeWidth: 2 }} isAnimationActive={false} />
                  </ComposedChart>
                </ResponsiveContainer>
              </div>
              <div className="chart-legend scenario-legend" aria-label="Scenario chart legend">
                <span><i className="legend-swatch legend-line-teal" />Baseline</span>
                <span><i className="legend-swatch legend-line-violet" />Assumption-based scenario</span>
              </div>
              <div className="scenario-band-note"><Info size={13} aria-hidden="true" /> Interval ranges are shown in the table below. Scenario bands are inherited illustrative bounds, not calibrated intervention uncertainty.</div>
              <div className="scenario-table-wrap">
                <table className="data-table scenario-table">
                  <caption className="sr-only">Baseline and scenario forecast ranges</caption>
                  <thead><tr><th scope="col">Horizon</th><th scope="col">Baseline</th><th scope="col">Baseline interval</th><th scope="col">Scenario</th><th scope="col">Scenario interval</th></tr></thead>
                  <tbody>
                    {rows.map((row) => (
                      <tr key={row.minutes}>
                        <td>{row.minutes} min</td>
                        <td>{row.baseline === null ? 'Unavailable' : `${formatNumber(row.baseline)} mg/dL`}</td>
                        <td><RangeText lower={row.baselineLower} upper={row.baselineUpper} /></td>
                        <td>{row.scenario === null ? 'Unavailable' : `${formatNumber(row.scenario)} mg/dL`}</td>
                        <td><RangeText lower={row.scenarioLower} upper={row.scenarioUpper} /></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="scenario-assumptions">
                <div className="scenario-assumptions-title"><Info size={14} aria-hidden="true" /> API-returned assumptions</div>
                {scenario.assumptions.length > 0 ? <ul>{scenario.assumptions.map((assumption, index) => <li key={`${assumption}-${index}`}>{assumption}</li>)}</ul> : <p>No assumptions were returned.</p>}
                <p className="scenario-disclaimer">{scenario.disclaimer || 'Scenario bands are inherited illustrative bands, not calibrated intervention uncertainty.'}</p>
              </div>
              {rows[0]?.timestamp && <div className="scenario-timestamp">Scenario horizon timestamps begin {formatDateTime(rows[0].timestamp)}.</div>}
            </>
          )}
        </div>
      )}
    </Panel>
  );
}
