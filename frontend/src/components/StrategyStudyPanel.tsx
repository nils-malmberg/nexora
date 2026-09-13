import { useState } from "react";
import { errorMessage, getStrategyStudy } from "../api/client";
import { LineChart } from "../charts/LineChart";
import { exportAsCsv } from "../csvExport";
import { formatDate, formatNumber, formatPct } from "../format";
import type { Instrument, ReturnStats, StrategyRule, StrategyStudy } from "../types";
import { STRATEGY_RULES, STRATEGY_RULE_LABELS } from "../types";
import { EducationNote } from "./EducationNote";

/** Educational backtest of a mechanical rule on one instrument, against
 * buy-and-hold. Signals are applied the next day, fees are charged on every
 * switch; the result describes the past under stated parameters — never a
 * signal or a recommendation. */
export function StrategyStudyPanel({ instrument }: { instrument: Instrument }) {
  const [rule, setRule] = useState<StrategyRule>("sma_cross");
  const [days, setDays] = useState(730);
  const [fast, setFast] = useState(20);
  const [slow, setSlow] = useState(50);
  const [rsiPeriod, setRsiPeriod] = useState(14);
  const [rsiLow, setRsiLow] = useState(30);
  const [rsiHigh, setRsiHigh] = useState(70);
  const [feeBps, setFeeBps] = useState(10);
  const [study, setStudy] = useState<StrategyStudy | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run() {
    setLoading(true);
    setError(null);
    try {
      setStudy(await getStrategyStudy(instrument.id, { rule, days, fast, slow, rsi_period: rsiPeriod, rsi_low: rsiLow, rsi_high: rsiHigh, fee_bps: feeBps }));
    } catch (err) {
      setError(errorMessage(err, "Étude impossible"));
    } finally {
      setLoading(false);
    }
  }

  const rows: [string, (s: ReturnStats) => string][] = [
    ["Rendement total", (s) => formatPct(s.total_return)],
    ["Rendement annualisé (CAGR)", (s) => formatPct(s.cagr)],
    ["Volatilité annualisée", (s) => formatPct(s.volatility_annualized)],
    ["Drawdown maximal", (s) => formatPct(s.max_drawdown)],
    ["Sharpe", (s) => formatNumber(s.sharpe, 2)],
    ["Sortino", (s) => formatNumber(s.sortino, 2)],
    ["Calmar", (s) => formatNumber(s.calmar, 2)],
    ["Pire jour", (s) => formatPct(s.worst_period)],
  ];

  return (
    <section aria-label="Étude de stratégie">
      <h3>Étude de stratégie (backtest pédagogique)</h3>
      <p className="muted">
        Qu'aurait donné une règle mécanique sur {instrument.symbol}, comparée à « acheter et conserver » ? Signal sur la clôture du jour, position appliquée le lendemain, frais à chaque passage. Une description du passé sous des paramètres choisis — pas un signal.
      </p>
      <div className="inline-form">
        <label>
          Règle
          <select value={rule} onChange={(e) => setRule(e.target.value as StrategyRule)}>
            {STRATEGY_RULES.map((r) => (
              <option key={r} value={r}>
                {STRATEGY_RULE_LABELS[r]}
              </option>
            ))}
          </select>
        </label>
        <label>
          Fenêtre
          <select value={days} onChange={(e) => setDays(Number(e.target.value))}>
            <option value={365}>1 an</option>
            <option value={730}>2 ans</option>
            <option value={1825}>5 ans</option>
            <option value={3650}>10 ans</option>
          </select>
        </label>
        {rule === "sma_cross" && (
          <label>
            SMA rapide
            <input type="number" min={2} max={200} value={fast} onChange={(e) => setFast(Number(e.target.value) || 2)} style={{ width: 70 }} />
          </label>
        )}
        {rule !== "rsi_reversion" && (
          <label>
            SMA lente
            <input type="number" min={3} max={400} value={slow} onChange={(e) => setSlow(Number(e.target.value) || 3)} style={{ width: 70 }} />
          </label>
        )}
        {rule === "rsi_reversion" && (
          <>
            <label>
              RSI
              <input type="number" min={2} max={100} value={rsiPeriod} onChange={(e) => setRsiPeriod(Number(e.target.value) || 2)} style={{ width: 60 }} />
            </label>
            <label>
              Seuil bas
              <input type="number" min={1} max={50} value={rsiLow} onChange={(e) => setRsiLow(Number(e.target.value) || 1)} style={{ width: 60 }} />
            </label>
            <label>
              Seuil haut
              <input type="number" min={50} max={99} value={rsiHigh} onChange={(e) => setRsiHigh(Number(e.target.value) || 50)} style={{ width: 60 }} />
            </label>
          </>
        )}
        <label>
          Frais (points de base)
          <input type="number" min={0} max={500} value={feeBps} onChange={(e) => setFeeBps(Number(e.target.value) || 0)} style={{ width: 70 }} />
        </label>
        <button type="button" className="primary-button" onClick={run} disabled={loading || (rule === "sma_cross" && fast >= slow)}>
          {loading ? "Calcul…" : "Lancer l'étude"}
        </button>
      </div>
      {rule === "sma_cross" && fast >= slow && <p className="error-state">La SMA rapide doit être plus courte que la SMA lente.</p>}
      {error && <p className="error-state">{error}</p>}

      {study && !study.has_sufficient_data && <p className="empty-state">Pas assez d'historique ({study.observations} clôtures) pour cette règle et ces paramètres.</p>}
      {study && study.has_sufficient_data && (
        <>
          <p className="prediction-warning" role="note">
            {study.disclaimer}
          </p>
          <LineChart
            series={[
              { label: "Règle", color: "#1d4ed8", points: study.dates.map((d, i) => ({ x: new Date(d), y: study.strategy_equity[i] })), width: 2 },
              { label: "Acheter et conserver", color: "#a33a00", points: study.dates.map((d, i) => ({ x: new Date(d), y: study.benchmark_equity[i] })), dashed: true },
            ]}
            yFormatter={(v) => v.toFixed(2)}
            height={280}
            ariaLabel="Valeur de la règle contre acheter et conserver (base 1)"
          />
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Mesure</th>
                  <th>Règle</th>
                  <th>Acheter et conserver</th>
                </tr>
              </thead>
              <tbody>
                {study.strategy_stats &&
                  study.benchmark_stats &&
                  rows.map(([label, fn]) => (
                    <tr key={label}>
                      <td>{label}</td>
                      <td>{fn(study.strategy_stats!)}</td>
                      <td>{fn(study.benchmark_stats!)}</td>
                    </tr>
                  ))}
                <tr>
                  <td>Passages (entrées/sorties)</td>
                  <td>{study.n_trades}</td>
                  <td>1</td>
                </tr>
                <tr>
                  <td>Exposition (part du temps investi)</td>
                  <td>{formatPct(study.exposure_share, 0)}</td>
                  <td>100 %</td>
                </tr>
                <tr>
                  <td>Passages gagnants</td>
                  <td>{study.win_rate === null ? "—" : formatPct(study.win_rate, 0)}</td>
                  <td>—</td>
                </tr>
              </tbody>
            </table>
          </div>
          <p className="muted">
            {study.observations} clôtures · frais {study.fee_bps} pb par changement de position · {study.method}
          </p>
          {study.trades.length > 0 && (
            <details>
              <summary>Détail des {study.trades.length} passage(s)</summary>
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>Entrée</th>
                      <th>Sortie</th>
                      <th>Prix d'entrée</th>
                      <th>Prix de sortie</th>
                      <th>Rendement net</th>
                      <th>Durée</th>
                    </tr>
                  </thead>
                  <tbody>
                    {study.trades.map((t, i) => (
                      <tr key={i}>
                        <td>{formatDate(t.entry_date)}</td>
                        <td>{t.exit_date ? formatDate(t.exit_date) : "en cours"}</td>
                        <td>{formatNumber(t.entry_price, 2)}</td>
                        <td>{t.exit_price === null ? "—" : formatNumber(t.exit_price, 2)}</td>
                        <td className={t.return_pct === null ? undefined : t.return_pct >= 0 ? "delta-up" : "delta-down"}>{t.return_pct === null ? "—" : formatPct(t.return_pct)}</td>
                        <td>{t.holding_days === null ? "—" : `${t.holding_days} j`}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </details>
          )}
          <button
            type="button"
            className="export-button"
            onClick={() =>
              exportAsCsv(
                `nexora-strategie-${instrument.symbol}-${study.rule}.csv`,
                study.dates.map((d, i) => ({ date: d, regle: study.strategy_equity[i], acheter_conserver: study.benchmark_equity[i], investi: study.invested[i] })),
              )
            }
          >
            Exporter les courbes (CSV)
          </button>
        </>
      )}
      <EducationNote slug="etude-de-strategie" />
    </section>
  );
}
