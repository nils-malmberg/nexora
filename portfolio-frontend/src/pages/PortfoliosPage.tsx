import { useEffect, useState } from "react";
import { ApiError, createPortfolio, deletePortfolio, listPortfolios } from "../api/client";
import type { Portfolio } from "../types";
import { PortfolioDetailPage } from "./PortfolioDetailPage";

export function PortfoliosPage() {
  const [portfolios, setPortfolios] = useState<Portfolio[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [baseCurrency, setBaseCurrency] = useState("EUR");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  function reload() {
    setLoading(true);
    listPortfolios()
      .then((list) => {
        setPortfolios(list);
        if (!selectedId && list.length > 0) setSelectedId(list[0].id);
      })
      .catch((err: unknown) => setError(err instanceof ApiError ? err.message : "Erreur de chargement"))
      .finally(() => setLoading(false));
  }

  useEffect(reload, []);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    try {
      const portfolio = await createPortfolio(name, baseCurrency);
      setPortfolios((prev) => [...prev, portfolio]);
      setSelectedId(portfolio.id);
      setName("");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Impossible de créer le portefeuille");
    }
  }

  async function handleDelete(portfolioId: string) {
    if (!window.confirm("Supprimer ce portefeuille et toutes ses transactions ? Cette action est irréversible.")) return;
    await deletePortfolio(portfolioId);
    setPortfolios((prev) => prev.filter((p) => p.id !== portfolioId));
    if (selectedId === portfolioId) setSelectedId(null);
  }

  return (
    <section aria-label="Portefeuilles">
      <div className="portfolio-layout">
        <aside className="portfolio-sidebar">
          <h2>Portefeuilles</h2>
          {loading && <p className="loading-state">Chargement…</p>}
          {error && <p className="error-state">{error}</p>}
          <ul className="portfolio-list">
            {portfolios.map((p) => (
              <li key={p.id}>
                <button
                  type="button"
                  className={p.id === selectedId ? "portfolio-item selected" : "portfolio-item"}
                  onClick={() => setSelectedId(p.id)}
                >
                  {p.name} <span className="muted">({p.base_currency})</span>
                </button>
                <button type="button" className="link-button danger" onClick={() => handleDelete(p.id)}>
                  Supprimer
                </button>
              </li>
            ))}
          </ul>
          <form onSubmit={handleCreate} className="form-grid">
            <label>
              Nom
              <input required value={name} onChange={(e) => setName(e.target.value)} placeholder="Compte principal" />
            </label>
            <label>
              Devise de référence
              <input value={baseCurrency} onChange={(e) => setBaseCurrency(e.target.value.toUpperCase())} maxLength={8} />
            </label>
            <button type="submit" className="primary-button">
              Créer un portefeuille
            </button>
          </form>
        </aside>
        <div className="portfolio-main">
          {selectedId ? (
            <PortfolioDetailPage
              portfolio={portfolios.find((p) => p.id === selectedId)!}
              onRenamed={(updated) => setPortfolios((prev) => prev.map((p) => (p.id === updated.id ? updated : p)))}
            />
          ) : (
            <p className="empty-state">Sélectionnez ou créez un portefeuille pour commencer.</p>
          )}
        </div>
      </div>
    </section>
  );
}
