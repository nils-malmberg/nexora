import { useEffect, useMemo, useState } from "react";
import { ApiError, listInstrumentNews, refreshInstrumentNews } from "../api/client";
import { formatDateTime } from "../format";
import { href } from "../router";
import type { NewsRefresh } from "../types";
import { NewsCard } from "../components/NewsCard";
import { CATEGORIES, CATEGORY_LABELS } from "../types";
import type { NewsItem } from "../types";
import { useDismissed } from "../hooks/useDismissed";
import { exportAsJson } from "../export";

const SEARCH_DEBOUNCE_MS = 350;

export function NewsPage({ instrumentId }: { instrumentId: string }) {
  const [items, setItems] = useState<NewsItem[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [category, setCategory] = useState("");
  const [kind, setKind] = useState("");
  const [searchInput, setSearchInput] = useState("");
  const [q, setQ] = useState("");
  const [showDismissed, setShowDismissed] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refresh, setRefresh] = useState<NewsRefresh | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [reloadTick, setReloadTick] = useState(0);
  const { dismissed, dismiss, restore } = useDismissed();

  // One (server-throttled) company-news refresh when the page opens, so a
  // freshly added instrument shows news instead of an unexplained empty list.
  useEffect(() => {
    let cancelled = false;
    setRefreshing(true);
    refreshInstrumentNews(instrumentId)
      .then((r) => {
        if (cancelled) return;
        setRefresh(r);
        if (r.status === "refreshed") setReloadTick((t) => t + 1);
      })
      .catch(() => !cancelled && setRefresh(null))
      .finally(() => !cancelled && setRefreshing(false));
    return () => {
      cancelled = true;
    };
  }, [instrumentId]);

  useEffect(() => {
    const timer = setTimeout(() => setQ(searchInput.trim()), SEARCH_DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [searchInput]);

  useEffect(() => {
    setLoading(true);
    setError(null);
    listInstrumentNews(instrumentId, { category: category || undefined, kind: kind || undefined, q: q || undefined })
      .then((page) => {
        setItems(page.items);
        setNextCursor(page.next_cursor);
      })
      .catch((err: unknown) => setError(err instanceof ApiError ? err.message : "Erreur de chargement"))
      .finally(() => setLoading(false));
  }, [instrumentId, category, kind, q, reloadTick]);

  async function handleRefresh() {
    setRefreshing(true);
    try {
      const r = await refreshInstrumentNews(instrumentId);
      setRefresh(r);
      if (r.status === "refreshed") setReloadTick((t) => t + 1);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Rafraîchissement impossible");
    } finally {
      setRefreshing(false);
    }
  }

  async function loadMore() {
    if (!nextCursor) return;
    const page = await listInstrumentNews(instrumentId, {
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
    exportAsJson(`nexora-actualites-${instrumentId}.json`, visibleItems);
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
        <button type="button" className="export-button" onClick={handleRefresh} disabled={refreshing}>
          {refreshing ? "Recherche d'actualités…" : "Rafraîchir les actualités"}
        </button>
        <button type="button" className="export-button" onClick={handleExport} disabled={visibleItems.length === 0}>
          Exporter (JSON)
        </button>
      </div>
      {refresh && <NewsSourceStatus refresh={refresh} />}

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
        <p className="empty-state">Aucune actualité récente pour cet instrument avec ces filtres (aucune source configurée ne le couvre encore ?).</p>
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


function NewsSourceStatus({ refresh }: { refresh: NewsRefresh }) {
  if (refresh.status === "not_configured") {
    return (
      <p className="provider-banner" role="status">
        Les actualités par société viennent de Finnhub (gratuit, clé personnelle). Aucune clé n'est configurée : ajoutez{" "}
        <code>{"FINNHUB_API_KEY=…"}</code> dans le fichier <code>.env</code> puis redémarrez. Détails dans{" "}
        <a href={href("settings")}>Paramètres › Sources</a>.
      </p>
    );
  }
  if (refresh.status === "failed") {
    return (
      <p className="provider-banner" role="status">
        Impossible de récupérer les actualités : {refresh.detail ?? refresh.error_code}. La source est mise en pause automatiquement en cas
        d'échecs répétés ; un administrateur peut la réactiver dans Paramètres › Administration.
      </p>
    );
  }
  if (refresh.status === "not_eligible") return null;
  return (
    <p className="muted" role="status">
      {refresh.status === "refreshed" ? "Actualités mises à jour à l'instant" : refresh.status === "rate_limited" ? refresh.detail : "Actualités en cache"}
      {refresh.last_collected_at ? ` · dernière collecte ${formatDateTime(refresh.last_collected_at)}` : ""} · {refresh.items_total} élément(s) au total ·
      rafraîchies automatiquement toutes les 15 min pour les titres suivis ou détenus.
    </p>
  );
}
