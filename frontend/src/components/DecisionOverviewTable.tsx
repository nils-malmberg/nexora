import { useEffect, useState } from "react";
import { errorMessage, getDecisionOverview } from "../api/client";
import { href } from "../router";
import type { DecisionOverview } from "../types";
import { ReadingBadge, TallyBar } from "./ReadingBadge";

/** The quick read for everything held or watched, from cached data only
 * — a glance, with the full aid one click away. */
export function DecisionOverviewTable() {
  const [overview, setOverview] = useState<DecisionOverview | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getDecisionOverview()
      .then((o) => !cancelled && setOverview(o))
      .catch((err: unknown) => !cancelled && setError(errorMessage(err)));
    return () => {
      cancelled = true;
    };
  }, []);

  if (error) return <p className="error-state">{error}</p>;
  if (!overview) return <p className="loading-state">Lecture des instruments suivis…</p>;
  if (overview.entries.length === 0) return null;

  return (
    <section aria-label="Bilan rapide">
      <h3>Bilan rapide (aide à la décision)</h3>
      <p className="muted">
        Lecture instantanée des méthodes principales sur vos instruments, à partir des données en cache. Cliquez un instrument pour le bilan complet et les explications. <a href={href("help", "aide-a-la-decision")}>Comment lire</a>
      </p>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>Instrument</th>
              <th>Tendance</th>
              <th>Momentum 12 m</th>
              <th>RSI</th>
              <th>Valorisation</th>
              <th>Bilan</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {overview.entries.map((e) => (
              <tr key={e.instrument.id}>
                <td>
                  <a href={href("markets", e.instrument.id) + "?tab=decision"}>
                    <strong>{e.instrument.symbol}</strong>
                  </a>{" "}
                  <span className="muted">{e.held ? "détenu" : "suivi"}</span>
                </td>
                <td>
                  <ReadingBadge reading={e.trend} compact />
                </td>
                <td>
                  <ReadingBadge reading={e.momentum} compact />
                </td>
                <td>
                  <ReadingBadge reading={e.rsi_reading} compact /> {e.rsi && <span className="muted">{e.rsi}</span>}
                </td>
                <td>
                  <ReadingBadge reading={e.valuation} compact />
                </td>
                <td>
                  <TallyBar tally={e.tally} label={`Lectures ${e.instrument.symbol}`} />
                </td>
                <td>
                  <a href={href("markets", e.instrument.id) + "?tab=decision"}>Bilan complet</a>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {!overview.fundamentals_configured && <p className="muted">Valorisation « indisponible » : la source de fondamentaux est désactivée (voir Paramètres › Sources).</p>}
      <p className="muted">{overview.disclaimer}</p>
    </section>
  );
}
