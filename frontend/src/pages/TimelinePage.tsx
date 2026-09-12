import { useEffect, useState } from "react";
import { ApiError, getAssetTimeline } from "../api/client";
import { NewsCard } from "../components/NewsCard";
import { EventCard } from "../components/EventCard";
import { CATEGORIES, CATEGORY_LABELS } from "../types";
import type { TimelineEntry } from "../types";

const GRANULARITIES = [
  { value: "day", label: "Jour" },
  { value: "month", label: "Mois" },
  { value: "quarter", label: "Trimestre" },
  { value: "year", label: "Année" },
];

export function TimelinePage({ assetId }: { assetId: string }) {
  const [entries, setEntries] = useState<TimelineEntry[]>([]);
  const [granularity, setGranularity] = useState("month");
  const [category, setCategory] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    getAssetTimeline(assetId, { granularity, category: category || undefined })
      .then(setEntries)
      .catch((err: unknown) => setError(err instanceof ApiError ? err.message : "Erreur de chargement"))
      .finally(() => setLoading(false));
  }, [assetId, granularity, category]);

  let lastBucket: string | null = null;

  return (
    <section aria-label="Chronologie">
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
      </div>

      {loading && <p className="loading-state">Chargement…</p>}
      {error && <p className="error-state">{error}</p>}
      {!loading && !error && entries.length === 0 && (
        <p className="empty-state">Aucun élément de chronologie pour cet actif.</p>
      )}
      {entries.map((entry) => {
        const showBucketHeader = entry.bucket !== lastBucket;
        lastBucket = entry.bucket;
        const key = entry.news_item?.id ?? entry.event?.id ?? `${entry.entry_type}-${entry.effective_at}`;
        return (
          <div key={key}>
            {showBucketHeader && <div className="timeline-bucket">{entry.bucket}</div>}
            {entry.date_basis === "publication_date" && (
              <p className="prediction-warning" role="note">
                Date d'événement inconnue : positionné selon sa date de publication.
              </p>
            )}
            {entry.news_item && <NewsCard item={entry.news_item} />}
            {entry.event && <EventCard event={entry.event} />}
          </div>
        );
      })}
    </section>
  );
}
