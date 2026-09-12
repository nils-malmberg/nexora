export interface ChartPoint {
  x: Date;
  y: number;
}

export interface ChartSeries {
  label: string;
  color: string;
  points: ChartPoint[];
}

const WIDTH = 640;
const PAD = 36;

/** Hand-rolled SVG line chart - no charting dependency (this project keeps
 * frontend dependencies to react/react-dom only). Good enough for V1's line
 * series (portfolio value over time, instrument price + indicators); real
 * candlesticks would need OHLC data this app doesn't have yet (see
 * app/adapters/market_data.py). */
export function LineChart({
  series,
  height = 220,
  yFormatter = (v) => v.toFixed(2),
}: {
  series: ChartSeries[];
  height?: number;
  yFormatter?: (value: number) => string;
}) {
  // A series whose window (e.g. SMA/EMA) hasn't filled yet renders as no
  // points at all - drop it entirely rather than showing an empty legend
  // swatch for a line nobody can see.
  const visibleSeries = series.filter((s) => s.points.length > 0);
  const allPoints = visibleSeries.flatMap((s) => s.points);
  if (allPoints.length < 2) {
    return <p className="empty-state">Pas assez de données pour un graphique.</p>;
  }

  const xs = allPoints.map((p) => p.x.getTime());
  const ys = allPoints.map((p) => p.y);
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(...ys, 0);
  const maxY = Math.max(...ys);

  const scaleX = (t: number) => (maxX === minX ? WIDTH / 2 : PAD + ((t - minX) / (maxX - minX)) * (WIDTH - 2 * PAD));
  const scaleY = (v: number) =>
    maxY === minY ? height / 2 : height - PAD - ((v - minY) / (maxY - minY)) * (height - 2 * PAD);

  return (
    <div className="chart-wrapper">
      <svg viewBox={`0 0 ${WIDTH} ${height}`} className="line-chart" role="img" aria-label="Graphique en ligne">
        <line x1={PAD} y1={height - PAD} x2={WIDTH - PAD} y2={height - PAD} className="chart-axis" />
        <text x={PAD} y={height - 10} className="chart-axis-label">
          {new Date(minX).toLocaleDateString("fr-FR")}
        </text>
        <text x={WIDTH - PAD} y={height - 10} textAnchor="end" className="chart-axis-label">
          {new Date(maxX).toLocaleDateString("fr-FR")}
        </text>
        <text x={4} y={PAD} className="chart-axis-label">
          {yFormatter(maxY)}
        </text>
        <text x={4} y={height - PAD} className="chart-axis-label">
          {yFormatter(minY)}
        </text>
        {visibleSeries.map((s) => (
          <polyline
            key={s.label}
            fill="none"
            stroke={s.color}
            strokeWidth={2}
            points={s.points.map((p) => `${scaleX(p.x.getTime())},${scaleY(p.y)}`).join(" ")}
          />
        ))}
      </svg>
      <div className="chart-legend">
        {visibleSeries.map((s) => (
          <span key={s.label} className="chart-legend-item">
            <span className="chart-swatch" style={{ background: s.color }} />
            {s.label}
          </span>
        ))}
      </div>
    </div>
  );
}
