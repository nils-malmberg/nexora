import { useEffect, useState } from "react";
import {
  ApiError,
  getAllocation,
  getHistory,
  getIndicators,
  getPerformance,
  getRisk,
} from "../api/client";
import { AllocationBar } from "../charts/AllocationBar";
import { LineChart, type ChartPoint } from "../charts/LineChart";
import { EducationNote } from "./EducationNote";
import { exportAsCsv } from "../csvExport";
import { exportAsJson } from "../export";
import { formatAmount, formatDate } from "../format";
import type { Allocation, History, Indicators, Instrument, Performance, Risk } from "../types";

function toPoints(dates: string[], values: (string | null)[]): ChartPoint[] {
  const points: ChartPoint[] = [];
  dates.forEach((d, i) => {
    const v = values[i];
    if (v !== null && v !== undefined) points.push({ x: new Date(d), y: Number(v) });
  });
  return points;
}

function pct(value: string | null): string {
  return value === null ? "—" : `${(Number(value) * 100).toFixed(2)} %`;
}

export function AnalyticsSection({
  portfolioId,
  instruments,
  refreshKey = 0,
}: {
  portfolioId: string;
  instruments: Instrument[];
  /** Bump this from the parent whenever a transaction or price changes
   * elsewhere on the page - this section has its own data and otherwise
   * has no way to know it's gone stale. */
  refreshKey?: number;
}) {
  const [history, setHistory] = useState<History | null>(null);
  const [allocation, setAllocation] = useState<Allocation | null>(null);
  const [risk, setRisk] = useState<Risk | null>(null);
  const [performance, setPerformance] = useState<Performance | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedInstrumentId, setSelectedInstrumentId] = useState("");
  const [indicators, setIndicators] = useState<Indicators | null>(null);

  useEffect(() => {
    Promise.all([getHistory(portfolioId), getAllocation(portfolioId), getRisk(portfolioId), getPerformance(portfolioId)])
      .then(([h, a, r, p]) => {
        setHistory(h);
        setAllocation(a);
        setRisk(r);
        setPerformance(p);
      })
      .catch((err: unknown) => setError(err instanceof ApiError ? err.message : "Erreur de chargement"));
  }, [portfolioId, refreshKey]);

  useEffect(() => {
    if (!selectedInstrumentId) {
      setIndicators(null);
      return;
    }
    getIndicators(selectedInstrumentId)
      .then(setIndicators)
      .catch(() => setIndicators(null));
  }, [selectedInstrumentId, refreshKey]);

  return (
    <section aria-label="Analyse">
      <h3>Analyse</h3>
      {error && <p className="error-state">{error}</p>}

      <h4>Historique de valeur</h4>
      {history && history.points.length > 0 ? (
        <>
          <LineChart
            series={[
              {
                label: "Valeur totale",
                color: "#1d4ed8",
                points: history.points.map((p) => ({ x: new Date(p.as_of), y: Number(p.total_value) })),
              },
            ]}
            yFormatter={(v) => formatAmount(String(v), history.base_currency)}
          />
          <div className="toolbar">
            <button
              type="button"
              className="export-button"
              onClick={() =>
                exportAsCsv(
                  `nexora-historique-${portfolioId}.csv`,
                  history.points.map((p) => ({
                    date: p.as_of,
                    cash: p.cash,
                    positions_value: p.positions_value,
                    total_value: p.total_value,
                  })),
                )
              }
            >
              Exporter (CSV)
            </button>
            <button
              type="button"
              className="export-button"
              onClick={() => exportAsJson(`nexora-historique-${portfolioId}.json`, history)}
            >
              Exporter (JSON)
            </button>
          </div>
        </>
      ) : (
        <p className="empty-state">Pas encore assez de données pour un historique.</p>
      )}
      <EducationNote slug="valorisation" />

      <h4>Répartition (hors trésorerie)</h4>
      {allocation && <AllocationBar slices={allocation.by_asset_class} />}
      {allocation && allocation.unconverted_currencies.length > 0 && (
        <p className="prediction-warning" role="note">
          Devises non converties, exclues de la répartition : {allocation.unconverted_currencies.join(", ")}.
        </p>
      )}
      <EducationNote slug="allocation" />

      <h4>Risque descriptif</h4>
      {risk &&
        (risk.has_sufficient_data ? (
          <p>
            Volatilité annualisée : <strong>{pct(risk.volatility_annualized)}</strong> — Repli maximum :{" "}
            <strong>{pct(risk.max_drawdown)}</strong> ({risk.observations} observations).
          </p>
        ) : (
          <p className="empty-state">
            Historique insuffisant pour calculer ces indicateurs ({risk.observations} observation(s)).
          </p>
        ))}
      <EducationNote slug="volatilite-drawdown" />

      <h4>Performance (TWR / MWR)</h4>
      {performance &&
        (performance.has_sufficient_data ? (
          <p>
            TWR : <strong>{pct(performance.twr)}</strong>
            {performance.mwr !== null && (
              <>
                {" "}
                — MWR (IRR) : <strong>{pct(performance.mwr)}</strong>
              </>
            )}{" "}
            du {formatDate(performance.start)} au {formatDate(performance.end)}, en {performance.base_currency}.
          </p>
        ) : (
          <p className="empty-state">Historique insuffisant pour calculer la performance sur cette période.</p>
        ))}
      <EducationNote slug="twr-mwr" />

      <h4>Indicateurs techniques</h4>
      <label>
        Instrument
        <select value={selectedInstrumentId} onChange={(e) => setSelectedInstrumentId(e.target.value)}>
          <option value="">— choisir —</option>
          {instruments.map((i) => (
            <option key={i.id} value={i.id}>
              {i.symbol}
            </option>
          ))}
        </select>
      </label>
      {indicators && indicators.prices.length > 0 && (
        <>
          <LineChart
            series={[
              { label: "Prix", color: "#1d4ed8", points: toPoints(indicators.dates, indicators.prices) },
              {
                label: `SMA(${indicators.sma_window})`,
                color: "#a33a00",
                points: toPoints(indicators.dates, indicators.sma),
              },
              {
                label: `EMA(${indicators.ema_window})`,
                color: "#1f7a3d",
                points: toPoints(indicators.dates, indicators.ema),
              },
            ]}
          />
          <LineChart
            series={[
              {
                label: `RSI(${indicators.rsi_window})`,
                color: "#7c3aed",
                points: toPoints(indicators.dates, indicators.rsi),
              },
            ]}
            height={120}
          />
          <LineChart
            series={[
              { label: "MACD", color: "#1d4ed8", points: toPoints(indicators.dates, indicators.macd) },
              { label: "Signal", color: "#a33a00", points: toPoints(indicators.dates, indicators.macd_signal) },
            ]}
            height={120}
          />
          <button
            type="button"
            className="export-button"
            onClick={() =>
              exportAsCsv(
                `nexora-indicateurs-${selectedInstrumentId}.csv`,
                indicators.dates.map((d, i) => ({
                  date: d,
                  prix: indicators.prices[i],
                  sma: indicators.sma[i],
                  ema: indicators.ema[i],
                  rsi: indicators.rsi[i],
                  macd: indicators.macd[i],
                  macd_signal: indicators.macd_signal[i],
                })),
              )
            }
          >
            Exporter (CSV)
          </button>
        </>
      )}
      {selectedInstrumentId && indicators && indicators.prices.length === 0 && (
        <p className="empty-state">Aucun prix enregistré pour cet instrument.</p>
      )}
      <EducationNote slug="indicateurs-techniques" />
    </section>
  );
}
