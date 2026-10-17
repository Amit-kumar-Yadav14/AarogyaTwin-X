import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { Clock3, Database, Eye } from 'lucide-react';
import type { Snapshot } from '../types';
import { formatNumber, formatTimestamp, isFiniteNumber } from '../utils';
import { EmptyState, Panel, SectionHeading } from './Primitives';

export function HistoryPanel({ snapshot }: { snapshot: Snapshot }) {
  const chartData = snapshot.history.map((point) => ({
    ...point,
    time: formatTimestamp(point.timestamp),
    glucoseValue: isFiniteNumber(point.glucose) ? point.glucose : null,
  }));
  const recent = snapshot.history.slice(-8).reverse();

  return (
    <Panel id="history" className="history-panel">
      <SectionHeading
        eyebrow="Observed stream"
        title="Replay history"
        description="Only observations available at the selected replay clock are shown."
        action={<span className="section-chip"><Clock3 size={14} aria-hidden="true" /> Step {formatNumber(snapshot.step)}</span>}
      />
      {chartData.length === 0 ? (
        <EmptyState title="No history returned" description="The API did not return observed records for this replay position." />
      ) : (
        <>
          <div className="history-chart" role="img" aria-label="Observed glucose history chart">
            <ResponsiveContainer width="100%" height={218}>
              <LineChart data={chartData} margin={{ top: 8, right: 12, bottom: 4, left: -16 }}>
                <CartesianGrid stroke="#edf1f6" vertical={false} />
                <XAxis dataKey="time" tickLine={false} axisLine={false} hide />
                <YAxis
                  tickLine={false}
                  axisLine={false}
                  width={48}
                  tick={{ fill: '#8390a3', fontSize: 11 }}
                  tickFormatter={(value: number) => `${value}`}
                />
                <Tooltip
                  formatter={(value: unknown) => [typeof value === 'number' && Number.isFinite(value) ? `${formatNumber(value)} mg/dL` : 'Unavailable', 'Glucose']}
                  labelFormatter={(label) => String(label)}
                  contentStyle={{ borderRadius: 10, border: '1px solid #e4eaf1', boxShadow: '0 10px 30px rgba(26, 48, 78, 0.12)' }}
                />
                <Line
                  type="monotone"
                  dataKey="glucoseValue"
                  stroke="#159b9a"
                  strokeWidth={2.5}
                  dot={false}
                  connectNulls={false}
                  isAnimationActive={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
          <div className="history-caption"><Eye size={14} aria-hidden="true" /> Glucose values are observed inputs, not model explanations.</div>
          <div className="history-table-wrap">
            <table className="data-table">
              <caption className="sr-only">Most recent observed history records</caption>
              <thead>
                <tr><th scope="col">Time</th><th scope="col">Glucose</th><th scope="col">Heart rate</th><th scope="col">Steps</th><th scope="col">Meal</th></tr>
              </thead>
              <tbody>
                {recent.map((point, index) => (
                  <tr key={`${point.timestamp}-${index}`}>
                    <td>{formatTimestamp(point.timestamp, true)}</td>
                    <td>{isFiniteNumber(point.glucose) ? `${formatNumber(point.glucose)} mg/dL` : 'Unavailable'}</td>
                    <td>{isFiniteNumber(point.heart_rate) ? `${formatNumber(point.heart_rate)} bpm` : 'Unavailable'}</td>
                    <td>{formatNumber(point.steps)}</td>
                    <td>{formatNumber(point.meal_carbs)} g</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="history-source"><Database size={13} aria-hidden="true" /> Synthetic observations returned by the local twin API</div>
        </>
      )}
    </Panel>
  );
}
