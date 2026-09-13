import type { CalendarEvent } from "../types";
import { formatDateTime, formatDate } from "../format";

const STATUS_LABELS: Record<string, string> = {
  confirme: "Confirmé",
  previsionnel: "Prévisionnel",
  reporte: "Reporté",
  annule: "Annulé",
  unknown: "Statut inconnu",
};

export function EventCard({
  event,
  instrumentLabel,
  dismissed = false,
  onDismiss,
  onRestore,
}: {
  event: CalendarEvent;
  instrumentLabel?: string;
  dismissed?: boolean;
  onDismiss?: () => void;
  onRestore?: () => void;
}) {
  return (
    <article className={`card ${event.stale ? "stale" : ""}`} aria-label={event.type}>
      <div className="card-header">
        <span className="badge event-status">{STATUS_LABELS[event.status] ?? event.status}</span>
        {event.stale && <span className="badge stale">Non re-vérifié récemment</span>}
      </div>
      <h3>
        {event.type.replaceAll("_", " ")}
        {instrumentLabel && <span className="muted"> — {instrumentLabel}</span>}
      </h3>
      <div className="meta-row">
        {event.starts_at ? (
          <span>{formatDateTime(event.starts_at, event.timezone)}</span>
        ) : (
          <span>{event.period_label ? `Période : ${event.period_label}` : "Date inconnue"}</span>
        )}
        {event.amount !== null && (
          <span>
            Montant : {event.amount} {event.currency}
          </span>
        )}
        <span>Dernière vérification : {formatDate(event.last_verified_at)}</span>
      </div>
      <div className="meta-row">
        {event.sources.map((source) => (
          <a key={source.url} href={source.url} target="_blank" rel="noreferrer noopener">
            Source
          </a>
        ))}
      </div>
      {event.status_history.length > 1 && (
        <div className="status-history">
          Historique : {event.status_history.map((h) => STATUS_LABELS[h.new_status] ?? h.new_status).join(" → ")}
        </div>
      )}

      <details className="details-toggle">
        <summary>Détails</summary>
        <dl className="details-grid">
          <dt>Instrument</dt>
          <dd>{instrumentLabel ?? event.instrument_id}</dd>
          <dt>Fuseau horaire</dt>
          <dd>{event.timezone}</dd>
          <dt>Nombre de sources</dt>
          <dd>{event.sources.length}</dd>
          <dt>Historique de statut</dt>
          <dd>
            {event.status_history.length === 0
              ? "—"
              : event.status_history.map((h) => `${STATUS_LABELS[h.new_status] ?? h.new_status} (${formatDate(h.changed_at)})`).join(", ")}
          </dd>
        </dl>
      </details>

      {(onDismiss || onRestore) && (
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
      )}
    </article>
  );
}
