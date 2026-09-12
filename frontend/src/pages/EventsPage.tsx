import { useEffect, useState } from "react";
import { ApiError, listUpcomingEvents } from "../api/client";
import { EventCard } from "../components/EventCard";
import type { CalendarEvent } from "../types";

const STATUSES = [
  { value: "", label: "Tous (hors annulés)" },
  { value: "confirme", label: "Confirmé" },
  { value: "previsionnel", label: "Prévisionnel" },
  { value: "reporte", label: "Reporté" },
  { value: "annule", label: "Annulé" },
  { value: "unknown", label: "Inconnu" },
];

export function EventsPage({ assetId }: { assetId: string }) {
  const [events, setEvents] = useState<CalendarEvent[]>([]);
  const [status, setStatus] = useState("");
  const [timezone, setTimezone] = useState(() => Intl.DateTimeFormat().resolvedOptions().timeZone);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    listUpcomingEvents({ assetId, status: status || undefined, tz: timezone })
      .then(setEvents)
      .catch((err: unknown) => setError(err instanceof ApiError ? err.message : "Erreur de chargement"))
      .finally(() => setLoading(false));
  }, [assetId, status, timezone]);

  return (
    <section aria-label="Événements à venir">
      <div className="filters">
        <label>
          Statut
          <select value={status} onChange={(e) => setStatus(e.target.value)}>
            {STATUSES.map((s) => (
              <option key={s.value} value={s.value}>
                {s.label}
              </option>
            ))}
          </select>
        </label>
        <label>
          Fuseau horaire
          <input
            value={timezone}
            onChange={(e) => setTimezone(e.target.value)}
            aria-describedby="tz-hint"
            style={{ padding: "6px 8px", borderRadius: 6 }}
          />
        </label>
      </div>
      <p id="tz-hint" className="empty-state" style={{ display: "none" }}>
        Nom de fuseau IANA, ex. Europe/Paris
      </p>

      {loading && <p className="loading-state">Chargement…</p>}
      {error && <p className="error-state">{error}</p>}
      {!loading && !error && events.length === 0 && (
        <p className="empty-state">Aucun événement à venir pour cet actif.</p>
      )}
      {events.map((event) => (
        <EventCard key={event.id} event={event} />
      ))}
    </section>
  );
}
