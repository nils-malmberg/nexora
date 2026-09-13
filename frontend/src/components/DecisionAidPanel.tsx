import { useEffect, useState } from "react";
import { autoExperiment, errorMessage, getDecisionAid, getDecisionAidPast, getExperiment } from "../api/client";
import { LineChart } from "../charts/LineChart";
import { formatDateTime, formatNumber, formatPct } from "../format";
import { href } from "../router";
import type { DecisionAid, Experiment, Instrument, Orientation, PastValidation, Verdict } from "../types";
import { EducationNote } from "./EducationNote";
import { ReadingBadge, TallyBar } from "./ReadingBadge";
import { SignalTable } from "./SignalTable";

const ORIENTATION_ICON: Record<Orientation, string> = { achat: "▲", vente: "▼", attendre: "⏸" };

export function OrientationBadge({ orientation, label, confidence, big = false }: { orientation: Orientation; label?: string; confidence?: string; big?: boolean }) {
  return (
    <span className={`orientation orientation-${orientation} ${big ? "orientation-big" : ""}`}>
      <span aria-hidden="true">{ORIENTATION_ICON[orientation]}</span> {label ?? orientation}
      {confidence && <span className="orientation-confidence"> · confiance {confidence}</span>}
    </span>
  );
}

function fmtPrice(v: number | null | undefined, digits = 2) {
  return v === null || v === undefined ? "—" : formatNumber(v, digits);
}

/** The one-button view for a novice, now framed as a trader reads it:
 * buy or sell?, why (arguments each way), at what levels (stop, target,
 * size), what if I already hold it, and did this method work on this
 * instrument's own past. Counts and explanations, never an instruction. */
export function DecisionAidPanel({ instrument, onHoldClick }: { instrument: Instrument; onHoldClick?: () => void }) {
  const [aid, setAid] = useState<DecisionAid | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [capital, setCapital] = useState(10_000);
  const [riskPct, setRiskPct] = useState(1);
  const [horizon, setHorizon] = useState<"all" | "court_terme" | "long_terme" | "transversal">("all");
  const [past, setPast] = useState<PastValidation | null>(null);
  const [pastHorizon, setPastHorizon] = useState(20);
  const [pastLoading, setPastLoading] = useState(false);
  const [experiment, setExperiment] = useState<Experiment | null>(null);
  const [predLoading, setPredLoading] = useState(false);

  function load(refresh = false) {
    setLoading(true);
    setError(null);
    getDecisionAid(instrument.id, { refreshFundamentals: refresh, capital, riskPct })
      .then(setAid)
      .catch((err: unknown) => setError(errorMessage(err)))
      .finally(() => setLoading(false));
  }

  useEffect(() => load(), [instrument.id, capital, riskPct]); // eslint-disable-line react-hooks/exhaustive-deps

  async function runPast() {
    setPastLoading(true);
    setError(null);
    try {
      setPast(await getDecisionAidPast(instrument.id, pastHorizon));
    } catch (err) {
      setError(errorMessage(err, "Test impossible"));
    } finally {
      setPastLoading(false);
    }
  }

  async function runPrediction() {
    setPredLoading(true);
    setError(null);
    try {
      let exp = await autoExperiment(instrument.id, 5);
      for (let i = 0; i < 60 && (exp.status === "pending" || exp.status === "running"); i++) {
        await new Promise((r) => setTimeout(r, 2000));
        exp = await getExperiment(exp.id);
      }
      setExperiment(exp);
      load();
    } catch (err) {
      setError(errorMessage(err, "Prévision impossible"));
    } finally {
      setPredLoading(false);
    }
  }

  if (loading && !aid) return <p className="loading-state">Application des méthodes…</p>;
  if (error && !aid) return <p className="error-state">{error}</p>;
  if (!aid) return null;

  const visible = horizon === "all" ? aid.signals : aid.signals.filter((s) => s.horizon === horizon);
  const f = aid.fundamentals;
  const lv = aid.levels;
  const court = aid.verdicts.find((v) => v.horizon === "court_terme");
  const long = aid.verdicts.find((v) => v.horizon === "long_terme");

  return (
    <section aria-label="Aide à la décision" className="decision-aid">
      <div className="card-header">
        <h3>Acheter ou vendre {aid.instrument.symbol} ?</h3>
        <button type="button" className="export-button" onClick={() => load(true)} disabled={loading}>
          {loading ? "Calcul…" : "Recalculer"}
        </button>
      </div>
      <p className="muted">
        Les méthodes reconnues appliquées à ce titre, comptées et expliquées. « Achat » veut dire : la majorité des méthodes lit une situation favorable à un achat ou à la conservation ; « vente » : favorable à une vente ou à l'abstention. <a href={href("help", "acheter-ou-vendre")}>Comment lire</a>
      </p>
      {error && <p className="error-state">{error}</p>}

      <div className={`card decision-summary decision-${aid.orientation}`}>
        <div className="card-header">
          <OrientationBadge orientation={aid.orientation} label={aid.orientation_label} confidence={aid.orientation_confidence} big />
          <TallyBar tally={aid.tally} />
        </div>
        <p className="decision-text">{aid.orientation_text}</p>
        <div className="two-columns verdict-columns">
          <div>
            <h4 className="reading-favorable-text">▲ Arguments pour acheter / conserver</h4>
            <ul>
              {aid.verdicts.flatMap((v) => v.buy_case.map((c) => <li key={`${v.horizon}-${c}`}>{c} <span className="muted">({v.horizon === "court_terme" ? "court terme" : "long terme"})</span></li>))}
              {aid.verdicts.every((v) => v.buy_case.length === 0) && <li className="muted">Aucune méthode ne penche pour l'achat.</li>}
            </ul>
          </div>
          <div>
            <h4 className="reading-defavorable-text">▼ Arguments pour vendre / s'abstenir</h4>
            <ul>
              {aid.verdicts.flatMap((v) => v.sell_case.map((c) => <li key={`${v.horizon}-${c}`}>{c} <span className="muted">({v.horizon === "court_terme" ? "court terme" : "long terme"})</span></li>))}
              {aid.verdicts.every((v) => v.sell_case.length === 0) && <li className="muted">Aucune méthode ne penche pour la vente.</li>}
            </ul>
          </div>
        </div>
        <div className="card-grid verdict-grid">
          {[court, long].filter((v): v is Verdict => !!v).map((v) => (
            <div key={v.horizon} className="card">
              <h4>{v.label}</h4>
              <OrientationBadge orientation={v.orientation} label={v.orientation_label} confidence={v.available ? v.confidence : undefined} />
              <p className="muted">{v.text}</p>
            </div>
          ))}
        </div>
        <p className="prediction-warning" role="note">
          {aid.disclaimer}
        </p>
      </div>

      {aid.holder ? (
        <div className={`card decision-holder decision-${aid.holder.orientation}`}>
          <h4>
            Vous détenez ce titre : <OrientationBadge orientation={aid.holder.orientation} label={aid.holder.label} />
          </h4>
          <p>{aid.holder.text}</p>
          {aid.holder.entry_price !== null && (
            <p className="muted">
              Prix d'entrée {fmtPrice(aid.holder.entry_price)} · cours {fmtPrice(lv?.price)} · <span className={aid.holder.pnl_pct !== null && aid.holder.pnl_pct >= 0 ? "delta-up" : "delta-down"}>{formatPct(aid.holder.pnl_pct)}</span>
              {lv?.trailing_stop ? ` · stop suiveur ${fmtPrice(lv.trailing_stop)}` : ""}
            </p>
          )}
        </div>
      ) : (
        onHoldClick && (
          <p className="muted">
            Vous détenez déjà ce titre ?{" "}
            <button type="button" className="link-button" onClick={onHoldClick}>
              Indiquez-le
            </button>{" "}
            pour une lecture « conserver ou vendre » avec votre prix d'entrée.
          </p>
        )
      )}

      {lv && (
        <div className="card">
          <div className="card-header">
            <h4>Niveaux pour agir (règles usuelles de gestion du risque)</h4>
            <form className="inline-form" onSubmit={(e) => e.preventDefault()}>
              <label>
                Capital
                <input type="number" min={100} step={100} value={capital} onChange={(e) => setCapital(Number(e.target.value) || 100)} style={{ width: 100 }} />
              </label>
              <label>
                Risque par position (%)
                <input type="number" min={0.1} max={10} step={0.1} value={riskPct} onChange={(e) => setRiskPct(Number(e.target.value) || 1)} style={{ width: 70 }} />
              </label>
            </form>
          </div>
          <div className="levels-grid">
            <div>
              <span className="muted">Cours</span>
              <strong>{fmtPrice(lv.price)}</strong>
            </div>
            <div>
              <span className="muted">Stop de protection</span>
              <strong className="delta-down">{fmtPrice(lv.stop_loss)}</strong>
              <span className="muted">{formatPct(lv.stop_loss_pct)}</span>
            </div>
            <div>
              <span className="muted">Objectif</span>
              <strong className="delta-up">{fmtPrice(lv.target)}</strong>
              <span className="muted">{formatPct(lv.target_pct)}</span>
            </div>
            <div>
              <span className="muted">Gain / risque</span>
              <strong>{lv.risk_reward === null ? "—" : formatNumber(lv.risk_reward, 2)}</strong>
            </div>
            <div>
              <span className="muted">Stop suiveur</span>
              <strong>{fmtPrice(lv.trailing_stop)}</strong>
            </div>
            <div>
              <span className="muted">Taille de position</span>
              <strong>{lv.position_size === null ? "—" : `${lv.position_size} titre(s)`}</strong>
              <span className="muted">risque max {formatNumber(lv.risk_amount, 0)} ({lv.risk_pct} % de {formatNumber(lv.capital, 0)})</span>
            </div>
            <div>
              <span className="muted">Supports</span>
              <strong>{lv.supports.length ? lv.supports.map((s) => fmtPrice(s)).join(" · ") : "—"}</strong>
            </div>
            <div>
              <span className="muted">Résistances</span>
              <strong>{lv.resistances.length ? lv.resistances.map((s) => fmtPrice(s)).join(" · ") : "—"}</strong>
            </div>
            <div>
              <span className="muted">Fourchette 1 an</span>
              <strong>
                {fmtPrice(lv.low_52w)} – {fmtPrice(lv.high_52w)}
              </strong>
            </div>
          </div>
          <p className="muted">
            {lv.method}. Le stop dit où la thèse est invalidée ; la taille de position fait que ce stop, s'il est touché, ne coûte que {lv.risk_pct} % du capital. Ce sont des repères de méthode, pas des ordres.
          </p>
        </div>
      )}

      <div className="card">
        <div className="card-header">
          <h4>Cette méthode a-t-elle marché sur ce titre ?</h4>
          <div className="inline-form">
            <label>
              Horizon
              <select value={pastHorizon} onChange={(e) => setPastHorizon(Number(e.target.value))}>
                <option value={5}>5 jours</option>
                <option value={10}>10 jours</option>
                <option value={20}>20 jours</option>
                <option value={60}>60 jours</option>
              </select>
            </label>
            <button type="button" className="export-button" onClick={runPast} disabled={pastLoading}>
              {pastLoading ? "Calcul…" : "Tester sur le passé"}
            </button>
          </div>
        </div>
        <p className="muted">À chaque date passée, le bilan court terme est recalculé avec les seules données d'alors, puis comparé à ce que le cours a fait ensuite. Le test le plus honnête qu'on puisse faire — et souvent décevant.</p>
        {past && (
          <>
            <p>{past.text}</p>
            {past.evaluations > 0 && (
              <>
                <div className="table-scroll">
                  <table>
                    <thead>
                      <tr>
                        <th>Le bilan disait</th>
                        <th>Fois</th>
                        <th>Avait raison</th>
                        <th>Rendement moyen à {past.horizon_days} j</th>
                        <th>Médian</th>
                        <th>Pire</th>
                        <th>Meilleur</th>
                      </tr>
                    </thead>
                    <tbody>
                      {past.by_orientation.map((b) => (
                        <tr key={b.orientation}>
                          <td>
                            <OrientationBadge orientation={b.orientation} label={b.label} />
                          </td>
                          <td>{b.count}</td>
                          <td>{b.hit_rate === null ? "—" : formatPct(b.hit_rate, 0)}</td>
                          <td className={b.mean_return === null ? undefined : b.mean_return >= 0 ? "delta-up" : "delta-down"}>{formatPct(b.mean_return)}</td>
                          <td>{formatPct(b.median_return)}</td>
                          <td>{formatPct(b.worst)}</td>
                          <td>{formatPct(b.best)}</td>
                        </tr>
                      ))}
                      <tr className="row-highlight">
                        <td>Référence : n'importe quand</td>
                        <td>{past.evaluations}</td>
                        <td>{formatPct(past.baseline_hit_rate, 0)}</td>
                        <td>{formatPct(past.baseline_mean_return)}</td>
                        <td colSpan={3} />
                      </tr>
                    </tbody>
                  </table>
                </div>
                <LineChart
                  series={[
                    { label: "Cours", color: "#4b5563", points: past.timeline.map((p) => ({ x: new Date(p.as_of), y: p.close })) },
                    { label: "Bilan « achat »", color: "#166534", points: past.timeline.filter((p) => p.orientation === "achat").map((p) => ({ x: new Date(p.as_of), y: p.close })) , width: 3 },
                    { label: "Bilan « vente »", color: "#991b1b", points: past.timeline.filter((p) => p.orientation === "vente").map((p) => ({ x: new Date(p.as_of), y: p.close })), width: 3 },
                  ]}
                  yFormatter={(v) => formatNumber(v, 2)}
                  height={220}
                  ariaLabel="Orientation du bilan dans le temps"
                />
                <p className="muted">Segments verts : périodes où le bilan disait « achat » ; rouges : « vente ». {past.method}</p>
              </>
            )}
          </>
        )}
      </div>

      <div className="card">
        <div className="card-header">
          <h4>Prévision statistique (expérimental)</h4>
          <button type="button" className="export-button" onClick={runPrediction} disabled={predLoading}>
            {predLoading ? "Entraînement… (quelques secondes)" : experiment ? "Relancer" : "Lancer une prévision à 5 jours"}
          </button>
        </div>
        <p className="muted">Un métamodèle (ridge, forêt aléatoire, gradient boosting) entraîné sur ce titre et validé sur son propre passé. Il n'entre dans le bilan ci-dessus que s'il a fait mieux que « aucun changement » hors échantillon.</p>
        {experiment && experiment.status === "completed" && experiment.latest_forecast && <ForecastSummary experiment={experiment} />}
        {experiment && experiment.status === "failed" && <p className="error-state">Échec : {experiment.error}</p>}
        {experiment && (
          <p className="muted">
            <a href={href("prediction")}>Détails, autres horizons et modèles dans le laboratoire de prédiction</a>
          </p>
        )}
      </div>

      <h4>Toutes les lectures</h4>
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
          Fondamentaux {f.status === "stale" ? "servis depuis le cache" : "indisponibles"} ({f.reason?.replaceAll("_", " ")}).
        </p>
      )}
      {f.status === "not_supported" && <p className="muted">Pas de fondamentaux pour ce type d'instrument : seules les lectures de cours et de risque s'appliquent.</p>}
      <div className="toolbar">
        <span className="muted">
          {aid.observations} clôtures{aid.price_source ? ` (${aid.price_source})` : ""}
          {f.as_of ? ` · fondamentaux ${f.source} du ${formatDateTime(f.as_of)}` : ""}
          {aid.news_last_7_days > 0 ? ` · ${aid.news_last_7_days} actualité(s) sur 7 jours` : ""}
          {aid.prediction_available ? " · prédiction incluse" : ""}
        </span>
        {horizon !== "all" && (
          <button type="button" className="link-button" onClick={() => setHorizon("all")}>
            Voir toutes les lectures
          </button>
        )}
      </div>
      <SignalTable signals={visible} showHorizon={horizon === "all"} />
      <p className="muted">
        Vue d'ensemble : {aid.overall} <ReadingBadge reading={aid.tally.available === 0 ? "indisponible" : "neutre"} compact />
      </p>
      {f.license_note && <p className="muted attribution">{f.license_note}</p>}
      <EducationNote slug="acheter-ou-vendre" />
    </section>
  );
}

/** Forecast card + the model's own test on the past: hit rate and what
 * following its direction would have given versus holding. */
export function ForecastSummary({ experiment }: { experiment: Experiment }) {
  const fc = experiment.latest_forecast!;
  const meta = experiment.metrics.models?.meta;
  const naive = experiment.metrics.models?.naive_last;
  const beats = !!meta && !!naive && meta.mae < naive.mae;
  const preds = experiment.predictions;
  const h = Number(experiment.config.horizon ?? fc.horizon);
  // Non-overlapping approximation: take one prediction every h dates.
  let strat = 0;
  let hold = 0;
  const stratPts: { x: Date; y: number }[] = [];
  const holdPts: { x: Date; y: number }[] = [];
  for (let i = 0; i < preds.length; i += h) {
    const p = preds[i];
    const actual = Number(p.actual);
    const dir = Math.sign(Number(p.meta));
    strat += dir > 0 ? actual : 0; // long only: invested when the model expects a rise
    hold += actual;
    stratPts.push({ x: new Date(String(p.date)), y: Math.exp(strat) });
    holdPts.push({ x: new Date(String(p.date)), y: Math.exp(hold) });
  }
  const expected = Math.exp(fc.expected_log_return) - 1;
  return (
    <div>
      <div className="levels-grid">
        <div>
          <span className="muted">Rendement attendu à {fc.horizon} j</span>
          <strong className={expected >= 0 ? "delta-up" : "delta-down"}>{formatPct(expected)}</strong>
        </div>
        <div>
          <span className="muted">Prix impliqué</span>
          <strong>{formatNumber(fc.implied_price, 2)}</strong>
          <span className="muted">
            intervalle {formatPct(fc.interval_confidence, 0)} : {formatNumber(fc.implied_price_interval[0], 2)} – {formatNumber(fc.implied_price_interval[1], 2)}
          </span>
        </div>
        <div>
          <span className="muted">Bonne direction (hors échantillon)</span>
          <strong>{meta ? formatPct(meta.direction_accuracy, 0) : "—"}</strong>
        </div>
        <div>
          <span className="muted">Mieux que « aucun changement » ?</span>
          <strong className={beats ? "delta-up" : "delta-down"}>{beats ? "oui" : "non"}</strong>
          <span className="muted">{meta?.rmse_vs_naive ? `RMSE/naïf ${formatNumber(meta.rmse_vs_naive, 2)}` : ""}</span>
        </div>
      </div>
      {stratPts.length > 3 && (
        <>
          <LineChart
            series={[
              { label: "Suivre le modèle (investi quand il prévoit une hausse)", color: "#1d4ed8", points: stratPts, width: 2 },
              { label: "Rester investi", color: "#a33a00", points: holdPts, dashed: true },
            ]}
            yFormatter={(v) => v.toFixed(2)}
            height={200}
            ariaLabel="Test du modèle sur le passé"
          />
          <p className="muted">
            Test sur le passé : {preds.length} prédictions hors échantillon, une prise en compte tous les {h} jours, sans frais ni glissement. Illustration de ce que le modèle a « vu » — pas une promesse.
          </p>
        </>
      )}
      <p className="muted">{fc.disclaimer}</p>
    </div>
  );
}
