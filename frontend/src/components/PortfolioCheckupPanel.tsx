import { useEffect, useState } from "react";
import { errorMessage, getPortfolioCheckup, setTargetAllocation } from "../api/client";
import { formatAmount, formatPct } from "../format";
import { href } from "../router";
import type { Portfolio, PortfolioCheckup } from "../types";
import { ASSET_CLASSES, ASSET_CLASS_LABELS } from "../types";
import { EducationNote } from "./EducationNote";
import { ReadingBadge, TallyBar } from "./ReadingBadge";
import { SignalTable } from "./SignalTable";

const TARGET_KEYS = [...ASSET_CLASSES, "tresorerie"] as const;
const labelOf = (key: string) => (key === "tresorerie" ? "Trésorerie" : ASSET_CLASS_LABELS[key as keyof typeof ASSET_CLASS_LABELS] ?? key);

/** Structure check-up of one portfolio (concentration, diversification,
 * risk, drift) plus the editor of the user's own target allocation, which
 * only serves to measure that drift. */
export function PortfolioCheckupPanel({ portfolio, onPortfolioUpdated, refreshKey }: { portfolio: Portfolio; onPortfolioUpdated: (p: Portfolio) => void; refreshKey: number }) {
  const [checkup, setCheckup] = useState<PortfolioCheckup | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [targets, setTargets] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setError(null);
    getPortfolioCheckup(portfolio.id)
      .then((c) => !cancelled && setCheckup(c))
      .catch((err: unknown) => !cancelled && setError(errorMessage(err)));
    return () => {
      cancelled = true;
    };
  }, [portfolio.id, refreshKey, tick]);

  function startEditing() {
    const current: Record<string, string> = {};
    const source = portfolio.target_allocation ?? Object.fromEntries((checkup?.allocation ?? []).map((a) => [a.label, a.share]));
    for (const key of TARGET_KEYS) {
      const v = source[key];
      if (v) current[key] = String(Math.round(v * 100));
    }
    setTargets(current);
    setEditing(true);
  }

  const sum = Object.values(targets).reduce((acc, v) => acc + (Number(v) || 0), 0);

  async function save(clear = false) {
    setSaving(true);
    setError(null);
    try {
      const payload = clear ? null : Object.fromEntries(Object.entries(targets).filter(([, v]) => Number(v) > 0).map(([k, v]) => [k, Number(v) / 100]));
      const updated = await setTargetAllocation(portfolio.id, payload);
      onPortfolioUpdated(updated);
      setEditing(false);
      setTick((t) => t + 1);
    } catch (err) {
      setError(errorMessage(err, "Enregistrement impossible"));
    } finally {
      setSaving(false);
    }
  }

  if (error && !checkup) return <p className="error-state">{error}</p>;
  if (!checkup) return <p className="loading-state">Analyse de la structure…</p>;

  const majority = checkup.tally.defavorable === 0 ? "favorable" : checkup.tally.defavorable >= 3 ? "defavorable" : "neutre";

  return (
    <section aria-label="Bilan du portefeuille" className="decision-aid">
      <h3>Bilan du portefeuille</h3>
      <p className="muted">
        La structure compte plus que le choix de chaque titre : concentration, nombre de lignes, corrélation, risque global, et écart à l'allocation que vous vous êtes fixée. <a href={href("help", "bilan-portefeuille")}>Comprendre ce bilan</a>
      </p>
      {error && <p className="error-state">{error}</p>}
      <div className="card decision-summary">
        <div className="card-header">
          <h4>
            Vue d'ensemble <ReadingBadge reading={majority} />
          </h4>
          <TallyBar tally={checkup.tally} />
        </div>
        <p>{checkup.overall}</p>
        <p className="muted">Valeur totale {formatAmount(checkup.total_value, checkup.base_currency)}</p>
      </div>

      <h4>Allocation réelle {checkup.has_targets ? "et cible" : ""}</h4>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>Classe</th>
              <th>Réel</th>
              <th>Cible</th>
              <th>Écart</th>
            </tr>
          </thead>
          <tbody>
            {checkup.allocation.map((a) => (
              <tr key={a.label}>
                <td>{labelOf(a.label)}</td>
                <td>{formatPct(a.share, 0)}</td>
                <td>{a.target === null ? "—" : formatPct(a.target, 0)}</td>
                <td className={a.drift === null ? undefined : Math.abs(a.drift) > 0.1 ? "delta-down" : undefined}>{a.drift === null ? "—" : `${a.drift * 100 >= 0 ? "+" : ""}${(a.drift * 100).toFixed(0)} pts`}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {!editing ? (
        <div className="toolbar">
          <button type="button" className="export-button" onClick={startEditing}>
            {checkup.has_targets ? "Modifier l'allocation cible" : "Définir une allocation cible"}
          </button>
          {checkup.has_targets && (
            <button type="button" className="link-button" onClick={() => save(true)} disabled={saving}>
              Supprimer la cible
            </button>
          )}
        </div>
      ) : (
        <form
          className="inline-form"
          onSubmit={(e) => {
            e.preventDefault();
            save();
          }}
        >
          {TARGET_KEYS.map((key) => (
            <label key={key}>
              {labelOf(key)} (%)
              <input type="number" min={0} max={100} step={1} value={targets[key] ?? ""} onChange={(e) => setTargets({ ...targets, [key]: e.target.value })} style={{ width: 70 }} />
            </label>
          ))}
          <span className={Math.abs(sum - 100) > 1 ? "error-state" : "muted"}>Total {sum} %</span>
          <button type="submit" className="primary-button" disabled={saving || Math.abs(sum - 100) > 1}>
            Enregistrer
          </button>
          <button type="button" onClick={() => setEditing(false)}>
            Annuler
          </button>
        </form>
      )}
      <p className="muted">Votre cible sert uniquement à mesurer l'écart : rien n'est rééquilibré automatiquement.</p>

      <h4>Lectures</h4>
      <SignalTable signals={checkup.signals} />
      <p className="prediction-warning" role="note">
        {checkup.disclaimer}
      </p>
      <EducationNote slug="bilan-portefeuille" />
    </section>
  );
}
