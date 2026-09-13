import { useState } from "react";
import { addToWatchlist, errorMessage, updateWatchlistItem } from "../api/client";
import type { Instrument, Quote, WatchlistItem } from "../types";

/** "Je détiens ce titre": a note to oneself (entry price, quantity) on the
 * watchlist item — enough for the sell-or-hold reading, without any
 * transaction log. */
export function HoldDialog({
  instrument,
  quote,
  item,
  onDone,
  onCancel,
}: {
  instrument: Instrument;
  quote: Quote | null;
  item: WatchlistItem | null;
  onDone: (item: WatchlistItem) => void;
  onCancel: () => void;
}) {
  const [entryPrice, setEntryPrice] = useState(item?.entry_price ?? quote?.price ?? "");
  const [quantity, setQuantity] = useState(item?.quantity ?? "");
  const [entryDate, setEntryDate] = useState(item?.entry_date ? item.entry_date.slice(0, 10) : "");
  const [note, setNote] = useState(item?.note ?? "");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const target = item ?? (await addToWatchlist(instrument.id));
      const updated = await updateWatchlistItem(target.id, {
        held: true,
        entry_price: entryPrice ? String(entryPrice) : undefined,
        quantity: quantity ? String(quantity) : undefined,
        entry_date: entryDate ? new Date(entryDate).toISOString() : undefined,
        note: note || null,
      });
      onDone(updated);
    } catch (err) {
      setError(errorMessage(err, "Enregistrement impossible"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="dialog-backdrop" role="presentation" onClick={onCancel}>
      <form className="dialog" role="dialog" aria-modal="true" aria-label={`Je détiens ${instrument.symbol}`} onClick={(e) => e.stopPropagation()} onSubmit={submit}>
        <h3>Je détiens {instrument.symbol}</h3>
        <p className="muted">Une note pour vous-même : l'aide à la décision l'utilise pour parler de « conserver ou vendre » et calculer votre plus ou moins-value. Rien n'est transmis à un courtier.</p>
        <div className="form-grid">
          <label>
            Prix d'achat moyen ({quote?.currency ?? instrument.currency})
            <input type="number" step="any" min="0" value={entryPrice} onChange={(e) => setEntryPrice(e.target.value)} />
          </label>
          <label>
            Quantité (facultatif)
            <input type="number" step="any" min="0" value={quantity} onChange={(e) => setQuantity(e.target.value)} />
          </label>
          <label>
            Date d'achat (facultatif)
            <input type="date" value={entryDate} onChange={(e) => setEntryDate(e.target.value)} />
          </label>
          <label>
            Note
            <input value={note} onChange={(e) => setNote(e.target.value)} maxLength={200} placeholder="PEA, CTO…" />
          </label>
        </div>
        {error && <p className="error-state">{error}</p>}
        <div className="toolbar">
          <button type="submit" className="primary-button" disabled={busy}>
            Enregistrer
          </button>
          <button type="button" onClick={onCancel}>
            Annuler
          </button>
        </div>
      </form>
    </div>
  );
}
