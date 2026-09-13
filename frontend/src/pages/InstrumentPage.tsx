import { useEffect, useMemo, useState } from "react";
import {
  addToWatchlist,
  errorMessage,
  getIndicators,
  getInstrument,
  getMarketHistory,
  getQuote,
  listWatchlist,
  removeFromWatchlist,
} from "../api/client";
import { CandlestickChart } from "../charts/CandlestickChart";
import { LineChart, type ChartBand, type ChartPoint, type ChartSeries } from "../charts/LineChart";
import { AssetClassBadge, FreshnessBadge, QuoteStatusBadge } from "../components/Badges";
import { EducationNote } from "../components/EducationNote";
import { QuantPanel } from "../components/QuantPanel";
import { QuickBuyDialog } from "../components/QuickBuyDialog";
import { exportAsCsv } from "../csvExport";
import { formatAge, formatAmount, formatDateTime, formatPct } from "../format";
import { href, navigate } from "../router";
import type { HistoryRange, Indicators, Instrument, MarketHistory, Quote } from "../types";
import { ASSET_CLASS_LABELS, HISTORY_RANGES, HISTORY_RANGE_LABELS } from "../types";
import { NewsPage } from "./NewsPage";
import { EventsPage } from "./EventsPage";
import { TimelinePage } from "./TimelinePage";

const RANGE_DAYS: Record<HistoryRange, number> = { "1w": 7, "1m": 31, "3m": 93, "6m": 186, "1y": 366, "2y": 732, "5y": 1830, max: 3650 };

type Tab = "chart" | "quant" | "news" | "timeline" | "events";

function toPoints(dates: string[], values: (string | null)[]): ChartPoint[] {
  const points: ChartPoint[] = [];
  dates.forEach((d, i) => {
    const v = values[i];
    if (v !== null && v !== undefined) points.push({ x: new Date(d), y: Number(v) });
  });
  return points;
}

export function InstrumentPage({ instrumentId, initialTab }: { instrumentId: string; initialTab?: string }) {
  const [instrument, setInstrument] = useState<Instrument | null>(null);
  const [quote, setQuote] = useState<Quote | null>(null);
  const [history, setHistory] = useState<MarketHistory | null>(null);
  const [indicators, setIndicators] = useState<Indicators | null>(null);
  const [range, setRange] = useState<HistoryRange>("1y");
  const [tab, setTab] = useState<Tab>((initialTab as Tab) || "chart");
  const [error, setError] = useState<string | null>(null);
  const [watchItemId, setWatchItemId] = useState<string | null>(null);
  const [showBuy, setShowBuy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [chartMode, setChartMode] = useState<"candles" | "line">("candles");
  const [overlays, setOverlays] = useState({ sma: true, ema: false, bollinger: false });
  const [params, setParams] = useState({ sma: 20, ema: 12, rsi: 14, macd_fast: 12, macd_slow: 26, macd_signal: 9, bollinger: 20, atr: 14, stochastic: 14 });
  const [refreshTick, setRefreshTick] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setError(null);
    Promise.all([getInstrument(instrumentId), getQuote(instrumentId), listWatchlist()])
      .then(([i, q, watch]) => {
        if (cancelled) return;
        setInstrument(i);
        setQuote(q);
        setWatchItemId(watch.find((w) => w.instrument.id === instrumentId)?.id ?? null);
      })
      .catch((err: unknown) => !cancelled && setError(errorMessage(err)));
    return () => {
      cancelled = true;
    };
  }, [instrumentId, refreshTick]);

  useEffect(() => {
    let cancelled = false;
    getMarketHistory(instrumentId, range)
      .then((h) => !cancelled && setHistory(h))
      .catch((err: unknown) => !cancelled && setError(errorMessage(err)));
    return () => {
      cancelled = true;
    };
  }, [instrumentId, range, refreshTick]);

  useEffect(() => {
    let cancelled = false;
    getIndicators(instrumentId, { ...params, days: Math.max(RANGE_DAYS[range], 60) })
      .then((ind) => !cancelled && setIndicators(ind))
      .catch(() => !cancelled && setIndicators(null));
    return () => {
      cancelled = true;
    };
  }, [instrumentId, range, params, refreshTick]);

  const chartBars = useMemo(() => history?.bars ?? [], [history]);
  const rangeStart = useMemo(() => new Date(Date.now() - RANGE_DAYS[range] * 86_400_000), [range]);
  const inRange = (p: ChartPoint) => p.x >= rangeStart;

  const overlaySeries: ChartSeries[] = [];
  const bands: ChartBand[] = [];
  if (indicators) {
    if (overlays.sma) overlaySeries.push({ label: `SMA(${indicators.sma_window})`, color: "#a33a00", points: toPoints(indicators.dates, indicators.sma).filter(inRange) });
    if (overlays.ema) overlaySeries.push({ label: `EMA(${indicators.ema_window})`, color: "#1f7a3d", points: toPoints(indicators.dates, indicators.ema).filter(inRange) });
    if (overlays.bollinger) {
      const upper = toPoints(indicators.dates, indicators.bollinger_upper).filter(inRange);
      const lower = toPoints(indicators.dates, indicators.bollinger_lower).filter(inRange);
      if (upper.length > 1 && upper.length === lower.length) bands.push({ label: `Bollinger(${indicators.bollinger_window}, ${indicators.bollinger_k})`, color: "#7c3aed", upper, lower });
    }
  }

  async function toggleWatch() {
    setMessage(null);
    try {
      if (watchItemId) {
        await removeFromWatchlist(watchItemId);
        setWatchItemId(null);
        setMessage("Retiré de la liste de suivi.");
      } else {
        const item = await addToWatchlist(instrumentId);
        setWatchItemId(item.id);
        setMessage("Ajouté à la liste de suivi : sa cotation sera rafraîchie automatiquement.");
      }
    } catch (err) {
      setError(errorMessage(err, "Action impossible"));
    }
  }

  if (error && !instrument) return <p className="error-state">{error}</p>;
  if (!instrument) return <p className="loading-state">Chargement…</p>;

  const price = quote?.price ? Number(quote.price) : null;
  const currency = quote?.currency ?? instrument.currency;
  const changePct = quote?.change_pct ? Number(quote.change_pct) / 100 : null;

  return (
    <section aria-label={`Instrument ${instrument.symbol}`}>
      <p className="breadcrumb">
        <a href={href("markets")}>Marchés</a> › {instrument.symbol}
      </p>
      <div className="instrument-header">
        <div>
          <h2>
            {instrument.symbol} <span className="muted">{instrument.name}</span>
          </h2>
          <div className="card-header">
            <AssetClassBadge assetClass={instrument.asset_class} label={ASSET_CLASS_LABELS[instrument.asset_class] ?? instrument.asset_class} />
            {instrument.exchange && <span className="badge">{instrument.exchange}</span>}
            {instrument.isin && <span className="badge">ISIN {instrument.isin}</span>}
            <span className="badge">{instrument.is_shared ? `source : ${instrument.provider}` : "instrument privé"}</span>
          </div>
        </div>
        <div className="quote-block">
          <div className="quote-price">
            {price !== null ? formatAmount(price, currency) : "—"}
            {changePct !== null && <span className={changePct >= 0 ? "delta-up" : "delta-down"}> {changePct >= 0 ? "▲" : "▼"} {formatPct(changePct)}</span>}
          </div>
          <div className="quote-meta">
            {quote && <FreshnessBadge freshness={quote.freshness} />}
            {quote && <QuoteStatusBadge status={quote.status} reason={quote.reason} />}
            {quote?.as_of && (
              <span className="muted">
                {formatDateTime(quote.as_of)} ({formatAge(quote.age_seconds)}){quote.is_delayed ? " · différé" : ""}
              </span>
            )}
          </div>
          {quote?.attribution && <p className="muted attribution">{quote.attribution}</p>}
        </div>
      </div>
      <div className="toolbar">
        <button type="button" className="primary-button" onClick={() => setShowBuy(true)}>
          Ajouter au portefeuille
        </button>
        <button type="button" className="export-button" onClick={toggleWatch}>
          {watchItemId ? "Ne plus suivre" : "Suivre (watchlist)"}
        </button>
        <button type="button" className="export-button" onClick={() => setRefreshTick((t) => t + 1)}>
          Rafraîchir
        </button>
        <a className="export-button" href={href("prediction") + `?instrument=${instrument.id}`}>
          Expérience de prédiction
        </a>
      </div>
      {message && <p className="muted" role="status">{message}</p>}
      {error && <p className="error-state">{error}</p>}
      {showBuy && (
        <QuickBuyDialog
          instrument={instrument}
          quote={quote}
          onCancel={() => setShowBuy(false)}
          onDone={() => {
            setShowBuy(false);
            setMessage("Achat enregistré dans le portefeuille.");
          }}
        />
      )}

      <div role="tablist" aria-label="Sections de l'instrument" className="subtabs">
        {(
          [
            ["chart", "Cours & indicateurs"],
            ["quant", "Analyse quantitative"],
            ["news", "Actualités"],
            ["timeline", "Chronologie"],
            ["events", "Événements"],
          ] as [Tab, string][]
        ).map(([id, label]) => (
          <button key={id} role="tab" aria-selected={tab === id} onClick={() => setTab(id)}>
            {label}
          </button>
        ))}
      </div>

      {tab === "chart" && (
        <>
          <div className="toolbar">
            <div className="range-picker" role="group" aria-label="Fenêtre temporelle">
              {HISTORY_RANGES.map((r) => (
                <button key={r} type="button" className={r === range ? "range-button active" : "range-button"} onClick={() => setRange(r)}>
                  {HISTORY_RANGE_LABELS[r]}
                </button>
              ))}
            </div>
            <label className="inline-check">
              <input type="radio" name="chartmode" checked={chartMode === "candles"} onChange={() => setChartMode("candles")} disabled={!history?.has_ohlc} /> Chandeliers
            </label>
            <label className="inline-check">
              <input type="radio" name="chartmode" checked={chartMode === "line"} onChange={() => setChartMode("line")} /> Ligne
            </label>
            <label className="inline-check">
              <input type="checkbox" checked={overlays.sma} onChange={(e) => setOverlays({ ...overlays, sma: e.target.checked })} /> SMA
            </label>
            <label className="inline-check">
              <input type="checkbox" checked={overlays.ema} onChange={(e) => setOverlays({ ...overlays, ema: e.target.checked })} /> EMA
            </label>
            <label className="inline-check">
              <input type="checkbox" checked={overlays.bollinger} onChange={(e) => setOverlays({ ...overlays, bollinger: e.target.checked })} /> Bollinger
            </label>
          </div>
          {history && history.status !== "fresh" && history.status !== "cached" && (
            <p className="prediction-warning" role="status">
              Historique {history.status === "stale" ? "servi depuis le cache" : "indisponible"} ({history.reason?.replaceAll("_", " ")}).
            </p>
          )}
          {history && !history.has_ohlc && chartBars.length > 0 && <p className="muted">Cette source ne publie que des clôtures : tracé en ligne, jamais de chandeliers reconstitués.</p>}
          {chartMode === "candles" && history?.has_ohlc ? (
            <CandlestickChart bars={chartBars} overlays={overlaySeries} bands={bands} currency={currency} yFormatter={(v) => formatAmount(v, undefined)} />
          ) : (
            <LineChart
              series={[{ label: "Clôture", color: "#1d4ed8", points: chartBars.map((b) => ({ x: new Date(b.as_of), y: Number(b.close) })), width: 2 }, ...overlaySeries]}
              bands={bands}
              yFormatter={(v) => formatAmount(v, undefined)}
              height={300}
              ariaLabel="Cours de clôture"
            />
          )}
          {history && (
            <p className="muted">
              {history.bars.length} barre(s) quotidienne(s){history.source ? ` · source : ${history.source}` : ""}
              {history.attribution ? ` · ${history.attribution}` : ""}
              {history.license_note ? ` · ${history.license_note}` : ""}
            </p>
          )}
          <div className="toolbar">
            <button
              type="button"
              className="export-button"
              disabled={chartBars.length === 0}
              onClick={() => exportAsCsv(`nexora-${instrument.symbol}-${range}.csv`, chartBars.map((b) => ({ date: b.as_of, open: b.open, high: b.high, low: b.low, close: b.close, volume: b.volume })))}
            >
              Exporter l'historique (CSV)
            </button>
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
                  indicators.dates.map((d, i) => ({
                    date: d,
                    prix: indicators.prices[i],
                    sma: indicators.sma[i],
                    ema: indicators.ema[i],
                    rsi: indicators.rsi[i],
                    macd: indicators.macd[i],
                    macd_signal: indicators.macd_signal[i],
                    bollinger_upper: indicators.bollinger_upper[i],
                    bollinger_lower: indicators.bollinger_lower[i],
                    atr: indicators.atr[i],
                    stochastic_k: indicators.stochastic_k[i],
                    obv: indicators.obv[i],
                  })),
                )
              }
            >
              Exporter les indicateurs (CSV)
            </button>
          )}
          <EducationNote slug="indicateurs-techniques" />
        </>
      )}

      {tab === "quant" && <QuantPanel subject={{ instrument_id: instrument.id }} currency={currency} label={instrument.symbol} />}
      {tab === "news" && <NewsPage instrumentId={instrument.id} />}
      {tab === "timeline" && <TimelinePage instrumentId={instrument.id} />}
      {tab === "events" && <EventsPage instrumentId={instrument.id} />}
      <p className="muted">
        <button type="button" className="link-button" onClick={() => navigate("markets")}>
          ← Retour aux marchés
        </button>
      </p>
    </section>
  );
}
