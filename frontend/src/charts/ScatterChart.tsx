import { useState } from "react";

export interface ScatterPoint {
  x: number;
  y: number;
  label: string;
  kind?: "frontier" | "asset" | "special";
  color?: string;
}

const WIDTH = 720;
const HEIGHT = 300;
const PAD_LEFT = 56;
const PAD_RIGHT = 16;
const PAD_TOP = 14;
const PAD_BOTTOM = 34;

/** Risk/return scatter for the efficient frontier: frontier points joined by
 * a line, individual assets and named portfolios as labelled markers. */
export function ScatterChart({
  points,
  xLabel = "Volatilité annualisée",
  yLabel = "Rendement annualisé",
  formatter = (v: number) => `${(v * 100).toFixed(1)} %`,
}: {
  points: ScatterPoint[];
  xLabel?: string;
  yLabel?: string;
  formatter?: (v: number) => string;
}) {
  const [hover, setHover] = useState<ScatterPoint | null>(null);
  if (points.length === 0) return <p className="empty-state">Aucune donnée.</p>;
  const xs = points.map((p) => p.x);
  const ys = points.map((p) => p.y);
  const minX = Math.min(0, ...xs);
  const maxX = Math.max(...xs) * 1.1 || 1;
  let minY = Math.min(...ys);
  let maxY = Math.max(...ys);
  const span = maxY - minY || 1;
  minY -= span * 0.1;
  maxY += span * 0.1;
  const plotW = WIDTH - PAD_LEFT - PAD_RIGHT;
  const plotH = HEIGHT - PAD_TOP - PAD_BOTTOM;
  const sx = (v: number) => PAD_LEFT + ((v - minX) / (maxX - minX)) * plotW;
  const sy = (v: number) => PAD_TOP + plotH - ((v - minY) / (maxY - minY)) * plotH;
  const frontier = points.filter((p) => p.kind === "frontier").sort((a, b) => a.x - b.x);
  const yTicks = [minY, (minY + maxY) / 2, maxY];
  const xTicks = [minX, (minX + maxX) / 2, maxX];
  return (
    <div className="chart-wrapper">
      <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} className="line-chart" role="img" aria-label="Frontière efficiente">
        {yTicks.map((t) => (
          <g key={`y${t}`}>
            <line x1={PAD_LEFT} x2={WIDTH - PAD_RIGHT} y1={sy(t)} y2={sy(t)} className="chart-grid" />
            <text x={PAD_LEFT - 6} y={sy(t) + 3} textAnchor="end" className="chart-axis-label">
              {formatter(t)}
            </text>
          </g>
        ))}
        {xTicks.map((t) => (
          <text key={`x${t}`} x={sx(t)} y={HEIGHT - 16} textAnchor="middle" className="chart-axis-label">
            {formatter(t)}
          </text>
        ))}
        <text x={WIDTH / 2} y={HEIGHT - 3} textAnchor="middle" className="chart-axis-label">
          {xLabel}
        </text>
        <text x={12} y={PAD_TOP + plotH / 2} textAnchor="middle" transform={`rotate(-90 12 ${PAD_TOP + plotH / 2})`} className="chart-axis-label">
          {yLabel}
        </text>
        <line x1={PAD_LEFT} y1={PAD_TOP + plotH} x2={WIDTH - PAD_RIGHT} y2={PAD_TOP + plotH} className="chart-axis" />
        {frontier.length > 1 && <polyline fill="none" stroke="#1d4ed8" strokeWidth={2} points={frontier.map((p) => `${sx(p.x)},${sy(p.y)}`).join(" ")} />}
        {points.map((p, i) => (
          <g key={`${p.label}-${i}`} onMouseEnter={() => setHover(p)} onMouseLeave={() => setHover(null)}>
            {p.kind === "frontier" ? (
              <circle cx={sx(p.x)} cy={sy(p.y)} r={3} fill="#1d4ed8" />
            ) : p.kind === "special" ? (
              <rect x={sx(p.x) - 5} y={sy(p.y) - 5} width={10} height={10} fill={p.color ?? "#a33a00"} />
            ) : (
              <circle cx={sx(p.x)} cy={sy(p.y)} r={5} fill={p.color ?? "#1f7a3d"} />
            )}
            {p.kind !== "frontier" && (
              <text x={sx(p.x) + 7} y={sy(p.y) + 4} className="chart-axis-label">
                {p.label}
              </text>
            )}
          </g>
        ))}
      </svg>
      {hover && (
        <div className="chart-tooltip" role="status">
          <span>{hover.label}</span>
          <span>{xLabel} : {formatter(hover.x)}</span>
          <span>{yLabel} : {formatter(hover.y)}</span>
        </div>
      )}
    </div>
  );
}
