import { useId, useState } from "react";
import type { Bar } from "../types";
import type { ChartBand, ChartSeries } from "./LineChart";

export type ChartKind = "candles" | "bars" | "line" | "area";

export interface RefLine {
  y: number;
  label?: string;
  color?: string;
  dashed?: boolean;
}

/** Discrete points (e.g. parabolic SAR). */
export interface DotSeries {
  label: string;
  color: string;
  points: { x: Date; y: number; color?: string }[];
}

/** Annotations anchored to a bar (candlestick patterns). */
export interface Marker {
  x: Date;
  y: number;
  label: string;
  color: string;
  above?: boolean;
  title?: string;
}

/** User drawings: a segment between two (date, price) points, or a
 * horizontal line at a price. */
export interface Drawing {
  id: string;
  kind: "segment" | "horizontal";
  x1: number; // epoch ms
  y1: number;
  x2?: number;
  y2?: number;
  color?: string;
}

export interface ChartPointClick {
  x: Date;
  y: number;
}

const WIDTH = 760;
const PAD_LEFT = 58;
const PAD_RIGHT = 16;
const PAD_TOP = 12;
const PAD_BOTTOM = 26;
const VOLUME_H = 56;

function niceTicks(min: number, max: number, count = 5): number[] {
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

function logTicks(min: number, max: number): number[] {
  const ticks: number[] = [];
  let mag = 10 ** Math.floor(Math.log10(Math.max(min, 1e-9)));
  while (mag <= max) {
    for (const m of [1, 2, 5]) {
      const v = m * mag;
      if (v >= min && v <= max) ticks.push(v);
    }
    mag *= 10;
  }
  return ticks.length >= 2 ? ticks : niceTicks(min, max);
}

/** The instrument price chart: candles / OHLC bars / line / area on a
 * linear or logarithmic axis, volume pane, overlays and bands (moving
 * averages, Bollinger, Ichimoku cloud), reference lines (pivots, Fibonacci,
 * supports/resistances, stop/target), dot series (SAR), pattern markers, and
 * the user's own drawings with click-to-draw. Still a hand-rolled SVG: no
 * charting dependency, everything readable without colour alone. */
export function PriceChart({
  bars,
  kind = "candles",
  logScale = false,
  showVolume = true,
  overlays = [],
  bands = [],
  referenceLines = [],
  dots = [],
  markers = [],
  drawings = [],
  drawMode = null,
  onPointClick,
  extraDates = [],
  height = 360,
  currency,
  yFormatter = (v) => v.toFixed(2),
}: {
  bars: Bar[];
  kind?: ChartKind;
  logScale?: boolean;
  showVolume?: boolean;
  overlays?: ChartSeries[];
  bands?: ChartBand[];
  referenceLines?: RefLine[];
  dots?: DotSeries[];
  markers?: Marker[];
  drawings?: Drawing[];
  drawMode?: "segment" | "horizontal" | null;
  onPointClick?: (point: ChartPointClick) => void;
  /** Dates beyond the last bar the x axis must reach (Ichimoku cloud ahead). */
  extraDates?: Date[];
  height?: number;
  currency?: string;
  yFormatter?: (value: number) => string;
}) {
  const clipId = useId();
  const [hover, setHover] = useState<number | null>(null);
  const hasOhlc = bars.length > 1 && bars.every((b) => b.open !== null && b.high !== null && b.low !== null);
  const effectiveKind: ChartKind = hasOhlc ? kind : kind === "area" ? "area" : "line";
  if (bars.length < 2) return <p className="empty-state">Pas assez de données pour un graphique.</p>;

  const closes = bars.map((b) => Number(b.close));
  const highs = hasOhlc ? bars.map((b) => Number(b.high)) : closes;
  const lows = hasOhlc ? bars.map((b) => Number(b.low)) : closes;
  const extraYs = [
    ...overlays.flatMap((s) => s.points.map((p) => p.y)),
    ...bands.flatMap((b) => [...b.upper, ...b.lower].map((p) => p.y)),
    ...dots.flatMap((d) => d.points.map((p) => p.y)),
    ...referenceLines.map((r) => r.y),
  ].filter((v) => Number.isFinite(v) && v > 0);
  let lo = Math.min(...lows, ...extraYs);
  let hi = Math.max(...highs, ...extraYs);
  if (logScale) {
    lo = Math.max(lo, 1e-9) / 1.03;
    hi = hi * 1.03;
  } else {
    const span = hi - lo || 1;
    lo -= span * 0.04;
    hi += span * 0.04;
  }

  const hasVolume = showVolume && bars.some((b) => b.volume !== null);
  const plotW = WIDTH - PAD_LEFT - PAD_RIGHT;
  const priceH = height - PAD_TOP - PAD_BOTTOM - (hasVolume ? VOLUME_H + 8 : 0);
  const volumeTop = PAD_TOP + priceH + 8;
  const times = bars.map((b) => new Date(b.as_of).getTime());
  const minT = times[0];
  const maxT = Math.max(times[times.length - 1], ...extraDates.map((d) => d.getTime()));
  const n = bars.length;
  const slot = plotW / (n + extraDates.length);
  const bodyW = Math.max(1.5, Math.min(12, slot * 0.7));

  const xForTime = (t: number) => (maxT === minT ? PAD_LEFT + slot / 2 : PAD_LEFT + slot / 2 + ((t - minT) / (maxT - minT)) * (plotW - slot));
  const xAt = (i: number) => xForTime(times[i]);
  const yPrice = (v: number) => {
    const f = logScale ? (Math.log(Math.max(v, 1e-9)) - Math.log(lo)) / (Math.log(hi) - Math.log(lo)) : (v - lo) / (hi - lo);
    return PAD_TOP + priceH - f * priceH;
  };
  const priceAtY = (y: number) => {
    const f = (PAD_TOP + priceH - y) / priceH;
    return logScale ? Math.exp(Math.log(lo) + f * (Math.log(hi) - Math.log(lo))) : lo + f * (hi - lo);
  };
  const timeAtX = (x: number) => minT + ((x - PAD_LEFT - slot / 2) / (plotW - slot)) * (maxT - minT);
  const maxVol = Math.max(...bars.map((b) => Number(b.volume ?? 0)), 1);
  const yVol = (v: number) => volumeTop + VOLUME_H - (v / maxVol) * VOLUME_H;
  const ticks = logScale ? logTicks(lo, hi) : niceTicks(lo, hi);
  const dateFmt = (t: number) => new Date(t).toLocaleDateString("fr-FR", { day: "2-digit", month: "short", year: "2-digit" });

  function svgCoords(evt: React.MouseEvent<SVGSVGElement>) {
    const rect = evt.currentTarget.getBoundingClientRect();
    return { px: ((evt.clientX - rect.left) / rect.width) * WIDTH, py: ((evt.clientY - rect.top) / rect.height) * height };
  }
  function onMove(evt: React.MouseEvent<SVGSVGElement>) {
    const { px } = svgCoords(evt);
    const t = timeAtX(px);
    let best = 0;
    for (let i = 1; i < n; i++) if (Math.abs(times[i] - t) < Math.abs(times[best] - t)) best = i;
    setHover(Math.abs(times[best] - t) <= slot * 2 * ((maxT - minT) / (plotW - slot)) + 1 ? best : null);
  }
  function onClick(evt: React.MouseEvent<SVGSVGElement>) {
    if (!onPointClick) return;
    const { px, py } = svgCoords(evt);
    if (py < PAD_TOP || py > PAD_TOP + priceH) return;
    onPointClick({ x: new Date(timeAtX(px)), y: priceAtY(py) });
  }

  const hovered = hover !== null ? bars[hover] : null;
  const closePath = bars.map((b, i) => `${xAt(i)},${yPrice(Number(b.close))}`).join(" ");
  const gridLabel = (v: number) => (logScale ? yFormatter(v) : yFormatter(v));

  return (
    <div className={`chart-wrapper ${drawMode ? "chart-drawing" : ""}`}>
      <svg
        viewBox={`0 0 ${WIDTH} ${height}`}
        className="line-chart price-chart"
        role="img"
        aria-label={`Graphique ${effectiveKind === "candles" ? "en chandeliers" : effectiveKind === "bars" ? "en barres OHLC" : "en ligne"}`}
        onMouseMove={onMove}
        onMouseLeave={() => setHover(null)}
        onClick={onClick}
      >
        <defs>
          <clipPath id={clipId}>
            <rect x={PAD_LEFT} y={PAD_TOP} width={plotW} height={priceH} />
          </clipPath>
        </defs>
        {ticks.map((tick) => (
          <g key={tick}>
            <line x1={PAD_LEFT} x2={WIDTH - PAD_RIGHT} y1={yPrice(tick)} y2={yPrice(tick)} className="chart-grid" />
            <text x={PAD_LEFT - 6} y={yPrice(tick) + 3} textAnchor="end" className="chart-axis-label">
              {gridLabel(tick)}
            </text>
          </g>
        ))}
        <g clipPath={`url(#${clipId})`}>
          {bands.map((band) => {
            const upper = band.upper.map((p) => `${xForTime(p.x.getTime())},${yPrice(p.y)}`);
            const lower = [...band.lower].reverse().map((p) => `${xForTime(p.x.getTime())},${yPrice(p.y)}`);
            return <polygon key={band.label} points={[...upper, ...lower].join(" ")} fill={band.color} fillOpacity={0.16} stroke="none" />;
          })}
          {effectiveKind === "area" && (
            <polygon points={`${xAt(0)},${PAD_TOP + priceH} ${closePath} ${xAt(n - 1)},${PAD_TOP + priceH}`} fill="#1d4ed8" fillOpacity={0.12} stroke="none" />
          )}
          {(effectiveKind === "line" || effectiveKind === "area") && <polyline fill="none" stroke="#1d4ed8" strokeWidth={2} points={closePath} />}
          {(effectiveKind === "candles" || effectiveKind === "bars") &&
            bars.map((bar, i) => {
              const open = Number(bar.open);
              const close = Number(bar.close);
              const up = close >= open;
              const x = xAt(i);
              const top = yPrice(Math.max(open, close));
              const bottom = yPrice(Math.min(open, close));
              return (
                <g key={bar.as_of} className={up ? "candle-up" : "candle-down"}>
                  <line x1={x} x2={x} y1={yPrice(Number(bar.high))} y2={yPrice(Number(bar.low))} />
                  {effectiveKind === "candles" ? (
                    <rect x={x - bodyW / 2} y={top} width={bodyW} height={Math.max(1, bottom - top)} />
                  ) : (
                    <>
                      <line x1={x - bodyW / 2} x2={x} y1={yPrice(open)} y2={yPrice(open)} />
                      <line x1={x} x2={x + bodyW / 2} y1={yPrice(close)} y2={yPrice(close)} />
                    </>
                  )}
                </g>
              );
            })}
          {overlays
            .filter((s) => s.points.length > 1)
            .map((s) => (
              <polyline key={s.label} fill="none" stroke={s.color} strokeWidth={s.width ?? 1.6} strokeDasharray={s.dashed ? "5 4" : undefined} points={s.points.map((p) => `${xForTime(p.x.getTime())},${yPrice(p.y)}`).join(" ")} />
            ))}
          {dots.map((d) => (
            <g key={d.label}>
              {d.points.map((p, i) => (
                <circle key={i} cx={xForTime(p.x.getTime())} cy={yPrice(p.y)} r={1.8} fill={p.color ?? d.color} />
              ))}
            </g>
          ))}
          {referenceLines.map((ref, i) => (
            <g key={`${ref.label ?? "ref"}-${i}`}>
              <line x1={PAD_LEFT} x2={WIDTH - PAD_RIGHT} y1={yPrice(ref.y)} y2={yPrice(ref.y)} stroke={ref.color ?? "#64748b"} strokeDasharray={ref.dashed === false ? undefined : "4 4"} strokeOpacity={0.8} />
              {ref.label && (
                <text x={WIDTH - PAD_RIGHT - 4} y={yPrice(ref.y) - 3} textAnchor="end" className="chart-axis-label" fill={ref.color ?? "#64748b"}>
                  {ref.label}
                </text>
              )}
            </g>
          ))}
          {drawings.map((d) =>
            d.kind === "horizontal" ? (
              <line key={d.id} x1={PAD_LEFT} x2={WIDTH - PAD_RIGHT} y1={yPrice(d.y1)} y2={yPrice(d.y1)} stroke={d.color ?? "#be185d"} strokeWidth={1.4} />
            ) : d.x2 !== undefined && d.y2 !== undefined ? (
              <line key={d.id} x1={xForTime(d.x1)} y1={yPrice(d.y1)} x2={xForTime(d.x2)} y2={yPrice(d.y2)} stroke={d.color ?? "#be185d"} strokeWidth={1.6} />
            ) : (
              <circle key={d.id} cx={xForTime(d.x1)} cy={yPrice(d.y1)} r={3} fill={d.color ?? "#be185d"} />
            ),
          )}
          {markers.map((m, i) => {
            const x = xForTime(m.x.getTime());
            const y = yPrice(m.y) + (m.above ? -10 : 12);
            return (
              <g key={i}>
                <title>{m.title ?? m.label}</title>
                <text x={x} y={y} textAnchor="middle" fontSize={11} fontWeight={600} fill={m.color}>
                  {m.label}
                </text>
              </g>
            );
          })}
          {hover !== null && <line x1={xAt(hover)} x2={xAt(hover)} y1={PAD_TOP} y2={PAD_TOP + priceH} className="chart-crosshair" />}
        </g>
        {hasVolume &&
          bars.map((bar, i) =>
            bar.volume !== null ? (
              <rect key={`v-${bar.as_of}`} className={`volume-bar ${Number(bar.close) >= Number(bar.open ?? bar.close) ? "volume-up" : "volume-down"}`} x={xAt(i) - bodyW / 2} y={yVol(Number(bar.volume))} width={bodyW} height={volumeTop + VOLUME_H - yVol(Number(bar.volume))} />
            ) : null,
          )}
        <line x1={PAD_LEFT} y1={PAD_TOP + priceH} x2={WIDTH - PAD_RIGHT} y2={PAD_TOP + priceH} className="chart-axis" />
        {hasVolume && (
          <text x={PAD_LEFT - 6} y={volumeTop + 10} textAnchor="end" className="chart-axis-label">
            Vol.
          </text>
        )}
        <text x={PAD_LEFT} y={height - 6} className="chart-axis-label">
          {dateFmt(minT)}
        </text>
        <text x={WIDTH - PAD_RIGHT} y={height - 6} textAnchor="end" className="chart-axis-label">
          {dateFmt(maxT)}
        </text>
      </svg>
      {hovered && (
        <div className="chart-tooltip" role="status">
          <span className="muted">{dateFmt(new Date(hovered.as_of).getTime())}</span>
          {hasOhlc && <span>O {yFormatter(Number(hovered.open))}</span>}
          {hasOhlc && <span>H {yFormatter(Number(hovered.high))}</span>}
          {hasOhlc && <span>L {yFormatter(Number(hovered.low))}</span>}
          <span>C {yFormatter(Number(hovered.close))}</span>
          {hovered.volume !== null && <span>Vol. {Number(hovered.volume).toLocaleString("fr-FR", { maximumFractionDigits: 0 })}</span>}
          {currency && <span className="muted">{currency}</span>}
        </div>
      )}
      <div className="chart-legend">
        {(effectiveKind === "candles" || effectiveKind === "bars") && (
          <>
            <span className="chart-legend-item">
              <span className="chart-swatch candle-swatch-up" /> Clôture ≥ ouverture
            </span>
            <span className="chart-legend-item">
              <span className="chart-swatch candle-swatch-down" /> Clôture &lt; ouverture
            </span>
          </>
        )}
        {overlays
          .filter((s) => s.points.length > 1)
          .map((s) => (
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
        {dots.map((d) => (
          <span key={d.label} className="chart-legend-item">
            <span className="chart-swatch" style={{ background: d.color, borderRadius: "50%" }} />
            {d.label}
          </span>
        ))}
        {logScale && <span className="chart-legend-item muted">échelle logarithmique</span>}
      </div>
    </div>
  );
}
