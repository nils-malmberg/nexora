import { useId, useState } from "react";

export interface ChartPoint {
  x: Date;
  y: number;
}

export interface ChartSeries {
  label: string;
  color: string;
  points: ChartPoint[];
  dashed?: boolean;
  width?: number;
}

/** A shaded region between two series (e.g. Bollinger bands, Monte Carlo
 * percentiles). Both must be sampled on the same x values. */
export interface ChartBand {
  label: string;
  color: string;
  upper: ChartPoint[];
  lower: ChartPoint[];
}

export interface ReferenceLine {
  y: number;
  label?: string;
  color?: string;
}

const WIDTH = 720;
const PAD_LEFT = 56;
const PAD_RIGHT = 16;
const PAD_TOP = 12;
const PAD_BOTTOM = 28;

function niceTicks(min: number, max: number, count = 4): number[] {
  if (!(max > min)) return [min];
  const raw = (max - min) / count;
  const magnitude = 10 ** Math.floor(Math.log10(raw));
  const candidates = [1, 2, 2.5, 5, 10].map((m) => m * magnitude);
  const step = candidates.find((c) => c >= raw) ?? candidates[candidates.length - 1];
  const start = Math.ceil(min / step) * step;
  const ticks: number[] = [];
  for (let v = start; v <= max + step / 1000; v += step) ticks.push(Number(v.toFixed(10)));
  return ticks;
}

/** Hand-rolled SVG line chart: several series, optional bands and reference
 * lines, y gridlines, hover read-out. No charting dependency — the whole
 * frontend deliberately depends on react/react-dom only. */
export function LineChart({
  series,
  bands = [],
  referenceLines = [],
  height = 240,
  yFormatter = (v) => v.toFixed(2),
  yMin,
  yMax,
  ariaLabel = "Graphique en ligne",
  showLegend = true,
}: {
  series: ChartSeries[];
  bands?: ChartBand[];
  referenceLines?: ReferenceLine[];
  height?: number;
  yFormatter?: (value: number) => string;
  yMin?: number;
  yMax?: number;
  ariaLabel?: string;
  showLegend?: boolean;
}) {
  const clipId = useId();
  const [hover, setHover] = useState<{ x: number; date: Date; values: { label: string; color: string; y: number }[] } | null>(null);

  // A series whose window hasn't filled yet has no points: drop it rather
  // than showing a legend swatch for an invisible line.
  const visibleSeries = series.filter((s) => s.points.length > 0);
  const allPoints = [...visibleSeries.flatMap((s) => s.points), ...bands.flatMap((b) => [...b.upper, ...b.lower])];
  if (allPoints.length < 2) {
    return <p className="empty-state">Pas assez de données pour un graphique.</p>;
  }

  const xs = allPoints.map((p) => p.x.getTime());
  const ys = [...allPoints.map((p) => p.y), ...referenceLines.map((r) => r.y)];
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  let lo = yMin ?? Math.min(...ys);
  let hi = yMax ?? Math.max(...ys);
  if (hi === lo) {
    hi = lo + 1;
    lo = lo - 1;
  }
  const span = hi - lo;
  lo -= span * 0.04;
  hi += span * 0.04;

  const plotW = WIDTH - PAD_LEFT - PAD_RIGHT;
  const plotH = height - PAD_TOP - PAD_BOTTOM;
  const scaleX = (t: number) => (maxX === minX ? PAD_LEFT + plotW / 2 : PAD_LEFT + ((t - minX) / (maxX - minX)) * plotW);
  const scaleY = (v: number) => PAD_TOP + plotH - ((v - lo) / (hi - lo)) * plotH;
  const ticks = niceTicks(lo, hi);
  const dateFmt = (t: number) => new Date(t).toLocaleDateString("fr-FR", { day: "2-digit", month: "short", year: "2-digit" });

  function onMove(evt: React.MouseEvent<SVGSVGElement>) {
    const rect = evt.currentTarget.getBoundingClientRect();
    const px = ((evt.clientX - rect.left) / rect.width) * WIDTH;
    const t = minX + ((px - PAD_LEFT) / plotW) * (maxX - minX);
    const values = visibleSeries
      .map((s) => {
        let best = s.points[0];
        for (const p of s.points) if (Math.abs(p.x.getTime() - t) < Math.abs(best.x.getTime() - t)) best = p;
        return { label: s.label, color: s.color, y: best.y, t: best.x.getTime() };
      })
      .filter((v) => Math.abs(v.t - t) <= (maxX - minX) / 20 + 1);
    if (values.length === 0) {
      setHover(null);
      return;
    }
    setHover({ x: scaleX(values[0].t), date: new Date(values[0].t), values });
  }

  return (
    <div className="chart-wrapper">
      <svg
        viewBox={`0 0 ${WIDTH} ${height}`}
        className="line-chart"
        role="img"
        aria-label={ariaLabel}
        onMouseMove={onMove}
        onMouseLeave={() => setHover(null)}
      >
        <defs>
          <clipPath id={clipId}>
            <rect x={PAD_LEFT} y={PAD_TOP} width={plotW} height={plotH} />
          </clipPath>
        </defs>
        {ticks.map((tick) => (
          <g key={tick}>
            <line x1={PAD_LEFT} x2={WIDTH - PAD_RIGHT} y1={scaleY(tick)} y2={scaleY(tick)} className="chart-grid" />
            <text x={PAD_LEFT - 6} y={scaleY(tick) + 3} textAnchor="end" className="chart-axis-label">
              {yFormatter(tick)}
            </text>
          </g>
        ))}
        <line x1={PAD_LEFT} y1={PAD_TOP + plotH} x2={WIDTH - PAD_RIGHT} y2={PAD_TOP + plotH} className="chart-axis" />
        <text x={PAD_LEFT} y={height - 8} className="chart-axis-label">
          {dateFmt(minX)}
        </text>
        <text x={WIDTH - PAD_RIGHT} y={height - 8} textAnchor="end" className="chart-axis-label">
          {dateFmt(maxX)}
        </text>
        <g clipPath={`url(#${clipId})`}>
          {bands.map((band) => {
            const upper = band.upper.map((p) => `${scaleX(p.x.getTime())},${scaleY(p.y)}`);
            const lower = [...band.lower].reverse().map((p) => `${scaleX(p.x.getTime())},${scaleY(p.y)}`);
            return <polygon key={band.label} points={[...upper, ...lower].join(" ")} fill={band.color} fillOpacity={0.15} stroke="none" />;
          })}
          {referenceLines.map((ref) => (
            <g key={`${ref.label}-${ref.y}`}>
              <line x1={PAD_LEFT} x2={WIDTH - PAD_RIGHT} y1={scaleY(ref.y)} y2={scaleY(ref.y)} stroke={ref.color ?? "currentColor"} strokeDasharray="4 4" strokeOpacity={0.6} />
              {ref.label && (
                <text x={WIDTH - PAD_RIGHT - 4} y={scaleY(ref.y) - 3} textAnchor="end" className="chart-axis-label">
                  {ref.label}
                </text>
              )}
            </g>
          ))}
          {visibleSeries.map((s) => (
            <polyline
              key={s.label}
              fill="none"
              stroke={s.color}
              strokeWidth={s.width ?? 1.8}
              strokeDasharray={s.dashed ? "5 4" : undefined}
              points={s.points.map((p) => `${scaleX(p.x.getTime())},${scaleY(p.y)}`).join(" ")}
            />
          ))}
          {hover && <line x1={hover.x} x2={hover.x} y1={PAD_TOP} y2={PAD_TOP + plotH} className="chart-crosshair" />}
        </g>
      </svg>
      {hover && (
        <div className="chart-tooltip" role="status">
          <span className="muted">{dateFmt(hover.date.getTime())}</span>
          {hover.values.map((v) => (
            <span key={v.label}>
              <span className="chart-swatch" style={{ background: v.color }} /> {v.label} : {yFormatter(v.y)}
            </span>
          ))}
        </div>
      )}
      {showLegend && (
        <div className="chart-legend">
          {visibleSeries.map((s) => (
            <span key={s.label} className="chart-legend-item">
              <span className="chart-swatch" style={{ background: s.color }} />
              {s.label}
            </span>
          ))}
          {bands.map((b) => (
            <span key={b.label} className="chart-legend-item">
              <span className="chart-swatch" style={{ background: b.color, opacity: 0.35 }} />
              {b.label}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
