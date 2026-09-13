import { useEffect, useState } from "react";
import { createPortfolio, errorMessage, listPortfolios, quickBuy } from "../api/client";
import { formatAmount } from "../format";
import type { Instrument, Portfolio, Quote } from "../types";

/** "Ajouter au portefeuille": records a purchase the user confirms. Nothing
 * is sent to any broker — it is bookkeeping of something the user already
 * did (or wants to track as if they had). Prefilled with the last quote and
 * today, all editable. */
export function QuickBuyDialog({ instrument, quote, onDone, onCancel }: { instrument: Instrument; quote: Quote | null; onDone: () => void; onCancel: () => void }) {
  const [portfolios, setPortfolios] = useState<Portfolio[]>([]);
  const [portfolioId, setPortfolioId] = useState("");
  const [newPortfolioName, setNewPortfolioName] = useState("");
  const [quantity, setQuantity] = useState("1");
  const [unitPrice, setUnitPrice] = useState(quote?.price ? Number(quote.price).toString() : "");
  const [fees, setFees] = useState("0");
  const [tradeDate, setTradeDate] = useState(() => new Date().toISOString().slice(0, 16));
  const [note, setNote] = useState("");
  const [fundWithDeposit, setFundWithDeposit] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const currency = quote?.currency ?? instrument.currency;

  useEffect(() => {
    listPortfolios()
      .then((list) => {
        setPortfolios(list);
        if (list.length > 0) setPortfolioId(list[0].id);
      })
      .catch((err: unknown) => setError(errorMessage(err)));
  }, []);

  async function submit(evt: React.FormEvent) {
    evt.preventDefault();
    setSaving(true);
    setError(null);
    try {
      let target = portfolioId;
      if (!target) {
        if (!newPortfolioName.trim()) throw new Error("Nommez un portefeuille");
        const created = await createPortfolio(newPortfolioName.trim(), currency);
        target = created.id;
      }
      await quickBuy(instrument.id, {
        portfolio_id: target,
        quantity,
        unit_price: unitPrice,
        currency,
        fees,
        trade_date: new Date(tradeDate).toISOString(),
        note: note || undefined,
        fund_with_deposit: fundWithDeposit,
      });
      onDone();
    } catch (err) {
      setError(err instanceof Error && !("status" in err) ? err.message : errorMessage(err, "Enregistrement impossible"));
    } finally {
      setSaving(false);
    }
  }

  const total = Number(quantity) * Number(unitPrice) + Number(fees || 0);

  return (
    <div className="dialog-backdrop" role="presentation" onClick={onCancel}>
      <form className="dialog" role="dialog" aria-modal="true" aria-label={`Ajouter ${instrument.symbol} au portefeuille`} onClick={(e) => e.stopPropagation()} onSubmit={submit}>
        <h3>
          Ajouter {instrument.symbol} au portefeuille
        </h3>
        <p className="muted">
          Enregistre un achat dans votre suivi. Aucun ordre n'est transmis à un intermédiaire : vous décrivez une opération, vous ne l'exécutez pas ici.
        </p>
        <div className="form-grid">
          <label>
            Portefeuille
            <select value={portfolioId} onChange={(e) => setPortfolioId(e.target.value)}>
              {portfolios.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name} ({p.base_currency})
                </option>
              ))}
              <option value="">— créer un nouveau portefeuille —</option>
            </select>
          </label>
          {!portfolioId && (
            <label>
              Nom du nouveau portefeuille
              <input value={newPortfolioName} onChange={(e) => setNewPortfolioName(e.target.value)} required />
            </label>
          )}
          <label>
            Quantité
            <input type="number" step="any" min="0" value={quantity} onChange={(e) => setQuantity(e.target.value)} required />
          </label>
          <label>
            Prix unitaire ({currency})
            <input type="number" step="any" min="0" value={unitPrice} onChange={(e) => setUnitPrice(e.target.value)} required />
          </label>
          <label>
            Frais ({currency})
            <input type="number" step="any" min="0" value={fees} onChange={(e) => setFees(e.target.value)} />
          </label>
          <label>
            Date de l'opération
            <input type="datetime-local" value={tradeDate} onChange={(e) => setTradeDate(e.target.value)} required />
          </label>
          <label>
            Note (optionnelle)
            <input value={note} onChange={(e) => setNote(e.target.value)} maxLength={500} />
          </label>
          <label className="inline-check">
            <input type="checkbox" checked={fundWithDeposit} onChange={(e) => setFundWithDeposit(e.target.checked)} />
            Enregistrer aussi un apport du même montant (l'argent venait de l'extérieur du portefeuille)
          </label>
        </div>
        <p>
          Montant total : <strong>{Number.isFinite(total) ? formatAmount(total, currency) : "—"}</strong>
        </p>
        {error && <p className="error-state">{error}</p>}
        <div className="toolbar">
          <button type="submit" className="primary-button" disabled={saving}>
            Enregistrer l'achat
          </button>
          <button type="button" className="export-button" onClick={onCancel}>
            Annuler
          </button>
        </div>
      </form>
    </div>
  );
}
