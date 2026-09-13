import { useEffect, useState } from "react";
import { addToWatchlist, errorMessage, getInstrument, getQuote, listWatchlist, removeFromWatchlist, updateWatchlistItem } from "../api/client";
import { AlertForm } from "../components/AlertForm";
import { AssetClassBadge, FreshnessBadge, QuoteStatusBadge } from "../components/Badges";
import { ChartWorkbench } from "../components/ChartWorkbench";
import { DecisionAidPanel } from "../components/DecisionAidPanel";
import { HoldDialog } from "../components/HoldDialog";
import { QuantPanel } from "../components/QuantPanel";
import { QuickBuyDialog } from "../components/QuickBuyDialog";
import { StrategyStudyPanel } from "../components/StrategyStudyPanel";
import { appConfig } from "../configStore";
import { formatAge, formatAmount, formatDateTime, formatPct } from "../format";
import { href, navigate } from "../router";
import type { Instrument, Quote, WatchlistItem } from "../types";
import { ASSET_CLASS_LABELS } from "../types";
import { NewsPage } from "./NewsPage";
import { EventsPage } from "./EventsPage";
import { TimelinePage } from "./TimelinePage";

type Tab = "decision" | "chart" | "quant" | "strategy" | "news" | "timeline" | "events" | "alerts";

export function InstrumentPage({ instrumentId, initialTab }: { instrumentId: string; initialTab?: string }) {
  const [instrument, setInstrument] = useState<Instrument | null>(null);
  const [quote, setQuote] = useState<Quote | null>(null);
  const [tab, setTab] = useState<Tab>((initialTab as Tab) || "decision");
  const [error, setError] = useState<string | null>(null);
  const [watchItem, setWatchItem] = useState<WatchlistItem | null>(null);
  const [showBuy, setShowBuy] = useState(false);
  const [showHold, setShowHold] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [refreshTick, setRefreshTick] = useState(0);
  const config = appConfig();

  useEffect(() => {
    let cancelled = false;
    setError(null);
    Promise.all([getInstrument(instrumentId), getQuote(instrumentId), listWatchlist()])
      .then(([i, q, watch]) => {
        if (cancelled) return;
        setInstrument(i);
        setQuote(q);
        setWatchItem(watch.find((w) => w.instrument.id === instrumentId) ?? null);
      })
      .catch((err: unknown) => !cancelled && setError(errorMessage(err)));
    return () => {
      cancelled = true;
    };
  }, [instrumentId, refreshTick]);

  async function toggleWatch() {
    setMessage(null);
    try {
      if (watchItem) {
        await removeFromWatchlist(watchItem.id);
        setWatchItem(null);
        setMessage("Retiré de la liste de suivi.");
      } else {
        const item = await addToWatchlist(instrumentId);
        setWatchItem(item);
        setMessage("Ajouté à la liste de suivi : cotation, actualités et bilan rafraîchis automatiquement.");
      }
    } catch (err) {
      setError(errorMessage(err, "Action impossible"));
    }
  }

  async function stopHolding() {
    if (!watchItem) return;
    try {
      setWatchItem(await updateWatchlistItem(watchItem.id, { held: false, clear_entry: true }));
      setMessage("Vous n'êtes plus noté comme détenteur de ce titre.");
      setRefreshTick((t) => t + 1);
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
            {watchItem?.held && (
              <span className="badge quote-fresh">
                détenu{watchItem.entry_price ? ` à ${formatAmount(watchItem.entry_price, currency)}` : ""}
                {watchItem.quantity ? ` × ${Number(watchItem.quantity)}` : ""}
              </span>
            )}
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
        <button type="button" className="primary-button decision-button" onClick={() => setTab("decision")} aria-pressed={tab === "decision"}>
          Acheter ou vendre ?
        </button>
        <button type="button" className="export-button" onClick={toggleWatch}>
          {watchItem ? "Ne plus suivre" : "Suivre (watchlist)"}
        </button>
        {watchItem?.held ? (
          <>
            <button type="button" className="export-button" onClick={() => setShowHold(true)}>
              Modifier ma position
            </button>
            <button type="button" className="link-button" onClick={stopHolding}>
              Je ne détiens plus
            </button>
          </>
        ) : (
          <button type="button" className="export-button" onClick={() => setShowHold(true)}>
            Je détiens ce titre
          </button>
        )}
        {config.portfolios_enabled && (
          <button type="button" className="export-button" onClick={() => setShowBuy(true)}>
            Ajouter au portefeuille
          </button>
        )}
        <button type="button" className="export-button" onClick={() => setRefreshTick((t) => t + 1)}>
          Rafraîchir
        </button>
        <button type="button" className="export-button" onClick={() => setTab("alerts")}>
          Créer une alerte
        </button>
      </div>
      {message && (
        <p className="muted" role="status">
          {message}
        </p>
      )}
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
      {showHold && (
        <HoldDialog
          instrument={instrument}
          quote={quote}
          item={watchItem}
          onCancel={() => setShowHold(false)}
          onDone={(item) => {
            setWatchItem(item);
            setShowHold(false);
            setMessage("Position notée : l'aide à la décision parle maintenant de conserver ou vendre.");
            setRefreshTick((t) => t + 1);
          }}
        />
      )}

      <div role="tablist" aria-label="Sections de l'instrument" className="subtabs">
        {(
          [
            ["decision", "Acheter ou vendre ?"],
            ["chart", "Graphique & outils"],
            ["quant", "Analyse quantitative"],
            ["strategy", "Étude de stratégie"],
            ["news", "Actualités"],
            ["timeline", "Chronologie"],
            ["events", "Événements"],
            ["alerts", "Alertes"],
          ] as [Tab, string][]
        ).map(([id, label]) => (
          <button key={id} role="tab" aria-selected={tab === id} onClick={() => setTab(id)}>
            {label}
          </button>
        ))}
      </div>

      {tab === "decision" && <DecisionAidPanel key={refreshTick} instrument={instrument} onHoldClick={() => setShowHold(true)} />}
      {tab === "chart" && <ChartWorkbench instrument={instrument} currency={currency} refreshTick={refreshTick} />}
      {tab === "quant" && <QuantPanel subject={{ instrument_id: instrument.id }} currency={currency} label={instrument.symbol} />}
      {tab === "strategy" && <StrategyStudyPanel instrument={instrument} />}
      {tab === "alerts" && <AlertForm instrument={instrument} quote={quote} />}
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
