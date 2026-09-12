import { useEffect, useState } from "react";
import {
  ApiError,
  createInstrument,
  createPrice,
  createPrivateValuation,
  listInstruments,
  listPrices,
  listPrivateValuations,
} from "../api/client";
import { ASSET_CLASSES, ASSET_CLASS_LABELS } from "../types";
import type { Instrument, PricePoint, PrivateValuation } from "../types";
import { formatAmount, formatDateTime } from "../format";

export function InstrumentsPage() {
  const [instruments, setInstruments] = useState<Instrument[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [symbol, setSymbol] = useState("");
  const [name, setName] = useState("");
  const [assetClass, setAssetClass] = useState("action");
  const [currency, setCurrency] = useState("EUR");
  const [error, setError] = useState<string | null>(null);

  function reload() {
    listInstruments()
      .then(setInstruments)
      .catch((err: unknown) => setError(err instanceof ApiError ? err.message : "Erreur de chargement"));
  }

  useEffect(reload, []);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    try {
      const instrument = await createInstrument({ symbol, name, asset_class: assetClass, currency });
      setInstruments((prev) => [...prev, instrument]);
      setSymbol("");
      setName("");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Impossible de créer l'instrument");
    }
  }

  const selected = instruments.find((i) => i.id === selectedId) ?? null;

  return (
    <section aria-label="Instruments">
      <h2>Instruments</h2>
      {error && <p className="error-state">{error}</p>}

      <form onSubmit={handleCreate} className="form-grid">
        <label>
          Symbole
          <input required value={symbol} onChange={(e) => setSymbol(e.target.value.toUpperCase())} />
        </label>
        <label>
          Nom
          <input required value={name} onChange={(e) => setName(e.target.value)} />
        </label>
        <label>
          Classe d'actif
          <select value={assetClass} onChange={(e) => setAssetClass(e.target.value)}>
            {ASSET_CLASSES.map((c) => (
              <option key={c} value={c}>
                {ASSET_CLASS_LABELS[c]}
              </option>
            ))}
          </select>
        </label>
        <label>
          Devise
          <input required value={currency} onChange={(e) => setCurrency(e.target.value.toUpperCase())} maxLength={8} />
        </label>
        <button type="submit" className="primary-button">
          Créer l'instrument
        </button>
      </form>

      <div className="portfolio-layout">
        <aside className="portfolio-sidebar">
          <ul className="portfolio-list">
            {instruments.map((i) => (
              <li key={i.id}>
                <button
                  type="button"
                  className={i.id === selectedId ? "portfolio-item selected" : "portfolio-item"}
                  onClick={() => setSelectedId(i.id)}
                >
                  {i.symbol} <span className="muted">{ASSET_CLASS_LABELS[i.asset_class]}</span>
                </button>
              </li>
            ))}
          </ul>
        </aside>
        <div className="portfolio-main">
          {selected ? <InstrumentDetail instrument={selected} /> : <p className="empty-state">Sélectionnez un instrument.</p>}
        </div>
      </div>
    </section>
  );
}

function InstrumentDetail({ instrument }: { instrument: Instrument }) {
  const [prices, setPrices] = useState<PricePoint[]>([]);
  const [valuations, setValuations] = useState<PrivateValuation[]>([]);
  const [asOf, setAsOf] = useState(() => new Date().toISOString().slice(0, 16));
  const [price, setPrice] = useState("");
  const [isEstimate, setIsEstimate] = useState(false);
  const [valuationAmount, setValuationAmount] = useState("");
  const [method, setMethod] = useState("");
  const [error, setError] = useState<string | null>(null);

  function reload() {
    listPrices(instrument.id).then(setPrices);
    if (instrument.asset_class === "actif_prive") listPrivateValuations(instrument.id).then(setValuations);
  }

  useEffect(reload, [instrument.id]);

  async function handleAddPrice(e: React.FormEvent) {
    e.preventDefault();
    try {
      await createPrice(instrument.id, {
        as_of: new Date(asOf).toISOString(),
        price,
        currency: instrument.currency,
        is_estimate: isEstimate,
      });
      setPrice("");
      reload();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Impossible d'ajouter le prix");
    }
  }

  async function handleAddValuation(e: React.FormEvent) {
    e.preventDefault();
    try {
      await createPrivateValuation(instrument.id, {
        valuation_date: new Date(asOf).toISOString(),
        valuation_amount: valuationAmount,
        currency: instrument.currency,
        method,
      });
      setValuationAmount("");
      setMethod("");
      reload();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Impossible d'ajouter la valorisation");
    }
  }

  return (
    <div>
      <h3>
        {instrument.symbol} — {instrument.name}
      </h3>
      {error && <p className="error-state">{error}</p>}

      <h4>Prix</h4>
      <form onSubmit={handleAddPrice} className="inline-form">
        <input type="datetime-local" value={asOf} onChange={(e) => setAsOf(e.target.value)} />
        <input placeholder="Prix" required value={price} onChange={(e) => setPrice(e.target.value)} />
        <label>
          <input type="checkbox" checked={isEstimate} onChange={(e) => setIsEstimate(e.target.checked)} /> estimation
        </label>
        <button type="submit">Ajouter un prix</button>
      </form>
      <ul className="plain-list">
        {prices.map((p) => (
          <li key={p.id}>
            {formatDateTime(p.as_of)} — {formatAmount(p.price, p.currency)}{" "}
            {p.is_estimate && <span className="badge">estimé</span>}
          </li>
        ))}
      </ul>

      {instrument.asset_class === "actif_prive" && (
        <>
          <h4>Valorisations privées</h4>
          <form onSubmit={handleAddValuation} className="inline-form">
            <input placeholder="Montant" required value={valuationAmount} onChange={(e) => setValuationAmount(e.target.value)} />
            <input placeholder="Méthode (ex. dernière levée de fonds)" required value={method} onChange={(e) => setMethod(e.target.value)} />
            <button type="submit">Ajouter une valorisation</button>
          </form>
          <ul className="plain-list">
            {valuations.map((v) => (
              <li key={v.id}>
                {formatDateTime(v.valuation_date)} — {formatAmount(v.valuation_amount, v.currency)} ({v.method}, confiance{" "}
                {v.confidence})
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
