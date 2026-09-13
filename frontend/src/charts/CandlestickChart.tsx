import { useState } from "react";
import type { Bar } from "../types";
import type { ChartBand, ChartSeries } from "./LineChart";

const WIDTH = 720;
const PAD_LEFT = 56;
const PAD_RIGHT = 16;
const PAD_TOP = 12;
const PAD_BOTTOM = 26;
const VOLUME_H = 56;

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

/** OHLC candlesticks + volume, drawn from provider bars as they are — when a
 * bar has no open/high/low (close-only sources) the caller renders a
 * LineChart instead; this component never invents candle bodies. Overlays
 * (moving averages, Bollinger bands) share the price axis. */
export function CandlestickChart({
  bars,
  overlays = [],
  bands = [],
  height = 320,
  currency,
  yFormatter = (v) => v.toFixed(2),
}: {
  bars: Bar[];
  overlays?: ChartSeries[];
  bands?: ChartBand[];
  height?: number;
  currency?: string;
  yFormatter?: (value: number) => string;
}) {
  const [hover, setHover] = useState<number | null>(null);
  const usable = bars.filter((b) => b.open !== null && b.high !== null && b.low !== null);
  if (usable.length < 2) {
    return <p className="empty-state">Pas assez de chandeliers (source sans OHLC ou historique trop court).</p>;
  }
  const highs = usable.map((b) => Number(b.high));
  const lows = usable.map((b) => Number(b.low));
  const overlayYs = [...overlays.flatMap((s) => s.points.map((p) => p.y)), ...bands.flatMap((b) => [...b.upper, ...b.lower].map((p) => p.y))];
  let lo = Math.min(...lows, ...overlayYs);
  let hi = Math.max(...highs, ...overlayYs);
  const span = hi - lo || 1;
  lo -= span * 0.04;
  hi += span * 0.04;

  const hasVolume = usable.some((b) => b.volume !== null);
  const plotW = WIDTH - PAD_LEFT - PAD_RIGHT;
  const priceH = height - PAD_TOP - PAD_BOTTOM - (hasVolume ? VOLUME_H + 8 : 0);
  const volumeTop = PAD_TOP + priceH + 8;
  const n = usable.length;
  const slot = plotW / n;
  const bodyW = Math.max(1.5, Math.min(12, slot * 0.7));
  const times = usable.map((b) => new Date(b.as_of).getTime());
  const minT = times[0];
  const maxT = times[n - 1];

  const xAt = (i: number) => PAD_LEFT + slot * i + slot / 2;
  const xForTime = (t: number) => (maxT === minT ? xAt(0) : PAD_LEFT + slot / 2 + ((t - minT) / (maxT - minT)) * (plotW - slot));
  const yPrice = (v: number) => PAD_TOP + priceH - ((v - lo) / (hi - lo)) * priceH;
  const maxVol = Math.max(...usable.map((b) => Number(b.volume ?? 0)), 1);
  const yVol = (v: number) => volumeTop + VOLUME_H - (v / maxVol) * VOLUME_H;
  const ticks = niceTicks(lo, hi);
  const dateFmt = (t: number) => new Date(t).toLocaleDateString("fr-FR", { day: "2-digit", month: "short", year: "2-digit" });

  function onMove(evt: React.MouseEvent<SVGSVGElement>) {
    const rect = evt.currentTarget.getBoundingClientRect();
    const px = ((evt.clientX - rect.left) / rect.width) * WIDTH;
    const i = Math.round((px - PAD_LEFT - slot / 2) / slot);
    setHover(i >= 0 && i < n ? i : null);
  }

  const hovered = hover !== null ? usable[hover] : null;

  return (
    <div className="chart-wrapper">
      <svg viewBox={`0 0 ${WIDTH} ${height}`} className="line-chart" role="img" aria-label="Graphique en chandeliers" onMouseMove={onMove} onMouseLeave={() => setHover(null)}>
        {ticks.map((tick) => (
          <g key={tick}>
            <line x1={PAD_LEFT} x2={WIDTH - PAD_RIGHT} y1={yPrice(tick)} y2={yPrice(tick)} className="chart-grid" />
            <text x={PAD_LEFT - 6} y={yPrice(tick) + 3} textAnchor="end" className="chart-axis-label">
              {yFormatter(tick)}
            </text>
          </g>
        ))}
        {bands.map((band) => {
          const upper = band.upper.map((p) => `${xForTime(p.x.getTime())},${yPrice(p.y)}`);
          const lower = [...band.lower].reverse().map((p) => `${xForTime(p.x.getTime())},${yPrice(p.y)}`);
          return <polygon key={band.label} points={[...upper, ...lower].join(" ")} fill={band.color} fillOpacity={0.15} stroke="none" />;
        })}
        {usable.map((bar, i) => {
          const open = Number(bar.open);
          const close = Number(bar.close);
          const up = close >= open;
          const x = xAt(i);
          const top = yPrice(Math.max(open, close));
          const bottom = yPrice(Math.min(open, close));
          return (
            <g key={bar.as_of} className={up ? "candle-up" : "candle-down"}>
              <line x1={x} x2={x} y1={yPrice(Number(bar.high))} y2={yPrice(Number(bar.low))} />
              <rect x={x - bodyW / 2} y={top} width={bodyW} height={Math.max(1, bottom - top)} />
              {hasVolume && bar.volume !== null && <rect className="volume-bar" x={x - bodyW / 2} y={yVol(Number(bar.volume))} width={bodyW} height={volumeTop + VOLUME_H - yVol(Number(bar.volume))} />}
            </g>
          );
        })}
        {overlays
          .filter((s) => s.points.length > 1)
          .map((s) => (
            <polyline key={s.label} fill="none" stroke={s.color} strokeWidth={s.width ?? 1.6} strokeDasharray={s.dashed ? "5 4" : undefined} points={s.points.map((p) => `${xForTime(p.x.getTime())},${yPrice(p.y)}`).join(" ")} />
          ))}
        {hover !== null && <line x1={xAt(hover)} x2={xAt(hover)} y1={PAD_TOP} y2={PAD_TOP + priceH} className="chart-crosshair" />}
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
          <span>O {yFormatter(Number(hovered.open))}</span>
          <span>H {yFormatter(Number(hovered.high))}</span>
          <span>L {yFormatter(Number(hovered.low))}</span>
          <span>C {yFormatter(Number(hovered.close))}</span>
          {hovered.volume !== null && <span>Vol. {Number(hovered.volume).toLocaleString("fr-FR", { maximumFractionDigits: 0 })}</span>}
          {currency && <span className="muted">{currency}</span>}
        </div>
      )}
      <div className="chart-legend">
        <span className="chart-legend-item">
          <span className="chart-swatch candle-swatch-up" /> Clôture ≥ ouverture
        </span>
        <span className="chart-legend-item">
          <span className="chart-swatch candle-swatch-down" /> Clôture &lt; ouverture
        </span>
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
      </div>
    </div>
  );
}
