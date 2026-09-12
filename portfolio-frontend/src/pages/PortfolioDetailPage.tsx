import { useEffect, useState } from "react";
import {
  ApiError,
  createInstrument,
  createTransaction,
  getPositions,
  getValuation,
  listInstruments,
  listTransactions,
  reverseTransaction,
  updatePortfolio,
} from "../api/client";
import {
  ASSET_CLASSES,
  ASSET_CLASS_LABELS,
  CASH_ONLY_TRANSACTION_TYPES,
  FRESHNESS_LABELS,
  TRANSACTION_TYPES,
  TRANSACTION_TYPE_LABELS,
} from "../types";
import type { Instrument, Portfolio, Position, Transaction, TransactionType, Valuation } from "../types";
import { formatAmount, formatDateTime, formatQuantity } from "../format";
import { ImportWizard } from "../components/ImportWizard";

const INSTRUMENT_REQUIRED_TYPES: TransactionType[] = ["achat", "vente", "dividende", "coupon", "split"];

function toDatetimeLocal(iso: string): string {
  return iso.slice(0, 16);
}

export function PortfolioDetailPage({
  portfolio,
  onRenamed,
}: {
  portfolio: Portfolio;
  onRenamed: (updated: Portfolio) => void;
}) {
  const [positions, setPositions] = useState<Position[]>([]);
  const [valuation, setValuation] = useState<Valuation | null>(null);
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [instruments, setInstruments] = useState<Instrument[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [renaming, setRenaming] = useState(false);
  const [newName, setNewName] = useState(portfolio.name);

  function reload() {
    setError(null);
    Promise.all([getPositions(portfolio.id), getValuation(portfolio.id), listTransactions(portfolio.id), listInstruments()])
      .then(([pos, val, txs, instr]) => {
        setPositions(pos);
        setValuation(val);
        setTransactions(txs.items);
        setInstruments(instr);
      })
      .catch((err: unknown) => setError(err instanceof ApiError ? err.message : "Erreur de chargement"));
  }

  useEffect(reload, [portfolio.id]);

  async function handleRename(e: React.FormEvent) {
    e.preventDefault();
    const updated = await updatePortfolio(portfolio.id, newName);
    onRenamed(updated);
    setRenaming(false);
  }

  async function handleReverse(tx: Transaction) {
    const reason = window.prompt("Motif de la contre-passation ?");
    if (!reason) return;
    try {
      await reverseTransaction(portfolio.id, tx.id, reason);
      reload();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Impossible de contre-passer cette transaction");
    }
  }

  return (
    <div>
      <header className="portfolio-header">
        {renaming ? (
          <form onSubmit={handleRename} className="inline-form">
            <input value={newName} onChange={(e) => setNewName(e.target.value)} autoFocus />
            <button type="submit">Enregistrer</button>
            <button type="button" onClick={() => setRenaming(false)}>
              Annuler
            </button>
          </form>
        ) : (
          <h2>
            {portfolio.name}{" "}
            <button type="button" className="link-button" onClick={() => setRenaming(true)}>
              renommer
            </button>
          </h2>
        )}
      </header>

      {error && <p className="error-state">{error}</p>}

      {valuation && <ValuationSummary valuation={valuation} />}

      <h3>Positions</h3>
      <PositionsTable positions={positions} />

      <h3>Nouvelle transaction</h3>
      <TransactionForm
        portfolioId={portfolio.id}
        instruments={instruments}
        onCreated={reload}
        onInstrumentCreated={(i) => setInstruments((prev) => [...prev, i])}
        onError={(msg) => setError(msg)}
      />

      <h3>Transactions</h3>
      <TransactionsList transactions={transactions} instruments={instruments} onReverse={handleReverse} />

      <ImportWizard portfolioId={portfolio.id} onCommitted={reload} />
    </div>
  );
}

function ValuationSummary({ valuation }: { valuation: Valuation }) {
  return (
    <div className="card valuation-summary">
      <div>
        <span className="muted">Valeur totale</span>
        <strong>{formatAmount(valuation.total_value, valuation.base_currency)}</strong>
      </div>
      <div>
        <span className="muted">Liquidités</span>
        <strong>{formatAmount(valuation.cash, valuation.base_currency)}</strong>
      </div>
      <div>
        <span className="muted">Positions</span>
        <strong>{formatAmount(valuation.positions_value, valuation.base_currency)}</strong>
      </div>
      {valuation.has_missing_prices && (
        <p className="prediction-warning" role="note">
          Certaines positions n'ont pas de prix connu : elles sont exclues de la valeur totale.
        </p>
      )}
      {valuation.unconverted_currencies.length > 0 && (
        <p className="prediction-warning" role="note">
          Devises non converties (aucun taux de change configuré), exclues du total :{" "}
          {valuation.unconverted_currencies.join(", ")}.
        </p>
      )}
    </div>
  );
}

function PositionsTable({ positions }: { positions: Position[] }) {
  if (positions.length === 0) return <p className="empty-state">Aucune position ouverte.</p>;
  return (
    <div className="table-scroll">
      <table>
        <thead>
          <tr>
            <th>Instrument</th>
            <th>Quantité</th>
            <th>Coût moyen</th>
            <th>Dernier prix</th>
            <th>Valeur de marché</th>
            <th>Fraîcheur</th>
          </tr>
        </thead>
        <tbody>
          {positions.map((p) => (
            <tr key={p.instrument_id} className={p.freshness === "manquant" ? "row-warning" : undefined}>
              <td>
                {p.symbol} <span className="muted">{p.name}</span>
              </td>
              <td>{formatQuantity(p.quantity)}</td>
              <td>{formatAmount(p.average_unit_cost, p.currency)}</td>
              <td>{p.price ? formatAmount(p.price, p.currency) : "—"}</td>
              <td>{p.market_value ? formatAmount(p.market_value, p.currency) : "—"}</td>
              <td>
                <span className={`badge freshness-${p.freshness}`}>{FRESHNESS_LABELS[p.freshness]}</span>
                {!p.matches_base_currency && <span className="badge">devise différente</span>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function TransactionForm({
  portfolioId,
  instruments,
  onCreated,
  onInstrumentCreated,
  onError,
}: {
  portfolioId: string;
  instruments: Instrument[];
  onCreated: () => void;
  onInstrumentCreated: (instrument: Instrument) => void;
  onError: (message: string) => void;
}) {
  const [type, setType] = useState<TransactionType>("achat");
  const [instrumentId, setInstrumentId] = useState("");
  const [tradeDate, setTradeDate] = useState(() => toDatetimeLocal(new Date().toISOString()));
  const [quantity, setQuantity] = useState("1");
  const [unitPrice, setUnitPrice] = useState("");
  const [currency, setCurrency] = useState("EUR");
  const [fees, setFees] = useState("0");
  const [showNewInstrument, setShowNewInstrument] = useState(false);
  const [newSymbol, setNewSymbol] = useState("");
  const [newInstrumentName, setNewInstrumentName] = useState("");
  const [newAssetClass, setNewAssetClass] = useState("action");

  const needsInstrument = INSTRUMENT_REQUIRED_TYPES.includes(type);
  const isCashOnly = CASH_ONLY_TRANSACTION_TYPES.includes(type);

  async function handleCreateInstrument() {
    try {
      const instrument = await createInstrument({
        symbol: newSymbol,
        name: newInstrumentName || newSymbol,
        asset_class: newAssetClass,
        currency,
      });
      onInstrumentCreated(instrument);
      setInstrumentId(instrument.id);
      setShowNewInstrument(false);
      setNewSymbol("");
      setNewInstrumentName("");
    } catch (err) {
      onError(err instanceof ApiError ? err.message : "Impossible de créer l'instrument");
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    try {
      await createTransaction(portfolioId, {
        instrument_id: needsInstrument ? instrumentId : null,
        type,
        trade_date: new Date(tradeDate).toISOString(),
        quantity: isCashOnly ? "1" : quantity,
        unit_price: unitPrice,
        currency,
        fees,
      });
      setUnitPrice("");
      onCreated();
    } catch (err) {
      onError(err instanceof ApiError ? err.message : "Impossible d'enregistrer la transaction");
    }
  }

  return (
    <form onSubmit={handleSubmit} className="form-grid transaction-form">
      <label>
        Type
        <select value={type} onChange={(e) => setType(e.target.value as TransactionType)}>
          {TRANSACTION_TYPES.map((t) => (
            <option key={t} value={t}>
              {TRANSACTION_TYPE_LABELS[t]}
            </option>
          ))}
        </select>
      </label>

      {needsInstrument && (
        <label>
          Instrument
          <select required value={instrumentId} onChange={(e) => setInstrumentId(e.target.value)}>
            <option value="">— choisir —</option>
            {instruments.map((i) => (
              <option key={i.id} value={i.id}>
                {i.symbol} — {i.name}
              </option>
            ))}
          </select>
          <button type="button" className="link-button" onClick={() => setShowNewInstrument((v) => !v)}>
            {showNewInstrument ? "annuler" : "+ nouvel instrument"}
          </button>
        </label>
      )}

      {showNewInstrument && (
        <div className="inline-form">
          <input placeholder="Symbole" value={newSymbol} onChange={(e) => setNewSymbol(e.target.value)} />
          <input placeholder="Nom" value={newInstrumentName} onChange={(e) => setNewInstrumentName(e.target.value)} />
          <select value={newAssetClass} onChange={(e) => setNewAssetClass(e.target.value)}>
            {ASSET_CLASSES.map((c) => (
              <option key={c} value={c}>
                {ASSET_CLASS_LABELS[c]}
              </option>
            ))}
          </select>
          <button type="button" onClick={handleCreateInstrument} disabled={!newSymbol}>
            Créer
          </button>
        </div>
      )}

      <label>
        Date
        <input type="datetime-local" required value={tradeDate} onChange={(e) => setTradeDate(e.target.value)} />
      </label>

      {!isCashOnly && (
        <label>
          Quantité
          <input required value={quantity} onChange={(e) => setQuantity(e.target.value)} />
        </label>
      )}

      <label>
        {isCashOnly ? "Montant" : "Prix unitaire"}
        <input required value={unitPrice} onChange={(e) => setUnitPrice(e.target.value)} />
      </label>

      <label>
        Devise
        <input required value={currency} onChange={(e) => setCurrency(e.target.value.toUpperCase())} maxLength={8} />
      </label>

      <label>
        Frais
        <input value={fees} onChange={(e) => setFees(e.target.value)} />
      </label>

      <button type="submit" className="primary-button">
        Ajouter la transaction
      </button>
    </form>
  );
}

function TransactionsList({
  transactions,
  instruments,
  onReverse,
}: {
  transactions: Transaction[];
  instruments: Instrument[];
  onReverse: (tx: Transaction) => void;
}) {
  if (transactions.length === 0) return <p className="empty-state">Aucune transaction pour le moment.</p>;
  const instrumentById = new Map(instruments.map((i) => [i.id, i]));
  return (
    <div className="table-scroll">
      <table>
        <thead>
          <tr>
            <th>Date</th>
            <th>Type</th>
            <th>Instrument</th>
            <th>Quantité</th>
            <th>Prix / Montant</th>
            <th>Frais</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {transactions.map((tx) => (
            <tr key={tx.id} className={tx.reversed_at ? "row-reversed" : undefined}>
              <td>{formatDateTime(tx.trade_date)}</td>
              <td>{TRANSACTION_TYPE_LABELS[tx.type]}</td>
              <td>{tx.instrument_id ? instrumentById.get(tx.instrument_id)?.symbol ?? tx.instrument_id : "—"}</td>
              <td>{formatQuantity(tx.quantity)}</td>
              <td>{formatAmount(tx.unit_price, tx.currency)}</td>
              <td>{formatAmount(tx.fees, tx.currency)}</td>
              <td>
                {tx.reversed_at ? (
                  <span className="muted" title={tx.reversal_reason ?? undefined}>
                    contre-passée
                  </span>
                ) : (
                  <button type="button" className="link-button" onClick={() => onReverse(tx)}>
                    contre-passer
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
