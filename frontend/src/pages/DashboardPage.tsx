import { useEffect, useState } from "react";
import { errorMessage, getConsolidated, getMarketOverview, getValuation, listInstrumentNews, listPortfolios, listUpcomingEvents } from "../api/client";
import { AllocationBar } from "../charts/AllocationBar";
import { FreshnessBadge } from "../components/Badges";
import { EventCard } from "../components/EventCard";
import { NewsCard } from "../components/NewsCard";
import { ProviderStatusBanner } from "../components/ProviderStatusBanner";
import { formatAge, formatAmount, formatDateTime, formatPct } from "../format";
import { href } from "../router";
import type { CalendarEvent, Consolidated, NewsItem, OverviewEntry, Portfolio, User, Valuation } from "../types";
import { ASSET_CLASS_LABELS } from "../types";

interface PortfolioCard {
  portfolio: Portfolio;
  valuation: Valuation | null;
}

/** Home: one screen with the money (every portfolio's value, cash, missing
 * prices), the market board (cached quotes for what's held/watched), what's
 * coming (events) and what's new (news across tracked instruments). */
export function DashboardPage({ user }: { user: User }) {
  const [cards, setCards] = useState<PortfolioCard[]>([]);
  const [overview, setOverview] = useState<OverviewEntry[]>([]);
  const [events, setEvents] = useState<CalendarEvent[]>([]);
  const [news, setNews] = useState<NewsItem[]>([]);
  const [consolidated, setConsolidated] = useState<Consolidated | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [portfolios, entries, upcoming, total] = await Promise.all([
          listPortfolios(),
          getMarketOverview(),
          listUpcomingEvents({ tz: user.display_timezone, limit: 8 }),
          getConsolidated().catch(() => null),
        ]);
        const valuations = await Promise.all(portfolios.map((p) => getValuation(p.id).catch(() => null)));
        if (cancelled) return;
        setCards(portfolios.map((p, i) => ({ portfolio: p, valuation: valuations[i] })));
        setConsolidated(total);
        setOverview(entries);
        setEvents(upcoming);
        // Latest news across tracked instruments (a handful each, merged, newest first).
        const perInstrument = await Promise.all(entries.slice(0, 12).map((e) => listInstrumentNews(e.instrument.id, { limit: 3 }).then((p) => p.items).catch(() => [])));
        if (cancelled) return;
        const merged = new Map<string, NewsItem>();
        for (const item of perInstrument.flat()) merged.set(item.id, item);
        setNews([...merged.values()].sort((a, b) => b.publication_at.localeCompare(a.publication_at)).slice(0, 8));
      } catch (err) {
        if (!cancelled) setError(errorMessage(err));
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [user.display_timezone]);

  const symbolOf = (instrumentId: string) => overview.find((e) => e.instrument.id === instrumentId)?.instrument.symbol;

  if (loading) return <p className="loading-state">Chargement…</p>;

  return (
    <section aria-label="Tableau de bord">
      <ProviderStatusBanner />
      <h2>Bonjour{user.display_name ? ` ${user.display_name}` : ""}</h2>
      {error && <p className="error-state">{error}</p>}

      {cards.length === 0 && overview.length === 0 && (
        <section className="onboarding" aria-label="Pour commencer">
          <h3>Pour commencer</h3>
          <div className="card-grid">
            <a className="card card-link" href={href("portfolios") + "?tab=import"}>
              <h4>1. Importer mon courtier</h4>
              <p className="muted">Trade Republic, Revolut ou tout CSV : exportez l'historique depuis l'app, importez-le ici. Rien n'est écrit avant votre confirmation.</p>
            </a>
            <a className="card card-link" href={href("markets")}>
              <h4>2. Chercher un titre</h4>
              <p className="muted">Actions, ETF, indices, crypto : cours, chandeliers, indicateurs, actualités, puis « Ajouter au portefeuille » ou « Suivre ».</p>
            </a>
            <a className="card card-link" href={href("help")}>
              <h4>3. Comprendre les chiffres</h4>
              <p className="muted">Chaque mesure renvoie à l'aide : valorisation, TWR/MWR, Sharpe, VaR, Markowitz, indicateurs, prédiction.</p>
            </a>
          </div>
        </section>
      )}

      {consolidated && cards.length > 0 && <ConsolidatedSummary view={consolidated} multi={cards.length > 1} />}

      <h3>Portefeuilles</h3>
      {cards.length === 0 ? (
        <p className="empty-state">
          Aucun portefeuille. <a href={href("portfolios") + "?tab=import"}>Importez votre courtier</a>, <a href={href("markets")}>cherchez un instrument</a> ou{" "}
          <a href={href("portfolios")}>créez un portefeuille</a>.
        </p>
      ) : (
        <div className="card-grid">
          {cards.map(({ portfolio, valuation }) => (
            <a key={portfolio.id} className="card card-link" href={href("portfolios", portfolio.id)}>
              <h4>{portfolio.name}</h4>
              {valuation ? (
                <>
                  <div className="big-number">{formatAmount(valuation.total_value, valuation.base_currency)}</div>
                  <div className="muted">
                    Trésorerie {formatAmount(valuation.cash, valuation.base_currency)} · positions {formatAmount(valuation.positions_value, valuation.base_currency)} · {valuation.positions.length} ligne(s)
                  </div>
                  {valuation.has_missing_prices && <span className="badge freshness-manquant">prix manquants</span>}
                  {valuation.unconverted_currencies.length > 0 && <span className="badge freshness-differe">non converti : {valuation.unconverted_currencies.join(", ")}</span>}
                  <div className="muted">Valorisé le {formatDateTime(valuation.as_of)}</div>
                </>
              ) : (
                <p className="muted">Valorisation indisponible</p>
              )}
            </a>
          ))}
        </div>
      )}

      <h3>Marché — instruments suivis</h3>
      {overview.length === 0 ? (
        <p className="empty-state">
          Rien à suivre encore. <a href={href("markets")}>Ouvrir les marchés</a>.
        </p>
      ) : (
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Instrument</th>
                <th>Cours</th>
                <th>Variation</th>
                <th>Fraîcheur</th>
                <th>Détenu</th>
              </tr>
            </thead>
            <tbody>
              {overview.map((e) => {
                const change = e.quote?.change_pct ? Number(e.quote.change_pct) / 100 : null;
                return (
                  <tr key={e.instrument.id}>
                    <td>
                      <a href={href("markets", e.instrument.id)}>{e.instrument.symbol}</a> <span className="muted">{e.instrument.name}</span>
                    </td>
                    <td>{e.quote?.price ? formatAmount(e.quote.price, e.quote.currency ?? e.instrument.currency) : "—"}</td>
                    <td className={change === null ? undefined : change >= 0 ? "delta-up" : "delta-down"}>{change === null ? "—" : formatPct(change)}</td>
                    <td>
                      {e.quote && <FreshnessBadge freshness={e.quote.freshness} />}
                      {e.quote?.age_seconds != null && <span className="muted"> {formatAge(e.quote.age_seconds)}</span>}
                    </td>
                    <td>{e.held_quantity ? "oui" : e.watched ? "suivi" : ""}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      <div className="two-columns">
        <div>
          <h3>Événements à venir</h3>
          {events.length === 0 ? <p className="empty-state">Aucun événement connu pour vos instruments.</p> : events.map((ev) => <EventCard key={ev.id} event={ev} instrumentLabel={symbolOf(ev.instrument_id)} />)}
          <p className="muted">
            <a href={href("news")}>Tout le calendrier et les actualités</a>
          </p>
        </div>
        <div>
          <h3>Dernières actualités</h3>
          {news.length === 0 ? <p className="empty-state">Aucune actualité collectée pour vos instruments (les sources se configurent dans Paramètres › Sources).</p> : news.map((item) => <NewsCard key={item.id} item={item} />)}
        </div>
      </div>
    </section>
  );
}

/** One number for the whole wealth (every portfolio converted into the
 * reference currency, rate provenance kept) and the global allocation. */
function ConsolidatedSummary({ view, multi }: { view: Consolidated; multi: boolean }) {
  const classLabel = (label: string) => (label === "tresorerie" ? "Trésorerie" : ASSET_CLASS_LABELS[label as keyof typeof ASSET_CLASS_LABELS] ?? label);
  return (
    <section aria-label="Patrimoine consolidé" className="consolidated">
      <h3>Patrimoine {multi ? "consolidé" : ""}</h3>
      <div className="card-grid">
        <div className="card">
          <h4>Valeur totale ({view.reference_currency})</h4>
          <div className="big-number">{formatAmount(view.total_value, view.reference_currency)}</div>
          <div className="muted">
            positions {formatAmount(view.positions_value, view.reference_currency)} · trésorerie {formatAmount(view.cash, view.reference_currency)} · {view.portfolios.length} portefeuille(s)
          </div>
          {view.has_missing_prices && <span className="badge freshness-manquant">prix manquants</span>}
          {view.unconverted_currencies.length > 0 && <span className="badge freshness-differe">non converti : {view.unconverted_currencies.join(", ")}</span>}
          <div className="muted">
            Valorisé le {formatDateTime(view.as_of)} · <a href={href("help", "patrimoine-consolide")}>méthode</a>
          </div>
        </div>
        <div className="card">
          <h4>Par classe d'actifs</h4>
          <AllocationBar slices={view.by_asset_class.map((s) => ({ label: classLabel(s.label), share: s.share }))} />
        </div>
        {multi && (
          <div className="card">
            <h4>Par portefeuille</h4>
            <AllocationBar slices={view.by_portfolio} />
          </div>
        )}
        {view.by_currency.length > 1 && (
          <div className="card">
            <h4>Par devise</h4>
            <AllocationBar slices={view.by_currency} />
          </div>
        )}
      </div>
    </section>
  );
}
