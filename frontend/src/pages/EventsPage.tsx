import { useEffect, useMemo, useState } from "react";
import { ApiError, listUpcomingEvents } from "../api/client";
import { EventCard } from "../components/EventCard";
import type { CalendarEvent } from "../types";
import { useDismissed } from "../hooks/useDismissed";
import { exportAsJson } from "../export";

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
  const [search, setSearch] = useState("");
  const [showDismissed, setShowDismissed] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const { dismissed, dismiss, restore } = useDismissed();

  useEffect(() => {
    setLoading(true);
    setError(null);
    listUpcomingEvents({ assetId, status: status || undefined, tz: timezone })
      .then(setEvents)
      .catch((err: unknown) => setError(err instanceof ApiError ? err.message : "Erreur de chargement"))
      .finally(() => setLoading(false));
  }, [assetId, status, timezone]);

  const visibleEvents = useMemo(() => {
    const needle = search.trim().toLowerCase();
    return events.filter((event) => {
      if (!showDismissed && dismissed.has(event.id)) return false;
      if (needle && !event.type.toLowerCase().includes(needle)) return false;
      return true;
    });
  }, [events, search, dismissed, showDismissed]);
  const hiddenCount = events.filter((e) => dismissed.has(e.id)).length;

  function handleExport() {
    exportAsJson(`nexora-evenements-${assetId}.json`, visibleEvents);
  }

  return (
    <section aria-label="Événements à venir">
      <div className="toolbar">
        <label className="search-bar">
          Rechercher
          <input
            type="search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Type d'événement…"
            aria-label="Rechercher dans les événements"
          />
        </label>
        <button type="button" className="export-button" onClick={handleExport} disabled={visibleEvents.length === 0}>
          Exporter (JSON)
        </button>
      </div>

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
        {hiddenCount > 0 && (
          <label className="dismissed-toggle">
            <input type="checkbox" checked={showDismissed} onChange={(e) => setShowDismissed(e.target.checked)} />
            Afficher les {hiddenCount} élément(s) masqué(s)
          </label>
        )}
      </div>
      <p id="tz-hint" className="empty-state" style={{ display: "none" }}>
        Nom de fuseau IANA, ex. Europe/Paris
      </p>

      {loading && <p className="loading-state">Chargement…</p>}
      {error && <p className="error-state">{error}</p>}
      {!loading && !error && visibleEvents.length === 0 && (
        <p className="empty-state">Aucun événement à venir pour cet actif.</p>
      )}
      {visibleEvents.map((event) => (
        <EventCard
          key={event.id}
          event={event}
          dismissed={dismissed.has(event.id)}
          onDismiss={() => dismiss(event.id)}
          onRestore={() => restore(event.id)}
        />
      ))}
    </section>
  );
}
