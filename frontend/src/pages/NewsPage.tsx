import { useEffect, useMemo, useState } from "react";
import { ApiError, listAssetNews } from "../api/client";
import { NewsCard } from "../components/NewsCard";
import { CATEGORIES, CATEGORY_LABELS } from "../types";
import type { NewsItem } from "../types";
import { useDismissed } from "../hooks/useDismissed";
import { exportAsJson } from "../export";

const SEARCH_DEBOUNCE_MS = 350;

export function NewsPage({ assetId }: { assetId: string }) {
  const [items, setItems] = useState<NewsItem[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [category, setCategory] = useState("");
  const [kind, setKind] = useState("");
  const [searchInput, setSearchInput] = useState("");
  const [q, setQ] = useState("");
  const [showDismissed, setShowDismissed] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const { dismissed, dismiss, restore } = useDismissed();

  useEffect(() => {
    const timer = setTimeout(() => setQ(searchInput.trim()), SEARCH_DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [searchInput]);

  useEffect(() => {
    setLoading(true);
    setError(null);
    listAssetNews(assetId, { category: category || undefined, kind: kind || undefined, q: q || undefined })
      .then((page) => {
        setItems(page.items);
        setNextCursor(page.next_cursor);
      })
      .catch((err: unknown) => setError(err instanceof ApiError ? err.message : "Erreur de chargement"))
      .finally(() => setLoading(false));
  }, [assetId, category, kind, q]);

  async function loadMore() {
    if (!nextCursor) return;
    const page = await listAssetNews(assetId, {
      category: category || undefined,
      kind: kind || undefined,
      q: q || undefined,
      cursor: nextCursor,
    });
    setItems((prev) => [...prev, ...page.items]);
    setNextCursor(page.next_cursor);
  }

  const visibleItems = useMemo(
    () => items.filter((item) => showDismissed || !dismissed.has(item.id)),
    [items, dismissed, showDismissed],
  );
  const hiddenCount = items.length - items.filter((item) => !dismissed.has(item.id)).length;

  function handleExport() {
    exportAsJson(`nexora-actualites-${assetId}.json`, visibleItems);
  }

  return (
    <section aria-label="Actualités récentes">
      <div className="toolbar">
        <label className="search-bar">
          Rechercher
          <input
            type="search"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            placeholder="Titre, résumé, extrait…"
            aria-label="Rechercher dans les actualités"
          />
        </label>
        <button type="button" className="export-button" onClick={handleExport} disabled={visibleItems.length === 0}>
          Exporter (JSON)
        </button>
      </div>

      <div className="filters">
        <label>
          Catégorie
          <select value={category} onChange={(e) => setCategory(e.target.value)}>
            <option value="">Toutes</option>
            {CATEGORIES.map((c) => (
              <option key={c} value={c}>
                {CATEGORY_LABELS[c]}
              </option>
            ))}
          </select>
        </label>
        <label>
          Type
          <select value={kind} onChange={(e) => setKind(e.target.value)}>
            <option value="">Tous</option>
            <option value="fact">Fait</option>
            <option value="synthesis">Synthèse</option>
            <option value="prediction">Estimation</option>
          </select>
        </label>
        {hiddenCount > 0 && (
          <label className="dismissed-toggle">
            <input type="checkbox" checked={showDismissed} onChange={(e) => setShowDismissed(e.target.checked)} />
            Afficher les {hiddenCount} élément(s) masqué(s)
          </label>
        )}
      </div>

      {loading && <p className="loading-state">Chargement…</p>}
      {error && <p className="error-state">{error}</p>}
      {!loading && !error && visibleItems.length === 0 && (
        <p className="empty-state">Aucune actualité récente pour cet actif avec ces filtres.</p>
      )}
      {visibleItems.map((item) => (
        <NewsCard
          key={item.id}
          item={item}
          dismissed={dismissed.has(item.id)}
          onDismiss={() => dismiss(item.id)}
          onRestore={() => restore(item.id)}
        />
      ))}
      {nextCursor && (
        <button type="button" className="load-more" onClick={loadMore}>
          Charger plus
        </button>
      )}
    </section>
  );
}
