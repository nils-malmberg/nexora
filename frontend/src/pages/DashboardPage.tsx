import { useEffect, useState } from "react";
import { errorMessage, getMarketOverview, getValuation, listInstrumentNews, listPortfolios, listUpcomingEvents } from "../api/client";
import { FreshnessBadge } from "../components/Badges";
import { EventCard } from "../components/EventCard";
import { NewsCard } from "../components/NewsCard";
import { ProviderStatusBanner } from "../components/ProviderStatusBanner";
import { formatAge, formatAmount, formatDateTime, formatPct } from "../format";
import { href } from "../router";
import type { CalendarEvent, NewsItem, OverviewEntry, Portfolio, User, Valuation } from "../types";

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
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [portfolios, entries, upcoming] = await Promise.all([listPortfolios(), getMarketOverview(), listUpcomingEvents({ tz: user.display_timezone, limit: 8 })]);
        const valuations = await Promise.all(portfolios.map((p) => getValuation(p.id).catch(() => null)));
        if (cancelled) return;
        setCards(portfolios.map((p, i) => ({ portfolio: p, valuation: valuations[i] })));
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

      <h3>Portefeuilles</h3>
      {cards.length === 0 ? (
        <p className="empty-state">
          Aucun portefeuille. <a href={href("markets")}>Cherchez un instrument</a> et ajoutez-le, ou <a href={href("portfolios")}>créez un portefeuille</a> et importez un CSV.
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
