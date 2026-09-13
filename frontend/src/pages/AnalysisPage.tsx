import { useEffect, useState } from "react";
import { errorMessage, getCorrelation, getFrontier, listInstruments, listPortfolios } from "../api/client";
import { Heatmap } from "../charts/Heatmap";
import { ScatterChart, type ScatterPoint } from "../charts/ScatterChart";
import { EducationNote } from "../components/EducationNote";
import { QuantPanel } from "../components/QuantPanel";
import { formatNumber, formatPct } from "../format";
import type { CorrelationResult, FrontierResult, Instrument, Portfolio } from "../types";

/** The analysis workbench: pick a portfolio or an instrument, then read
 * return/risk statistics, drawdown, VaR, CAPM and Monte Carlo (QuantPanel);
 * for a portfolio also the correlation matrix and the Markowitz frontier.
 * Everything is descriptive of the past or an explicit simulation. */
export function AnalysisPage({ initialPortfolioId, initialInstrumentId }: { initialPortfolioId?: string; initialInstrumentId?: string }) {
  const [portfolios, setPortfolios] = useState<Portfolio[]>([]);
  const [instruments, setInstruments] = useState<Instrument[]>([]);
  const [subjectKind, setSubjectKind] = useState<"portfolio" | "instrument">(initialInstrumentId ? "instrument" : "portfolio");
  const [portfolioId, setPortfolioId] = useState(initialPortfolioId ?? "");
  const [instrumentId, setInstrumentId] = useState(initialInstrumentId ?? "");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([listPortfolios(), listInstruments()])
      .then(([p, i]) => {
        setPortfolios(p);
        setInstruments(i);
        if (!portfolioId && p.length > 0) setPortfolioId(p[0].id);
        if (!instrumentId && i.length > 0) setInstrumentId(i[0].id);
      })
      .catch((err: unknown) => setError(errorMessage(err)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const portfolio = portfolios.find((p) => p.id === portfolioId);
  const instrument = instruments.find((i) => i.id === instrumentId);

  return (
    <section aria-label="Analyse">
      <h2>Analyse quantitative</h2>
      <p className="muted">
        Statistiques de rendement et de risque, Value-at-Risk, MEDAF, corrélations, frontière efficiente de Markowitz et simulations de Monte Carlo. Chaque mesure indique sa méthode, sa période et ses limites — et renvoie vers l'aide. Rien ici n'est une recommandation.
      </p>
      {error && <p className="error-state">{error}</p>}
      <div className="inline-form">
        <label className="inline-check">
          <input type="radio" checked={subjectKind === "portfolio"} onChange={() => setSubjectKind("portfolio")} /> Portefeuille
        </label>
        <label className="inline-check">
          <input type="radio" checked={subjectKind === "instrument"} onChange={() => setSubjectKind("instrument")} /> Instrument
        </label>
        {subjectKind === "portfolio" ? (
          <select value={portfolioId} onChange={(e) => setPortfolioId(e.target.value)} aria-label="Portefeuille">
            {portfolios.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name} ({p.base_currency})
              </option>
            ))}
          </select>
        ) : (
          <select value={instrumentId} onChange={(e) => setInstrumentId(e.target.value)} aria-label="Instrument">
            {instruments.map((i) => (
              <option key={i.id} value={i.id}>
                {i.symbol} — {i.name}
              </option>
            ))}
          </select>
        )}
      </div>

      {subjectKind === "portfolio" && portfolio && (
        <>
          <QuantPanel subject={{ portfolio_id: portfolio.id }} currency={portfolio.base_currency} label={portfolio.name} />
          <PortfolioTheory portfolioId={portfolio.id} />
        </>
      )}
      {subjectKind === "instrument" && instrument && <QuantPanel subject={{ instrument_id: instrument.id }} currency={instrument.currency} label={instrument.symbol} />}
      {subjectKind === "portfolio" && !portfolio && <p className="empty-state">Créez d'abord un portefeuille.</p>}
      {subjectKind === "instrument" && !instrument && <p className="empty-state">Suivez ou détenez d'abord un instrument.</p>}
    </section>
  );
}

function PortfolioTheory({ portfolioId }: { portfolioId: string }) {
  const [days, setDays] = useState(365);
  const [riskFree, setRiskFree] = useState("0");
  const [correlation, setCorrelation] = useState<CorrelationResult | null>(null);
  const [frontier, setFrontier] = useState<FrontierResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function compute() {
    setLoading(true);
    setError(null);
    try {
      const [c, f] = await Promise.all([getCorrelation(portfolioId, days), getFrontier(portfolioId, days, Number(riskFree) || 0)]);
      setCorrelation(c);
      setFrontier(f);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  const points: ScatterPoint[] = [];
  if (frontier?.has_sufficient_data) {
    frontier.frontier.forEach((p, i) => points.push({ x: p.volatility, y: p.expected_return, label: `Frontière ${i + 1}`, kind: "frontier" }));
    frontier.labels.forEach((l, i) => points.push({ x: frontier.volatilities[i], y: frontier.expected_returns[i], label: l, kind: "asset" }));
    if (frontier.min_variance) points.push({ x: frontier.min_variance.volatility, y: frontier.min_variance.expected_return, label: "Variance min.", kind: "special", color: "#7c3aed" });
    if (frontier.max_sharpe) points.push({ x: frontier.max_sharpe.volatility, y: frontier.max_sharpe.expected_return, label: "Sharpe max.", kind: "special", color: "#a33a00" });
    if (frontier.equal_weight) points.push({ x: frontier.equal_weight.volatility, y: frontier.equal_weight.expected_return, label: "Équipondéré", kind: "special", color: "#0891b2" });
    if (frontier.current) points.push({ x: frontier.current.volatility, y: frontier.current.expected_return, label: "Actuel", kind: "special", color: "#be185d" });
  }

  return (
    <section aria-label="Théorie du portefeuille">
      <h3>Corrélations et frontière efficiente</h3>
      <div className="inline-form">
        <label>
          Fenêtre
          <select value={days} onChange={(e) => setDays(Number(e.target.value))}>
            <option value={180}>6 mois</option>
            <option value={365}>1 an</option>
            <option value={730}>2 ans</option>
            <option value={1825}>5 ans</option>
          </select>
        </label>
        <label>
          Taux sans risque
          <input type="number" step="0.001" value={riskFree} onChange={(e) => setRiskFree(e.target.value)} />
        </label>
        <button type="button" className="primary-button" onClick={compute} disabled={loading}>
          {loading ? "Calcul…" : "Calculer"}
        </button>
      </div>
      {error && <p className="error-state">{error}</p>}
      {correlation && (
        <>
          <h4>Matrice de corrélation</h4>
          {correlation.has_sufficient_data ? (
            <>
              <Heatmap labels={correlation.labels} matrix={correlation.matrix} />
              <p className="muted">
                {correlation.observations} dates communes · {correlation.method}
              </p>
            </>
          ) : (
            <p className="empty-state">Pas assez d'historique commun ({correlation.observations} dates) ou moins de deux positions.</p>
          )}
          <EducationNote slug="correlation-diversification" />
        </>
      )}
      {frontier && (
        <>
          <h4>Frontière efficiente (Markowitz)</h4>
          {frontier.has_sufficient_data ? (
            <>
              <p className="prediction-warning" role="note">
                {frontier.disclaimer}
              </p>
              <ScatterChart points={points} />
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>Portefeuille</th>
                      <th>Rendement attendu</th>
                      <th>Volatilité</th>
                      <th>Sharpe</th>
                      {frontier.labels.map((l) => (
                        <th key={l}>{l}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {(
                      [
                        ["Actuel", frontier.current],
                        ["Variance minimale", frontier.min_variance],
                        ["Sharpe maximal", frontier.max_sharpe],
                        ["Équipondéré", frontier.equal_weight],
                      ] as const
                    )
                      .filter(([, p]) => p !== null)
                      .map(([name, p]) => (
                        <tr key={name}>
                          <td>{name}</td>
                          <td>{formatPct(p!.expected_return)}</td>
                          <td>{formatPct(p!.volatility)}</td>
                          <td>{formatNumber(p!.sharpe, 2)}</td>
                          {p!.weights.map((w, i) => (
                            <td key={i}>{formatPct(w, 0)}</td>
                          ))}
                        </tr>
                      ))}
                  </tbody>
                </table>
              </div>
              <p className="muted">
                {frontier.observations} rendements quotidiens · taux sans risque {formatPct(frontier.risk_free_rate)} · {frontier.method}
              </p>
            </>
          ) : (
            <p className="empty-state">Il faut au moins deux positions avec ~3 mois d'historique commun ({frontier.observations} dates).</p>
          )}
          <EducationNote slug="markowitz" />
        </>
      )}
    </section>
  );
}
