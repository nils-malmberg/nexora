import { useEffect, useState } from "react";
import { ApiError, listAssetNews } from "../api/client";
import { NewsCard } from "../components/NewsCard";
import { CATEGORIES, CATEGORY_LABELS } from "../types";
import type { NewsItem } from "../types";

export function NewsPage({ assetId }: { assetId: string }) {
  const [items, setItems] = useState<NewsItem[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [category, setCategory] = useState("");
  const [kind, setKind] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    listAssetNews(assetId, { category: category || undefined, kind: kind || undefined })
      .then((page) => {
        setItems(page.items);
        setNextCursor(page.next_cursor);
      })
      .catch((err: unknown) => setError(err instanceof ApiError ? err.message : "Erreur de chargement"))
      .finally(() => setLoading(false));
  }, [assetId, category, kind]);

  async function loadMore() {
    if (!nextCursor) return;
    const page = await listAssetNews(assetId, {
      category: category || undefined,
      kind: kind || undefined,
      cursor: nextCursor,
    });
    setItems((prev) => [...prev, ...page.items]);
    setNextCursor(page.next_cursor);
  }

  return (
    <section aria-label="Actualités récentes">
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
      </div>

      {loading && <p className="loading-state">Chargement…</p>}
      {error && <p className="error-state">{error}</p>}
      {!loading && !error && items.length === 0 && (
        <p className="empty-state">Aucune actualité récente pour cet actif avec ces filtres.</p>
      )}
      {items.map((item) => (
        <NewsCard key={item.id} item={item} />
      ))}
      {nextCursor && (
        <button type="button" className="load-more" onClick={loadMore}>
          Charger plus
        </button>
      )}
    </section>
  );
}
