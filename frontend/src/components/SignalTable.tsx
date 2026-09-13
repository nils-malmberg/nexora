import { Fragment, useState } from "react";
import { href } from "../router";
import type { Signal } from "../types";
import { EVIDENCE_LABELS, FAMILY_LABELS } from "../types";
import { ReadingBadge } from "./ReadingBadge";

/** One row per method: reading, value, family, evidence, expandable
 * explanation in plain French with a link to the help article. */
export function SignalTable({ signals, showHorizon = false }: { signals: Signal[]; showHorizon?: boolean }) {
  const [open, setOpen] = useState<Record<string, boolean>>({});
  if (signals.length === 0) return <p className="empty-state">Aucune lecture.</p>;
  return (
    <div className="table-scroll">
      <table className="signal-table">
        <thead>
          <tr>
            <th>Lecture</th>
            <th>Méthode</th>
            <th>Valeur</th>
            <th>Famille</th>
            <th>Preuve</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {signals.map((s) => (
            <Fragment key={s.key}>
              <tr className={`signal-row signal-${s.reading}`}>
                <td>
                  <ReadingBadge reading={s.reading} />
                  {s.reading !== "indisponible" && s.strength === "fort" && <span className="muted"> (fort)</span>}
                </td>
                <td>
                  <strong>{s.label}</strong>
                  {showHorizon && <span className="muted"> · {s.horizon === "court_terme" ? "court terme" : s.horizon === "long_terme" ? "long terme" : "risque"}</span>}
                </td>
                <td>{s.value ?? "—"}</td>
                <td className="muted">{FAMILY_LABELS[s.family] ?? s.family}</td>
                <td>
                  <span className={`badge evidence-${s.evidence}`} title="Solidité de la méthode dans la littérature académique">
                    {EVIDENCE_LABELS[s.evidence]}
                  </span>
                </td>
                <td>
                  <button type="button" className="link-button" aria-expanded={!!open[s.key]} onClick={() => setOpen({ ...open, [s.key]: !open[s.key] })}>
                    {open[s.key] ? "Réduire" : "Pourquoi ?"}
                  </button>
                </td>
              </tr>
              {open[s.key] && (
                <tr className="signal-detail">
                  <td colSpan={6}>
                    <p>{s.detail}</p>
                    {s.help_slug && (
                      <p className="muted">
                        <a href={href("help", s.help_slug)}>Lire l'article d'aide</a>
                      </p>
                    )}
                  </td>
                </tr>
              )}
            </Fragment>
          ))}
        </tbody>
      </table>
    </div>
  );
}
