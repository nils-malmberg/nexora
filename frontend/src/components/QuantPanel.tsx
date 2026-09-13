import { useEffect, useState } from "react";
import { errorMessage, getCapm, getDrawdown, getMonteCarlo, getReturnStats, getVar, listInstruments } from "../api/client";
import type { Subject } from "../api/client";
import { LineChart } from "../charts/LineChart";
import { formatAmount, formatNumber, formatPct } from "../format";
import type { CapmResult, Drawdown, Instrument, MonteCarloResult, ReturnStats, VarResult } from "../types";
import { EducationNote } from "./EducationNote";

const DAYS_OPTIONS = [
  { value: 90, label: "3 mois" },
  { value: 180, label: "6 mois" },
  { value: 365, label: "1 an" },
  { value: 730, label: "2 ans" },
  { value: 1825, label: "5 ans" },
];

function Stat({ label, value, title }: { label: string; value: string; title?: string }) {
  return (
    <div className="stat" title={title}>
      <span className="stat-label">{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

/** Return statistics, drawdown, VaR/CVaR, CAPM and a Monte Carlo fan for one
 * subject (a portfolio or an instrument). Every block states its method and
 * says explicitly when the sample is too short. */
export function QuantPanel({ subject, currency, label }: { subject: Subject; currency?: string | null; label: string }) {
  const [days, setDays] = useState(365);
  const [riskFree, setRiskFree] = useState("0");
  const [confidence, setConfidence] = useState("0.95");
  const [horizon, setHorizon] = useState("1");
  const [stats, setStats] = useState<ReturnStats | null>(null);
  const [drawdown, setDrawdown] = useState<Drawdown | null>(null);
  const [varResult, setVarResult] = useState<VarResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [instruments, setInstruments] = useState<Instrument[]>([]);
  const [benchmarkId, setBenchmarkId] = useState("");
  const [capm, setCapm] = useState<CapmResult | null>(null);
  const [mcHorizon, setMcHorizon] = useState("252");
  const [mcSims, setMcSims] = useState("2000");
  const [mcSeed, setMcSeed] = useState("42");
  const [monteCarlo, setMonteCarlo] = useState<MonteCarloResult | null>(null);
  const [mcLoading, setMcLoading] = useState(false);

  const subjectKey = subject.portfolio_id ?? subject.instrument_id ?? "";

  useEffect(() => {
    let cancelled = false;
    setError(null);
    const rf = Number(riskFree) || 0;
    Promise.all([
      getReturnStats(subject, days, rf),
      getDrawdown(subject, days),
      getVar(subject, Math.max(days, 60), Number(confidence) || 0.95, Number(horizon) || 1),
    ])
      .then(([s, d, v]) => {
        if (cancelled) return;
        setStats(s);
        setDrawdown(d);
        setVarResult(v);
      })
      .catch((err: unknown) => !cancelled && setError(errorMessage(err)));
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [subjectKey, days, riskFree, confidence, horizon]);

  useEffect(() => {
    listInstruments()
      .then((list) => setInstruments(list.filter((i) => i.id !== subject.instrument_id)))
      .catch(() => setInstruments([]));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [subjectKey]);

  useEffect(() => {
    if (!benchmarkId) {
      setCapm(null);
      return;
    }
    let cancelled = false;
    getCapm(subject, benchmarkId, Math.max(days, 60), Number(riskFree) || 0)
      .then((c) => !cancelled && setCapm(c))
      .catch((err: unknown) => !cancelled && setError(errorMessage(err)));
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [subjectKey, benchmarkId, days, riskFree]);

  async function runMonteCarlo() {
    setMcLoading(true);
    setError(null);
    try {
      setMonteCarlo(await getMonteCarlo(subject, Math.max(days, 60), Number(mcHorizon) || 252, Number(mcSims) || 2000, Number(mcSeed) || 42));
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setMcLoading(false);
    }
  }

  const ccy = currency ?? stats?.currency ?? undefined;
  const money = (v: number) => formatAmount(v, ccy);

  return (
    <section className="quant-panel" aria-label={`Analyse quantitative — ${label}`}>
      <div className="inline-form">
        <label>
          Fenêtre
          <select value={days} onChange={(e) => setDays(Number(e.target.value))}>
            {DAYS_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </label>
        <label>
          Taux sans risque (annuel)
          <input type="number" step="0.001" min="-0.05" max="0.2" value={riskFree} onChange={(e) => setRiskFree(e.target.value)} />
        </label>
      </div>
      {error && <p className="error-state">{error}</p>}

      <h4>Rendement et risque</h4>
      {stats &&
        (stats.has_sufficient_data ? (
          <>
            <div className="stat-grid">
              <Stat label="Rendement total" value={formatPct(stats.total_return)} />
              <Stat label="CAGR" value={formatPct(stats.cagr)} title="Taux de croissance annuel composé" />
              <Stat label="Rendement moyen annualisé" value={formatPct(stats.mean_return_annualized)} />
              <Stat label="Volatilité annualisée" value={formatPct(stats.volatility_annualized)} />
              <Stat label="Déviation à la baisse" value={formatPct(stats.downside_deviation_annualized)} />
              <Stat label="Repli maximum" value={formatPct(stats.max_drawdown)} />
              <Stat label="Sharpe" value={formatNumber(stats.sharpe, 2)} />
              <Stat label="Sortino" value={formatNumber(stats.sortino, 2)} />
              <Stat label="Calmar" value={formatNumber(stats.calmar, 2)} />
              <Stat label="Asymétrie" value={formatNumber(stats.skewness, 2)} />
              <Stat label="Kurtosis (excès)" value={formatNumber(stats.kurtosis_excess, 2)} />
              <Stat label="Jours positifs" value={formatPct(stats.positive_period_share, 0)} />
              <Stat label="Meilleur / pire jour" value={`${formatPct(stats.best_period)} / ${formatPct(stats.worst_period)}`} />
            </div>
            <p className="muted">
              {stats.observations} observations quotidiennes · {stats.periods_per_year} périodes/an · taux sans risque {formatPct(stats.risk_free_rate)} · {stats.method}
            </p>
          </>
        ) : (
          <p className="empty-state">Historique insuffisant ({stats.observations} observations) pour ces statistiques.</p>
        ))}
      <EducationNote slug="sharpe-sortino-calmar" />

      <h4>Courbe de repli (drawdown)</h4>
      {drawdown && drawdown.points.length > 1 ? (
        <LineChart
          series={[{ label: "Drawdown", color: "#b3261e", points: drawdown.points.map((p) => ({ x: new Date(p.as_of), y: p.drawdown })) }]}
          yFormatter={(v) => formatPct(v, 1)}
          yMax={0}
          height={160}
          ariaLabel="Courbe de repli"
        />
      ) : (
        <p className="empty-state">Pas assez de données.</p>
      )}
      <EducationNote slug="volatilite-drawdown" />

      <h4>Value-at-Risk</h4>
      <div className="inline-form">
        <label>
          Confiance
          <select value={confidence} onChange={(e) => setConfidence(e.target.value)}>
            <option value="0.9">90 %</option>
            <option value="0.95">95 %</option>
            <option value="0.99">99 %</option>
          </select>
        </label>
        <label>
          Horizon (jours)
          <input type="number" min="1" max="60" value={horizon} onChange={(e) => setHorizon(e.target.value)} />
        </label>
      </div>
      {varResult &&
        (varResult.has_sufficient_data ? (
          <>
            <div className="stat-grid">
              <Stat label="VaR historique" value={formatPct(varResult.historical_var)} />
              <Stat label="CVaR (Expected Shortfall)" value={formatPct(varResult.historical_cvar)} />
              <Stat label="VaR gaussienne" value={formatPct(varResult.gaussian_var)} />
              <Stat label="VaR Cornish-Fisher" value={formatPct(varResult.cornish_fisher_var)} />
              {varResult.current_value !== null && varResult.historical_var !== null && (
                <Stat label={`Perte VaR sur ${formatAmount(varResult.current_value, ccy)}`} value={money(varResult.current_value * varResult.historical_var)} />
              )}
            </div>
            <p className="muted">
              Pertes en fraction de la valeur courante, à {formatPct(varResult.confidence, 0)} sur {varResult.horizon_periods} jour(s), {varResult.observations} observations · {varResult.method}
            </p>
          </>
        ) : (
          <p className="empty-state">Historique insuffisant ({varResult.observations} observations) pour une VaR.</p>
        ))}
      <EducationNote slug="var-cvar" />

      <h4>MEDAF (CAPM) contre un indice de référence</h4>
      <div className="inline-form">
        <label>
          Benchmark
          <select value={benchmarkId} onChange={(e) => setBenchmarkId(e.target.value)}>
            <option value="">— choisir un instrument suivi —</option>
            {instruments.map((i) => (
              <option key={i.id} value={i.id}>
                {i.symbol} — {i.name}
              </option>
            ))}
          </select>
        </label>
      </div>
      {capm &&
        (capm.has_sufficient_data ? (
          <>
            <div className="stat-grid">
              <Stat label="Bêta" value={formatNumber(capm.beta, 3)} />
              <Stat label="Alpha annualisé" value={formatPct(capm.alpha_annualized)} />
              <Stat label="Corrélation" value={formatNumber(capm.correlation, 3)} />
              <Stat label="R²" value={formatNumber(capm.r_squared, 3)} />
              <Stat label="Tracking error" value={formatPct(capm.tracking_error_annualized)} />
              <Stat label="Ratio d'information" value={formatNumber(capm.information_ratio, 2)} />
            </div>
            <p className="muted">
              {capm.observations} dates communes avec {capm.benchmark} · {capm.method}
            </p>
          </>
        ) : (
          <p className="empty-state">Pas assez de dates communes ({capm.observations}) avec ce benchmark.</p>
        ))}
      {!benchmarkId && <p className="muted">Ajoutez un indice (ex. un ETF monde) à votre liste de suivi pour l'utiliser comme référence.</p>}
      <EducationNote slug="capm-beta" />

      <h4>Simulation de Monte Carlo</h4>
      <div className="inline-form">
        <label>
          Horizon (jours de cotation)
          <input type="number" min="5" max="1260" value={mcHorizon} onChange={(e) => setMcHorizon(e.target.value)} />
        </label>
        <label>
          Simulations
          <input type="number" min="100" max="10000" value={mcSims} onChange={(e) => setMcSims(e.target.value)} />
        </label>
        <label>
          Graine
          <input type="number" min="0" value={mcSeed} onChange={(e) => setMcSeed(e.target.value)} />
        </label>
        <button type="button" className="primary-button" onClick={runMonteCarlo} disabled={mcLoading}>
          {mcLoading ? "Simulation…" : "Simuler"}
        </button>
      </div>
      {monteCarlo &&
        (monteCarlo.has_sufficient_data ? (
          <>
            <p className="prediction-warning" role="note">
              {monteCarlo.disclaimer}
            </p>
            <MonteCarloFan result={monteCarlo} currency={ccy} />
            <div className="stat-grid">
              <Stat label="Dérive annualisée estimée" value={formatPct(monteCarlo.drift_annualized)} />
              <Stat label="Volatilité annualisée estimée" value={formatPct(monteCarlo.volatility_annualized)} />
              <Stat label="Probabilité de finir sous la valeur actuelle" value={formatPct(monteCarlo.probability_of_loss, 0)} />
              <Stat label="Valeur finale médiane" value={money(monteCarlo.terminal_percentiles["50"])} />
              <Stat label="Fourchette 5 % – 95 %" value={`${money(monteCarlo.terminal_percentiles["5"])} – ${money(monteCarlo.terminal_percentiles["95"])}`} />
            </div>
            <p className="muted">
              {monteCarlo.simulations} trajectoires, graine {monteCarlo.seed}, calibré sur {monteCarlo.observations} rendements · {monteCarlo.method}
            </p>
          </>
        ) : (
          <p className="empty-state">Historique insuffisant ({monteCarlo.observations} observations) pour calibrer une simulation.</p>
        ))}
      <EducationNote slug="monte-carlo" />
    </section>
  );
}

function MonteCarloFan({ result, currency }: { result: MonteCarloResult; currency?: string }) {
  const start = new Date();
  const day = (i: number) => new Date(start.getTime() + i * 86_400_000 * (365 / 252));
  const series = (key: string) => (result.percentiles[key] ?? []).map((v, i) => ({ x: day(i), y: v }));
  return (
    <LineChart
      series={[
        { label: "Médiane", color: "#1d4ed8", points: series("50"), width: 2 },
        { label: "5e percentile", color: "#b3261e", points: series("5"), dashed: true },
        { label: "95e percentile", color: "#1f7a3d", points: series("95"), dashed: true },
      ]}
      bands={[{ label: "25e – 75e percentiles", color: "#1d4ed8", upper: series("75"), lower: series("25") }]}
      yFormatter={(v) => formatAmount(v, currency, 0)}
      height={260}
      ariaLabel="Éventail de trajectoires simulées"
    />
  );
}
