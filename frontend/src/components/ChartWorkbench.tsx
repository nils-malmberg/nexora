import { useEffect, useMemo, useState } from "react";
import { errorMessage, getChartTools, getIndicators, getMarketHistory } from "../api/client";
import { LineChart, type ChartBand, type ChartPoint, type ChartSeries } from "../charts/LineChart";
import { PriceChart, type ChartKind, type DotSeries, type Drawing, type Marker, type RefLine } from "../charts/PriceChart";
import { exportAsCsv } from "../csvExport";
import { formatAmount, formatDate, formatNumber } from "../format";
import { href } from "../router";
import type { ChartTools, HistoryRange, Indicators, Instrument, MarketHistory } from "../types";
import { HISTORY_RANGES, HISTORY_RANGE_LABELS, PATTERN_LABELS } from "../types";
import { EducationNote } from "./EducationNote";

const RANGE_DAYS: Record<HistoryRange, number> = { "1w": 7, "1m": 31, "3m": 93, "6m": 186, "1y": 366, "2y": 732, "5y": 1830, max: 3650 };

function toPoints(dates: string[], values: (number | string | null)[]): ChartPoint[] {
  const points: ChartPoint[] = [];
  dates.forEach((d, i) => {
    const v = values[i];
    if (v !== null && v !== undefined) points.push({ x: new Date(d), y: Number(v) });
  });
  return points;
}

interface Toggles {
  sma: boolean;
  ema: boolean;
  bollinger: boolean;
  ichimoku: boolean;
  sar: boolean;
  pivots: boolean;
  fibonacci: boolean;
  levels: boolean;
  patterns: boolean;
}

const DEFAULT_TOGGLES: Toggles = { sma: true, ema: false, bollinger: false, ichimoku: false, sar: false, pivots: false, fibonacci: false, levels: true, patterns: true };

/** The analysis chart a broker site offers: chart type, log scale, window,
 * classic overlays and the "pro" tools (Ichimoku, SAR, pivots, Fibonacci,
 * supports/resistances, candlestick patterns), each with its reading, plus
 * free-hand trend lines kept in the browser. */
export function ChartWorkbench({ instrument, currency, refreshTick }: { instrument: Instrument; currency: string; refreshTick: number }) {
  const [history, setHistory] = useState<MarketHistory | null>(null);
  const [indicators, setIndicators] = useState<Indicators | null>(null);
  const [tools, setTools] = useState<ChartTools | null>(null);
  const [range, setRange] = useState<HistoryRange>("1y");
  const [kind, setKind] = useState<ChartKind>("candles");
  const [logScale, setLogScale] = useState(false);
  const [showVolume, setShowVolume] = useState(true);
  const [toggles, setToggles] = useState<Toggles>(DEFAULT_TOGGLES);
  const [params, setParams] = useState({ sma: 20, ema: 12, rsi: 14, macd_fast: 12, macd_slow: 26, macd_signal: 9, bollinger: 20, atr: 14, stochastic: 14 });
  const [error, setError] = useState<string | null>(null);
  const [drawMode, setDrawMode] = useState<"segment" | "horizontal" | null>(null);
  const [pending, setPending] = useState<{ x: number; y: number } | null>(null);
  const storageKey = `nexora-drawings-${instrument.id}`;
  const [drawings, setDrawings] = useState<Drawing[]>(() => {
    try {
      return JSON.parse(localStorage.getItem(storageKey) ?? "[]");
    } catch {
      return [];
    }
  });

  useEffect(() => {
    try {
      localStorage.setItem(storageKey, JSON.stringify(drawings));
    } catch {
      // storage unavailable: drawings live for the session only
    }
  }, [drawings, storageKey]);

  useEffect(() => {
    let cancelled = false;
    setError(null);
    Promise.all([getMarketHistory(instrument.id, range), getChartTools(instrument.id, RANGE_DAYS[range])])
      .then(([h, t]) => {
        if (cancelled) return;
        setHistory(h);
        setTools(t);
      })
      .catch((err: unknown) => !cancelled && setError(errorMessage(err)));
    return () => {
      cancelled = true;
    };
  }, [instrument.id, range, refreshTick]);

  useEffect(() => {
    let cancelled = false;
    getIndicators(instrument.id, { ...params, days: Math.max(RANGE_DAYS[range], 60) })
      .then((ind) => !cancelled && setIndicators(ind))
      .catch(() => !cancelled && setIndicators(null));
    return () => {
      cancelled = true;
    };
  }, [instrument.id, range, params, refreshTick]);

  const bars = useMemo(() => history?.bars ?? [], [history]);
  const rangeStart = useMemo(() => new Date(Date.now() - RANGE_DAYS[range] * 86_400_000), [range]);
  const inRange = (p: ChartPoint) => p.x >= rangeStart;

  const overlays: ChartSeries[] = [];
  const bands: ChartBand[] = [];
  const refLines: RefLine[] = [];
  const dots: DotSeries[] = [];
  const markers: Marker[] = [];
  const extraDates: Date[] = [];

  if (indicators) {
    if (toggles.sma) overlays.push({ label: `SMA(${indicators.sma_window})`, color: "#a33a00", points: toPoints(indicators.dates, indicators.sma).filter(inRange) });
    if (toggles.ema) overlays.push({ label: `EMA(${indicators.ema_window})`, color: "#1f7a3d", points: toPoints(indicators.dates, indicators.ema).filter(inRange) });
    if (toggles.bollinger) {
      const upper = toPoints(indicators.dates, indicators.bollinger_upper).filter(inRange);
      const lower = toPoints(indicators.dates, indicators.bollinger_lower).filter(inRange);
      if (upper.length > 1 && upper.length === lower.length) bands.push({ label: `Bollinger(${indicators.bollinger_window}, ${indicators.bollinger_k})`, color: "#7c3aed", upper, lower });
    }
  }
  if (tools) {
    if (toggles.ichimoku && tools.ichimoku) {
      const ich = tools.ichimoku;
      overlays.push({ label: "Tenkan (9)", color: "#0891b2", points: toPoints(tools.dates, ich.tenkan), width: 1.2 });
      overlays.push({ label: "Kijun (26)", color: "#be185d", points: toPoints(tools.dates, ich.kijun), width: 1.2 });
      overlays.push({ label: "Chikou", color: "#4b5563", points: toPoints(tools.dates, ich.chikou), dashed: true, width: 1 });
      const allDates = [...tools.dates, ...ich.future_dates];
      const a = toPoints(allDates, [...ich.senkou_a, ...ich.future_senkou_a]);
      const b = toPoints(allDates, [...ich.senkou_b, ...ich.future_senkou_b]);
      if (a.length > 1 && a.length === b.length) bands.push({ label: "Nuage Ichimoku (Senkou A/B)", color: "#0891b2", upper: a, lower: b });
      extraDates.push(...ich.future_dates.map((d) => new Date(d)));
    }
    if (toggles.sar && tools.sar) {
      dots.push({
        label: "SAR parabolique",
        color: "#7c3aed",
        points: tools.dates.map((d, i) => ({ x: new Date(d), y: tools.sar!.values[i] ?? NaN, color: tools.sar!.trend[i] === 1 ? "#1f7a3d" : "#a33a00" })).filter((p) => Number.isFinite(p.y)),
      });
    }
    if (toggles.pivots && tools.pivots.length) {
      const p = tools.pivots[0];
      refLines.push({ y: p.pivot, label: "Pivot", color: "#334155", dashed: false }, { y: p.r1, label: "R1", color: "#991b1b" }, { y: p.r2, label: "R2", color: "#991b1b" }, { y: p.s1, label: "S1", color: "#166534" }, { y: p.s2, label: "S2", color: "#166534" });
    }
    if (toggles.fibonacci && tools.fibonacci) {
      for (const [ratio, price] of tools.fibonacci.levels) refLines.push({ y: price, label: `Fib ${(ratio * 100).toFixed(1)} %`, color: "#a3690a" });
    }
    if (toggles.levels) {
      for (const s of tools.supports) refLines.push({ y: s, label: "support", color: "#166534" });
      for (const r of tools.resistances) refLines.push({ y: r, label: "résistance", color: "#991b1b" });
    }
    if (toggles.patterns) {
      for (const pat of tools.patterns) {
        const bar = bars.find((b) => b.as_of === pat.as_of);
        if (!bar) continue;
        const up = pat.direction === "haussier";
        markers.push({ x: new Date(pat.as_of), y: Number(up ? bar.low : bar.high), label: up ? "▲" : pat.direction === "baissier" ? "▼" : "◆", color: up ? "#166534" : pat.direction === "baissier" ? "#991b1b" : "#64748b", above: !up, title: PATTERN_LABELS[pat.name] ?? pat.name });
      }
    }
  }

  function onPointClick(point: { x: Date; y: number }) {
    if (!drawMode) return;
    if (drawMode === "horizontal") {
      setDrawings((d) => [...d, { id: `${Date.now()}`, kind: "horizontal", x1: point.x.getTime(), y1: point.y }]);
      setDrawMode(null);
      return;
    }
    if (!pending) {
      setPending({ x: point.x.getTime(), y: point.y });
      return;
    }
    setDrawings((d) => [...d, { id: `${Date.now()}`, kind: "segment", x1: pending.x, y1: pending.y, x2: point.x.getTime(), y2: point.y }]);
    setPending(null);
    setDrawMode(null);
  }

  const pendingDrawing: Drawing[] = pending ? [{ id: "pending", kind: "segment", x1: pending.x, y1: pending.y }] : [];
  const toggle = (key: keyof Toggles) => setToggles({ ...toggles, [key]: !toggles[key] });

  return (
    <>
      <div className="toolbar">
        <div className="range-picker" role="group" aria-label="Fenêtre temporelle">
          {HISTORY_RANGES.map((r) => (
            <button key={r} type="button" className={r === range ? "range-button active" : "range-button"} onClick={() => setRange(r)}>
              {HISTORY_RANGE_LABELS[r]}
            </button>
          ))}
        </div>
        <label>
          Tracé
          <select value={kind} onChange={(e) => setKind(e.target.value as ChartKind)}>
            <option value="candles" disabled={!history?.has_ohlc}>
              Chandeliers
            </option>
            <option value="bars" disabled={!history?.has_ohlc}>
              Barres OHLC
            </option>
            <option value="line">Ligne</option>
            <option value="area">Aire</option>
          </select>
        </label>
        <label className="inline-check">
          <input type="checkbox" checked={logScale} onChange={(e) => setLogScale(e.target.checked)} /> Échelle log
        </label>
        <label className="inline-check">
          <input type="checkbox" checked={showVolume} onChange={(e) => setShowVolume(e.target.checked)} /> Volume
        </label>
      </div>
      <div className="toolbar chart-toggles" role="group" aria-label="Indicateurs et outils">
        {(
          [
            ["sma", "SMA"],
            ["ema", "EMA"],
            ["bollinger", "Bollinger"],
            ["ichimoku", "Ichimoku"],
            ["sar", "SAR"],
            ["pivots", "Pivots"],
            ["fibonacci", "Fibonacci"],
            ["levels", "Supports / résistances"],
            ["patterns", "Figures"],
          ] as [keyof Toggles, string][]
        ).map(([key, label]) => (
          <label key={key} className={`chip ${toggles[key] ? "active" : ""}`}>
            <input type="checkbox" checked={toggles[key]} onChange={() => toggle(key)} disabled={(key === "ichimoku" || key === "sar" || key === "pivots" || key === "patterns") && !tools?.has_ohlc} /> {label}
          </label>
        ))}
        <span className="muted">|</span>
        <button type="button" className={drawMode === "segment" ? "range-button active" : "range-button"} onClick={() => setDrawMode(drawMode === "segment" ? null : "segment")} title="Cliquez deux points sur le graphique">
          ✎ Droite de tendance
        </button>
        <button type="button" className={drawMode === "horizontal" ? "range-button active" : "range-button"} onClick={() => setDrawMode(drawMode === "horizontal" ? null : "horizontal")} title="Cliquez un niveau">
          ― Niveau horizontal
        </button>
        {drawings.length > 0 && (
          <button type="button" className="link-button" onClick={() => setDrawings([])}>
            Effacer les tracés ({drawings.length})
          </button>
        )}
      </div>
      {drawMode && <p className="muted" role="status">{drawMode === "segment" ? (pending ? "Cliquez le second point." : "Cliquez le premier point de la droite.") : "Cliquez le niveau à tracer."}</p>}
      {error && <p className="error-state">{error}</p>}
      {history && history.status !== "fresh" && history.status !== "cached" && (
        <p className="prediction-warning" role="status">
          Historique {history.status === "stale" ? "servi depuis le cache" : "indisponible"} ({history.reason?.replaceAll("_", " ")}).
        </p>
      )}
      {history && !history.has_ohlc && bars.length > 0 && <p className="muted">Cette source ne publie que des clôtures : tracé en ligne, sans chandeliers reconstitués ; Ichimoku, SAR, pivots et figures ne s'appliquent pas.</p>}
      <PriceChart
        bars={bars}
        kind={kind}
        logScale={logScale}
        showVolume={showVolume}
        overlays={overlays}
        bands={bands}
        referenceLines={refLines}
        dots={dots}
        markers={markers}
        drawings={[...drawings, ...pendingDrawing]}
        drawMode={drawMode}
        onPointClick={onPointClick}
        extraDates={extraDates}
        currency={currency}
        yFormatter={(v) => formatAmount(v, undefined)}
      />
      {history && (
        <p className="muted">
          {history.bars.length} barre(s) quotidienne(s){history.source ? ` · source : ${history.source}` : ""}
          {history.attribution ? ` · ${history.attribution}` : ""}
        </p>
      )}

      {tools && (
        <div className="card-grid tool-readings">
          {toggles.ichimoku && tools.ichimoku && (
            <div className="card">
              <h4>Ichimoku</h4>
              <p>{tools.ichimoku.reading}</p>
            </div>
          )}
          {toggles.sar && tools.sar && (
            <div className="card">
              <h4>SAR parabolique</h4>
              <p>{tools.sar.reading}</p>
            </div>
          )}
          {toggles.pivots && tools.pivots.length > 0 && (
            <div className="card">
              <h4>Points pivots</h4>
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th />
                      <th>S3</th>
                      <th>S2</th>
                      <th>S1</th>
                      <th>Pivot</th>
                      <th>R1</th>
                      <th>R2</th>
                      <th>R3</th>
                    </tr>
                  </thead>
                  <tbody>
                    {tools.pivots.map((p) => (
                      <tr key={p.period}>
                        <td title={p.based_on}>{p.period}</td>
                        <td>{formatNumber(p.s3, 2)}</td>
                        <td>{formatNumber(p.s2, 2)}</td>
                        <td>{formatNumber(p.s1, 2)}</td>
                        <td>
                          <strong>{formatNumber(p.pivot, 2)}</strong>
                        </td>
                        <td>{formatNumber(p.r1, 2)}</td>
                        <td>{formatNumber(p.r2, 2)}</td>
                        <td>{formatNumber(p.r3, 2)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="muted">Niveaux calculés sur la période précédente : au-dessus du pivot, les acheteurs dominent la séance ; S1/R1 sont les premiers arrêts probables. Le graphique affiche les pivots du jour.</p>
            </div>
          )}
          {toggles.fibonacci && tools.fibonacci && (
            <div className="card">
              <h4>Retracements de Fibonacci</h4>
              <p>{tools.fibonacci.reading}</p>
              <p className="muted">
                Plus haut {formatNumber(tools.fibonacci.swing_high, 2)} ({formatDate(tools.fibonacci.swing_high_date)}) · plus bas {formatNumber(tools.fibonacci.swing_low, 2)} ({formatDate(tools.fibonacci.swing_low_date)})
              </p>
            </div>
          )}
          {toggles.levels && (
            <div className="card">
              <h4>Supports et résistances</h4>
              <p>
                Supports : {tools.supports.length ? tools.supports.map((s) => formatNumber(s, 2)).join(" · ") : "aucun repéré"} — Résistances : {tools.resistances.length ? tools.resistances.map((r) => formatNumber(r, 2)).join(" · ") : "aucune repérée"}
              </p>
              <p className="muted">Niveaux où le cours s'est retourné plusieurs fois sur un an. Un support cassé devient souvent une résistance, et inversement.</p>
            </div>
          )}
          {toggles.patterns && tools.has_ohlc && (
            <div className="card">
              <h4>Figures de chandeliers (60 dernières séances)</h4>
              {tools.patterns.length === 0 ? (
                <p className="muted">Aucune figure classique détectée.</p>
              ) : (
                <ul className="pattern-list">
                  {tools.patterns
                    .slice(-8)
                    .reverse()
                    .map((p, i) => (
                      <li key={i}>
                        <strong className={p.direction === "haussier" ? "delta-up" : p.direction === "baissier" ? "delta-down" : undefined}>
                          {p.direction === "haussier" ? "▲" : p.direction === "baissier" ? "▼" : "◆"} {PATTERN_LABELS[p.name] ?? p.name}
                        </strong>{" "}
                        <span className="muted">{formatDate(p.as_of)}</span>
                        <p className="muted">{p.explanation}</p>
                      </li>
                    ))}
                </ul>
              )}
            </div>
          )}
        </div>
      )}
      {tools && <p className="muted">{tools.method}</p>}
      <div className="toolbar">
        <button type="button" className="export-button" disabled={bars.length === 0} onClick={() => exportAsCsv(`nexora-${instrument.symbol}-${range}.csv`, bars.map((b) => ({ date: b.as_of, open: b.open, high: b.high, low: b.low, close: b.close, volume: b.volume })))}>
          Exporter l'historique (CSV)
        </button>
        <a className="link-button" href={href("help", "outils-graphiques")}>
          Comprendre ces outils
        </a>
      </div>
      <EducationNote slug="chandeliers" />

      <h3>Indicateurs techniques</h3>
      <div className="inline-form">
        {(["sma", "ema", "rsi", "bollinger", "atr", "stochastic"] as const).map((key) => (
          <label key={key}>
            {key.toUpperCase()}
            <input type="number" min={2} max={200} value={params[key]} onChange={(e) => setParams({ ...params, [key]: Number(e.target.value) || 2 })} style={{ width: 70 }} />
          </label>
        ))}
        <label>
          MACD
          <span className="inline-form">
            <input type="number" min={2} max={200} value={params.macd_fast} onChange={(e) => setParams({ ...params, macd_fast: Number(e.target.value) || 2 })} style={{ width: 56 }} aria-label="MACD rapide" />
            <input type="number" min={2} max={200} value={params.macd_slow} onChange={(e) => setParams({ ...params, macd_slow: Number(e.target.value) || 2 })} style={{ width: 56 }} aria-label="MACD lent" />
            <input type="number" min={2} max={200} value={params.macd_signal} onChange={(e) => setParams({ ...params, macd_signal: Number(e.target.value) || 2 })} style={{ width: 56 }} aria-label="MACD signal" />
          </span>
        </label>
      </div>
      {indicators && indicators.prices.length > 1 ? (
        <div className="indicator-grid">
          <div>
            <h4>RSI({indicators.rsi_window})</h4>
            <LineChart series={[{ label: "RSI", color: "#7c3aed", points: toPoints(indicators.dates, indicators.rsi).filter(inRange) }]} referenceLines={[{ y: 70, label: "70" }, { y: 30, label: "30" }]} yMin={0} yMax={100} height={150} showLegend={false} />
          </div>
          <div>
            <h4>
              MACD({indicators.macd_fast}, {indicators.macd_slow}, {indicators.macd_signal_window})
            </h4>
            <LineChart
              series={[
                { label: "MACD", color: "#1d4ed8", points: toPoints(indicators.dates, indicators.macd).filter(inRange) },
                { label: "Signal", color: "#a33a00", points: toPoints(indicators.dates, indicators.macd_signal).filter(inRange), dashed: true },
              ]}
              referenceLines={[{ y: 0 }]}
              height={150}
            />
          </div>
          {indicators.has_ohlc && (
            <div>
              <h4>Stochastique({indicators.stochastic_window})</h4>
              <LineChart
                series={[
                  { label: "%K", color: "#0891b2", points: toPoints(indicators.dates, indicators.stochastic_k).filter(inRange) },
                  { label: "%D", color: "#be185d", points: toPoints(indicators.dates, indicators.stochastic_d).filter(inRange), dashed: true },
                ]}
                referenceLines={[{ y: 80, label: "80" }, { y: 20, label: "20" }]}
                yMin={0}
                yMax={100}
                height={150}
              />
            </div>
          )}
          {indicators.has_ohlc && (
            <div>
              <h4>ATR({indicators.atr_window})</h4>
              <LineChart series={[{ label: "ATR", color: "#4b5563", points: toPoints(indicators.dates, indicators.atr).filter(inRange) }]} height={150} showLegend={false} yFormatter={(v) => formatAmount(v, undefined)} />
            </div>
          )}
          {indicators.obv.some((v) => v !== null) && (
            <div>
              <h4>OBV</h4>
              <LineChart series={[{ label: "OBV", color: "#a3690a", points: toPoints(indicators.dates, indicators.obv).filter(inRange) }]} height={150} showLegend={false} yFormatter={(v) => v.toLocaleString("fr-FR", { maximumFractionDigits: 0 })} />
            </div>
          )}
        </div>
      ) : (
        <p className="empty-state">Pas encore assez de prix pour des indicateurs.</p>
      )}
      {indicators && (
        <button
          type="button"
          className="export-button"
          onClick={() =>
            exportAsCsv(
              `nexora-indicateurs-${instrument.symbol}.csv`,
              indicators.dates.map((d, i) => ({ date: d, prix: indicators.prices[i], sma: indicators.sma[i], ema: indicators.ema[i], rsi: indicators.rsi[i], macd: indicators.macd[i], macd_signal: indicators.macd_signal[i], bollinger_upper: indicators.bollinger_upper[i], bollinger_lower: indicators.bollinger_lower[i], atr: indicators.atr[i], stochastic_k: indicators.stochastic_k[i], obv: indicators.obv[i] })),
            )
          }
        >
          Exporter les indicateurs (CSV)
        </button>
      )}
      <EducationNote slug="indicateurs-techniques" />
    </>
  );
}
