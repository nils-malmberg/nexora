import type { NewsItem } from "../types";
import { CATEGORY_LABELS } from "../types";
import { ConfidenceBadge, FreshnessBadge, KindBadge, StaleBadge } from "./Badges";
import { formatDateTime } from "../format";

export function NewsCard({ item }: { item: NewsItem }) {
  const cardClass = ["card", item.stale ? "stale" : "", `kind-${item.kind}`].filter(Boolean).join(" ");
  return (
    <article className={cardClass} aria-label={item.title}>
      <div className="card-header">
        <KindBadge kind={item.kind} />
        <span className="badge">{CATEGORY_LABELS[item.category] ?? item.category}</span>
        <FreshnessBadge freshness={item.freshness_at_collection} />
        <ConfidenceBadge confidence={item.confidence} />
        <StaleBadge stale={item.stale} />
      </div>
      <h3>{item.title}</h3>
      {item.kind === "prediction" && (
        <p className="prediction-warning" role="note">
          Estimation ou prédiction : contenu séparé, incertain, non un conseil d'investissement.
        </p>
      )}
      {(item.summary ?? item.excerpt) && <p className="excerpt">{item.summary ?? item.excerpt}</p>}
      <div className="meta-row">
        <span>{item.provenance}</span>
        <span>Publié : {formatDateTime(item.publication_at)}</span>
        {item.event_at && <span>Événement : {formatDateTime(item.event_at, item.timezone)}</span>}
        <a href={item.url} target="_blank" rel="noreferrer noopener">
          Voir la source
        </a>
      </div>
      {(item.duplicate_of.length > 0 || item.corroborated_by.length > 0) && (
        <div className="related-list">
          {item.corroborated_by.length > 0 && (
            <div>Corroboré par {item.corroborated_by.length} source(s) indépendante(s).</div>
          )}
          {item.duplicate_of.length > 0 && <div>Doublon probable d'un autre article déjà listé.</div>}
        </div>
      )}
    </article>
  );
}
