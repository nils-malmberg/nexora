import { useEffect, useState } from "react";
import { errorMessage, getDecisionAid } from "../api/client";
import { formatDateTime } from "../format";
import { href } from "../router";
import type { DecisionAid, Instrument } from "../types";
import { EducationNote } from "./EducationNote";
import { ReadingBadge, TallyBar } from "./ReadingBadge";
import { SignalTable } from "./SignalTable";

/** The one-button view for a novice: every recognised method applied to
 * this instrument, its reading, its explanation and its limits. Counts,
 * never a verdict; the disclaimer is always on screen. */
export function DecisionAidPanel({ instrument }: { instrument: Instrument }) {
  const [aid, setAid] = useState<DecisionAid | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [horizon, setHorizon] = useState<"all" | "court_terme" | "long_terme" | "transversal">("all");

  function load(refresh = false) {
    setLoading(true);
    setError(null);
    getDecisionAid(instrument.id, refresh)
      .then(setAid)
      .catch((err: unknown) => setError(errorMessage(err)))
      .finally(() => setLoading(false));
  }

  useEffect(() => load(), [instrument.id]); // eslint-disable-line react-hooks/exhaustive-deps

  if (loading && !aid) return <p className="loading-state">Application des méthodes…</p>;
  if (error && !aid) return <p className="error-state">{error}</p>;
  if (!aid) return null;

  const visible = horizon === "all" ? aid.signals : aid.signals.filter((s) => s.horizon === horizon);
  // The headline badge is the majority reading — except when the short and
  // long term disagree, which is a "neutre" for a reader who would otherwise
  // take one word for a verdict (the text below spells the contradiction out).
  const lean = (t: { favorable: number; defavorable: number }) => (t.favorable > t.defavorable ? 1 : t.defavorable > t.favorable ? -1 : 0);
  const court = aid.horizons.find((h) => h.horizon === "court_terme")?.tally;
  const long = aid.horizons.find((h) => h.horizon === "long_terme")?.tally;
  const contradiction = !!court && !!long && court.available > 0 && long.available > 0 && lean(court) * lean(long) < 0;
  const majority = contradiction ? "neutre" : aid.tally.favorable > aid.tally.defavorable ? "favorable" : aid.tally.defavorable > aid.tally.favorable ? "defavorable" : "neutre";
  const f = aid.fundamentals;

  return (
    <section aria-label="Aide à la décision" className="decision-aid">
      <div className="card-header">
        <h3>Aide à la décision — {aid.instrument.symbol}</h3>
        <button type="button" className="export-button" onClick={() => load(true)} disabled={loading}>
          {loading ? "Calcul…" : "Recalculer"}
        </button>
      </div>
      <p className="muted">
        Une quinzaine de méthodes reconnues appliquées mécaniquement aux données disponibles. Chaque ligne dit ce qu'elle mesure, pourquoi elle lit « favorable » ou « défavorable », et jusqu'où on peut lui faire confiance. <a href={href("help", "aide-a-la-decision")}>Comment lire ce bilan</a>
      </p>

      <div className="card decision-summary">
        <div className="card-header">
          <h4>
            Vue d'ensemble <ReadingBadge reading={aid.tally.available === 0 ? "indisponible" : majority} />
            {contradiction && <span className="muted"> (horizons en désaccord)</span>}
          </h4>
          <TallyBar tally={aid.tally} />
        </div>
        <p>{aid.overall}</p>
        <p className="prediction-warning" role="note">
          {aid.disclaimer}
        </p>
      </div>

      <div className="card-grid">
        {aid.horizons.map((h) => (
          <button key={h.horizon} type="button" className={`card card-link horizon-card ${horizon === h.horizon ? "active" : ""}`} onClick={() => setHorizon(horizon === h.horizon ? "all" : h.horizon)} aria-pressed={horizon === h.horizon}>
            <h4>{h.label}</h4>
            <TallyBar tally={h.tally} label={h.label} />
            <p className="muted">{h.text}</p>
          </button>
        ))}
      </div>

      {f.status === "not_configured" && (
        <p className="provider-banner" role="status">
          Fondamentaux non configurés : {f.env_var ? `définissez ${f.env_var} (clé gratuite sur finnhub.io) puis redémarrez` : "la source de fondamentaux est désactivée"}. Le long terme (PER, dividende, croissance, dette, consensus) reste « indisponible » d'ici là.
        </p>
      )}
      {(f.status === "unavailable" || f.status === "stale") && (
        <p className="provider-banner" role="status">
          Fondamentaux {f.status === "stale" ? "servis depuis le cache" : "indisponibles"} ({f.reason?.replaceAll("_", " ")}). Ils sont demandés au plus une fois par jour, sous le budget du fournisseur.
        </p>
      )}
      {f.status === "not_supported" && <p className="muted">Pas de fondamentaux pour ce type d'instrument (ETF, crypto, indice ou instrument privé) : seules les lectures de cours et de risque s'appliquent.</p>}

      <div className="toolbar">
        <span className="muted">
          {aid.observations} clôtures{aid.price_source ? ` (${aid.price_source})` : ""}
          {f.as_of ? ` · fondamentaux ${f.source} du ${formatDateTime(f.as_of)}` : ""}
          {aid.news_last_7_days > 0 ? ` · ${aid.news_last_7_days} actualité(s) sur 7 jours` : ""}
          {aid.prediction_available ? " · prédiction expérimentale incluse" : ""}
        </span>
        {horizon !== "all" && (
          <button type="button" className="link-button" onClick={() => setHorizon("all")}>
            Voir toutes les lectures
          </button>
        )}
      </div>
      <SignalTable signals={visible} showHorizon={horizon === "all"} />
      {f.license_note && <p className="muted attribution">{f.license_note}</p>}
      <EducationNote slug="aide-a-la-decision" />
    </section>
  );
}
