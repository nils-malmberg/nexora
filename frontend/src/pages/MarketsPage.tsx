import { useEffect, useState } from "react";
import { errorMessage, getMarketOverview, getProvidersStatus, removeFromWatchlist, listWatchlist } from "../api/client";
import { AssetClassBadge, FreshnessBadge, QuoteStatusBadge } from "../components/Badges";
import { InstrumentSearch } from "../components/InstrumentSearch";
import { formatAge, formatAmount, formatPct, formatQuantity } from "../format";
import { href } from "../router";
import type { OverviewEntry, ProvidersOverview } from "../types";
import { ASSET_CLASS_LABELS } from "../types";

/** Markets: search anything quoted, and the "board" of everything the user
 * holds or watches with cached quotes (refreshed by the worker on the
 * configured cadence — the page itself never fans out to providers). */
export function MarketsPage() {
  const [entries, setEntries] = useState<OverviewEntry[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [providers, setProviders] = useState<ProvidersOverview | null>(null);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let cancelled = false;
    Promise.all([getMarketOverview(), getProvidersStatus()])
      .then(([o, p]) => {
        if (cancelled) return;
        setEntries(o);
        setProviders(p);
      })
      .catch((err: unknown) => !cancelled && setError(errorMessage(err)));
    return () => {
      cancelled = true;
    };
  }, [tick]);

  async function unwatch(instrumentId: string) {
    try {
      const items = await listWatchlist();
      const item = items.find((w) => w.instrument.id === instrumentId);
      if (item) await removeFromWatchlist(item.id);
      setTick((t) => t + 1);
    } catch (err) {
      setError(errorMessage(err, "Action impossible"));
    }
  }

  const held = entries.filter((e) => e.held_quantity !== null);
  const watchedOnly = entries.filter((e) => e.held_quantity === null && e.watched);

  return (
    <section aria-label="Marchés">
      <h2>Marchés</h2>
      <p className="muted">
        Recherchez n'importe quelle action, ETF, indice ou crypto-actif, ouvrez sa fiche (cours, chandeliers, indicateurs, actualités) et ajoutez-le à un portefeuille ou à votre liste de suivi en un clic.
      </p>
      <InstrumentSearch />
      {providers && (
        <p className="muted">
          Sources :{" "}
          {providers.market.map((m) => (
            <span key={m.role}>
              {m.role === "equity" ? "actions/ETF" : m.role === "crypto" ? "crypto" : "change"} → {m.name} {m.healthy ? "✓" : "✗"}
              {m.attribution ? ` (${m.attribution})` : ""} ·{" "}
            </span>
          ))}
          cotations rafraîchies au plus toutes les {providers.quote_freshness_minutes} min, souvent différées selon la place.
        </p>
      )}
      {error && <p className="error-state">{error}</p>}

      <h3>Positions détenues</h3>
      <OverviewTable entries={held} emptyText="Aucune position pour l'instant : recherchez un instrument ci-dessus puis « Ajouter au portefeuille »." />

      <h3>Liste de suivi</h3>
      <OverviewTable entries={watchedOnly} emptyText="Aucun instrument suivi. Depuis la fiche d'un instrument, cliquez « Suivre »." onUnwatch={unwatch} />
    </section>
  );
}

function OverviewTable({ entries, emptyText, onUnwatch }: { entries: OverviewEntry[]; emptyText: string; onUnwatch?: (instrumentId: string) => void }) {
  if (entries.length === 0) return <p className="empty-state">{emptyText}</p>;
  return (
    <div className="table-scroll">
      <table>
        <thead>
          <tr>
            <th>Instrument</th>
            <th>Classe</th>
            <th>Dernier cours</th>
            <th>Variation</th>
            <th>Fraîcheur</th>
            <th>Quantité</th>
            <th>Source</th>
            {onUnwatch && <th />}
          </tr>
        </thead>
        <tbody>
          {entries.map((e) => {
            const q = e.quote;
            const change = q?.change_pct ? Number(q.change_pct) / 100 : null;
            return (
              <tr key={e.instrument.id}>
                <td>
                  <a href={href("markets", e.instrument.id)}>
                    <strong>{e.instrument.symbol}</strong>
                  </a>{" "}
                  <span className="muted">{e.instrument.name}</span>
                </td>
                <td>
                  <AssetClassBadge assetClass={e.instrument.asset_class} label={ASSET_CLASS_LABELS[e.instrument.asset_class] ?? e.instrument.asset_class} />
                </td>
                <td>{q?.price ? formatAmount(q.price, q.currency ?? e.instrument.currency) : "—"}</td>
                <td className={change === null ? undefined : change >= 0 ? "delta-up" : "delta-down"}>{change === null ? "—" : formatPct(change)}</td>
                <td>
                  {q && <FreshnessBadge freshness={q.freshness} />} {q && <QuoteStatusBadge status={q.status} reason={q.reason} />}
                  {q?.age_seconds !== null && q?.age_seconds !== undefined && <span className="muted"> {formatAge(q.age_seconds)}</span>}
                </td>
                <td>{e.held_quantity ? formatQuantity(e.held_quantity) : "—"}</td>
                <td className="muted">{q?.source ?? "—"}</td>
                {onUnwatch && (
                  <td>
                    <button type="button" className="link-button" onClick={() => onUnwatch(e.instrument.id)}>
                      Ne plus suivre
                    </button>
                  </td>
                )}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
