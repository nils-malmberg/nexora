import { useEffect, useMemo, useState } from "react";
import { ApiError, getInstrumentTimeline } from "../api/client";
import { NewsCard } from "../components/NewsCard";
import { EventCard } from "../components/EventCard";
import { CATEGORIES, CATEGORY_LABELS } from "../types";
import type { TimelineEntry } from "../types";
import { useDismissed } from "../hooks/useDismissed";
import { exportAsJson } from "../export";

const GRANULARITIES = [
  { value: "day", label: "Jour" },
  { value: "month", label: "Mois" },
  { value: "quarter", label: "Trimestre" },
  { value: "year", label: "Année" },
];

function entryId(entry: TimelineEntry): string {
  return entry.news_item?.id ?? entry.event?.id ?? `${entry.entry_type}-${entry.effective_at}`;
}

function entryLabel(entry: TimelineEntry): string {
  return entry.news_item?.title ?? entry.event?.type ?? "";
}

export function TimelinePage({ instrumentId }: { instrumentId: string }) {
  const [entries, setEntries] = useState<TimelineEntry[]>([]);
  const [granularity, setGranularity] = useState("month");
  const [category, setCategory] = useState("");
  const [search, setSearch] = useState("");
  const [showDismissed, setShowDismissed] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const { dismissed, dismiss, restore } = useDismissed();

  useEffect(() => {
    setLoading(true);
    setError(null);
    getInstrumentTimeline(instrumentId, { granularity, category: category || undefined })
      .then(setEntries)
      .catch((err: unknown) => setError(err instanceof ApiError ? err.message : "Erreur de chargement"))
      .finally(() => setLoading(false));
  }, [instrumentId, granularity, category]);

  // Entries are already fully loaded (no cursor pagination on this endpoint -
  // see backend/README.md "Limites connues"), so text search filters
  // client-side rather than round-tripping to the API.
  const visibleEntries = useMemo(() => {
    const needle = search.trim().toLowerCase();
    return entries.filter((entry) => {
      if (!showDismissed && dismissed.has(entryId(entry))) return false;
      if (needle && !entryLabel(entry).toLowerCase().includes(needle)) return false;
      return true;
    });
  }, [entries, search, dismissed, showDismissed]);
  const hiddenCount = entries.filter((e) => dismissed.has(entryId(e))).length;

  function handleExport() {
    exportAsJson(
      `nexora-chronologie-${instrumentId}.json`,
      visibleEntries.map((e) => e.news_item ?? e.event),
    );
  }

  let lastBucket: string | null = null;

  return (
    <section aria-label="Chronologie">
      <div className="toolbar">
        <label className="search-bar">
          Rechercher
          <input
            type="search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Titre ou type d'événement…"
            aria-label="Rechercher dans la chronologie"
          />
        </label>
        <button type="button" className="export-button" onClick={handleExport} disabled={visibleEntries.length === 0}>
          Exporter (JSON)
        </button>
      </div>

      <div className="filters">
        <label>
          Granularité
          <select value={granularity} onChange={(e) => setGranularity(e.target.value)}>
            {GRANULARITIES.map((g) => (
              <option key={g.value} value={g.value}>
                {g.label}
              </option>
            ))}
          </select>
        </label>
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
        {hiddenCount > 0 && (
          <label className="dismissed-toggle">
            <input type="checkbox" checked={showDismissed} onChange={(e) => setShowDismissed(e.target.checked)} />
            Afficher les {hiddenCount} élément(s) masqué(s)
          </label>
        )}
      </div>

      {loading && <p className="loading-state">Chargement…</p>}
      {error && <p className="error-state">{error}</p>}
      {!loading && !error && visibleEntries.length === 0 && (
        <p className="empty-state">Aucun élément de chronologie pour cet actif.</p>
      )}
      {visibleEntries.map((entry) => {
        const showBucketHeader = entry.bucket !== lastBucket;
        lastBucket = entry.bucket;
        const id = entryId(entry);
        return (
          <div key={id}>
            {showBucketHeader && <div className="timeline-bucket">{entry.bucket}</div>}
            {entry.date_basis === "publication_date" && (
              <p className="prediction-warning" role="note">
                Date d'événement inconnue : positionné selon sa date de publication.
              </p>
            )}
            {entry.news_item && (
              <NewsCard
                item={entry.news_item}
                dismissed={dismissed.has(id)}
                onDismiss={() => dismiss(id)}
                onRestore={() => restore(id)}
              />
            )}
            {entry.event && (
              <EventCard
                event={entry.event}
                dismissed={dismissed.has(id)}
                onDismiss={() => dismiss(id)}
                onRestore={() => restore(id)}
              />
            )}
          </div>
        );
      })}
    </section>
  );
}
