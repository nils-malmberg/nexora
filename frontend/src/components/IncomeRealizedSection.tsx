import { useEffect, useState } from "react";
import { errorMessage, getIncome, getRealized } from "../api/client";
import { exportAsCsv } from "../csvExport";
import { formatAmount, formatDate, formatQuantity } from "../format";
import { href } from "../router";
import type { IncomeReport, RealizedReport } from "../types";
import { INCOME_TYPE_LABELS } from "../types";
import { EducationNote } from "./EducationNote";

function signClass(value: string | null): string | undefined {
  if (value === null) return undefined;
  return Number(value) >= 0 ? "delta-up" : "delta-down";
}

/** Realized gains (FIFO) and income/fees for one portfolio, by year. A
 * tracking aid, not a tax return (the applicable rule may differ — see the
 * help article). */
export function IncomeRealizedSection({ portfolioId, baseCurrency, refreshKey }: { portfolioId: string; baseCurrency: string; refreshKey: number }) {
  const [year, setYear] = useState<number | undefined>(undefined);
  const [realized, setRealized] = useState<RealizedReport | null>(null);
  const [income, setIncome] = useState<IncomeReport | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setError(null);
    Promise.all([getRealized(portfolioId, year), getIncome(portfolioId, year)])
      .then(([r, i]) => {
        if (cancelled) return;
        setRealized(r);
        setIncome(i);
      })
      .catch((err: unknown) => !cancelled && setError(errorMessage(err)));
    return () => {
      cancelled = true;
    };
  }, [portfolioId, year, refreshKey]);

  // Years come from the unfiltered reports' by_year totals (kept from the
  // first load so the picker doesn't shrink after filtering).
  const [years, setYears] = useState<string[]>([]);
  useEffect(() => {
    if (year === undefined && realized && income) {
      const all = new Set([...realized.by_year.map((t) => t.key), ...income.by_year.map((t) => t.key)]);
      setYears([...all].sort().reverse());
    }
  }, [realized, income, year]);

  if (error) return <p className="error-state">{error}</p>;
  if (!realized || !income) return <p className="loading-state">Chargement…</p>;

  return (
    <section aria-label="Revenus et plus-values">
      <div className="inline-form">
        <label>
          Année
          <select value={year ?? ""} onChange={(e) => setYear(e.target.value ? Number(e.target.value) : undefined)}>
            <option value="">Toutes</option>
            {years.map((y) => (
              <option key={y} value={y}>
                {y}
              </option>
            ))}
          </select>
        </label>
      </div>

      <h3>Plus-values réalisées (FIFO)</h3>
      <div className="card-grid">
        <div className="card">
          <h4>Résultat réalisé net</h4>
          <div className={`big-number ${signClass(realized.total_realized_pnl_base) ?? ""}`}>{formatAmount(realized.total_realized_pnl_base, baseCurrency)}</div>
          <div className="muted">{realized.sales.length} vente(s)</div>
        </div>
        {realized.by_year.map((t) => (
          <div className="card" key={t.key}>
            <h4>{t.label}</h4>
            <div className={`big-number ${signClass(t.realized_pnl_base) ?? ""}`}>{formatAmount(t.realized_pnl_base, baseCurrency)}</div>
            <div className="muted">
              gains {formatAmount(t.gains_base, baseCurrency)} · pertes {formatAmount(t.losses_base, baseCurrency)} · {t.sales} vente(s)
            </div>
          </div>
        ))}
      </div>
      {realized.mixed_currency_sales > 0 && <p className="prediction-warning">{realized.mixed_currency_sales} vente(s) dans une devise différente de celle des achats : sans résultat calculable, exclue(s) des totaux.</p>}
      {realized.unconverted_currencies.length > 0 && <p className="prediction-warning">Devise(s) sans taux connu, exclue(s) des totaux : {realized.unconverted_currencies.join(", ")}.</p>}
      {realized.sales.length === 0 ? (
        <p className="empty-state">Aucune vente sur la période.</p>
      ) : (
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Date</th>
                <th>Instrument</th>
                <th>Quantité</th>
                <th>Prix</th>
                <th>Produit net</th>
                <th>Coût (FIFO)</th>
                <th>Résultat</th>
                <th>En {baseCurrency}</th>
                <th>Détention</th>
              </tr>
            </thead>
            <tbody>
              {realized.sales.map((s) => (
                <tr key={s.transaction_id}>
                  <td>{formatDate(s.trade_date)}</td>
                  <td>
                    <a href={href("markets", s.instrument_id)}>{s.symbol}</a>
                  </td>
                  <td>{formatQuantity(s.quantity)}</td>
                  <td>{formatAmount(s.unit_price, s.currency)}</td>
                  <td>{formatAmount(s.proceeds, s.currency)}</td>
                  <td>{s.cost_basis === null ? "—" : formatAmount(s.cost_basis, s.currency)}</td>
                  <td className={signClass(s.realized_pnl)}>{s.mixed_currency ? "devises mixtes" : formatAmount(s.realized_pnl, s.currency)}</td>
                  <td className={signClass(s.realized_pnl_base)} title={s.fx_rate ? `taux ${s.fx_rate} (${s.fx_source})` : undefined}>
                    {formatAmount(s.realized_pnl_base, baseCurrency)}
                  </td>
                  <td>{s.holding_days === null ? "—" : `${s.holding_days} j`}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {realized.by_instrument.length > 1 && (
        <p className="muted">
          Par instrument :{" "}
          {realized.by_instrument.map((t) => (
            <span key={t.key}>
              {t.label} {formatAmount(t.realized_pnl_base, baseCurrency)} ({t.sales}) ·{" "}
            </span>
          ))}
        </p>
      )}
      <p className="muted">{realized.method}</p>
      <button
        type="button"
        className="export-button"
        disabled={realized.sales.length === 0}
        onClick={() =>
          exportAsCsv(
            `nexora-plus-values-${year ?? "toutes"}.csv`,
            realized.sales.map((s) => ({
              date: s.trade_date,
              instrument: s.symbol,
              quantite: s.quantity,
              prix: s.unit_price,
              devise: s.currency,
              produit_net: s.proceeds,
              cout_fifo: s.cost_basis,
              resultat: s.realized_pnl,
              [`resultat_${baseCurrency}`]: s.realized_pnl_base,
              taux: s.fx_rate,
              jours_detention: s.holding_days,
            })),
          )
        }
      >
        Exporter (CSV)
      </button>
      <EducationNote slug="plus-values-realisees" />

      <h3>Revenus et frais</h3>
      <div className="card-grid">
        <div className="card">
          <h4>Revenus encaissés</h4>
          <div className="big-number delta-up">{formatAmount(income.total_income_base, baseCurrency)}</div>
          <div className="muted">dividendes, coupons, intérêts</div>
        </div>
        <div className="card">
          <h4>Frais</h4>
          <div className="big-number delta-down">{formatAmount(income.total_fees_base, baseCurrency)}</div>
          <div className="muted">frais autonomes et frais de transaction</div>
        </div>
        {income.by_year.map((t) => (
          <div className="card" key={t.key}>
            <h4>{t.label}</h4>
            <div className="big-number">{formatAmount(t.net_base, baseCurrency)}</div>
            <div className="muted">
              revenus {formatAmount(t.income_base, baseCurrency)} · frais {formatAmount(t.fees_base, baseCurrency)}
            </div>
          </div>
        ))}
      </div>
      {income.unconverted_currencies.length > 0 && <p className="prediction-warning">Devise(s) sans taux connu, exclue(s) des totaux : {income.unconverted_currencies.join(", ")}.</p>}
      {income.by_month.length > 0 && (
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Mois</th>
                <th>Revenus</th>
                <th>Frais</th>
                <th>Net</th>
                <th>Opérations</th>
              </tr>
            </thead>
            <tbody>
              {income.by_month.map((m) => (
                <tr key={m.key}>
                  <td>{m.label}</td>
                  <td className="delta-up">{formatAmount(m.income_base, baseCurrency)}</td>
                  <td className="delta-down">{formatAmount(m.fees_base, baseCurrency)}</td>
                  <td>{formatAmount(m.net_base, baseCurrency)}</td>
                  <td>{m.count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {income.by_instrument.length > 0 && (
        <p className="muted">
          Par instrument :{" "}
          {income.by_instrument.map((t) => (
            <span key={t.key}>
              {t.label} {formatAmount(t.net_base, baseCurrency)} ·{" "}
            </span>
          ))}
        </p>
      )}
      {income.rows.length === 0 ? (
        <p className="empty-state">Aucun revenu ni frais sur la période.</p>
      ) : (
        <details>
          <summary>Détail des {income.rows.length} opération(s)</summary>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Type</th>
                  <th>Instrument</th>
                  <th>Montant</th>
                  <th>En {baseCurrency}</th>
                  <th>Note</th>
                </tr>
              </thead>
              <tbody>
                {income.rows.map((r) => (
                  <tr key={`${r.transaction_id}-${r.type}`}>
                    <td>{formatDate(r.trade_date)}</td>
                    <td>{INCOME_TYPE_LABELS[r.type] ?? r.type}</td>
                    <td>{r.instrument_id ? <a href={href("markets", r.instrument_id)}>{r.symbol}</a> : "—"}</td>
                    <td className={signClass(r.amount)}>{formatAmount(r.amount, r.currency)}</td>
                    <td className={signClass(r.amount_base)}>{formatAmount(r.amount_base, baseCurrency)}</td>
                    <td className="muted">{r.note ?? ""}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      )}
      <p className="muted">{income.method}</p>
      <button
        type="button"
        className="export-button"
        disabled={income.rows.length === 0}
        onClick={() =>
          exportAsCsv(
            `nexora-revenus-${year ?? "toutes"}.csv`,
            income.rows.map((r) => ({ date: r.trade_date, type: r.type, instrument: r.symbol, montant: r.amount, devise: r.currency, [`montant_${baseCurrency}`]: r.amount_base, note: r.note })),
          )
        }
      >
        Exporter (CSV)
      </button>
      <EducationNote slug="revenus-du-portefeuille" />
    </section>
  );
}
