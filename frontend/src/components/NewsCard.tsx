import type { NewsItem } from "../types";
import { CATEGORY_LABELS } from "../types";
import { ConfidenceBadge, FreshnessBadge, KindBadge, StaleBadge } from "./Badges";
import { formatDateTime } from "../format";

export function NewsCard({
  item,
  dismissed = false,
  onDismiss,
  onRestore,
}: {
  item: NewsItem;
  dismissed?: boolean;
  onDismiss?: () => void;
  onRestore?: () => void;
}) {
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

      <details className="details-toggle">
        <summary>Détails</summary>
        <dl className="details-grid">
          <dt>Fournisseur</dt>
          <dd>{item.provider_name}</dd>
          <dt>Citation</dt>
          <dd>{item.citation ?? "—"}</dd>
          <dt>Langue</dt>
          <dd>{item.language ?? "inconnue"}</dd>
          <dt>Statut de vérification</dt>
          <dd>{item.verification_status}</dd>
          <dt>Score de pertinence</dt>
          <dd>{item.relevance_score.toFixed(3)}</dd>
          <dt>Collecté le</dt>
          <dd>{formatDateTime(item.collected_at)}</dd>
          <dt>Mis à jour le</dt>
          <dd>{formatDateTime(item.updated_at)}</dd>
        </dl>
      </details>

      <div className="card-actions">
        {dismissed ? (
          <button type="button" onClick={onRestore} className="link-button">
            Réafficher
          </button>
        ) : (
          <button type="button" onClick={onDismiss} className="link-button">
            Masquer localement
          </button>
        )}
      </div>
    </article>
  );
}
