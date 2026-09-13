import { useEffect, useState } from "react";
import { errorMessage, listInstruments } from "../api/client";
import { href } from "../router";
import type { Instrument } from "../types";
import { EventsPage } from "./EventsPage";
import { NewsPage } from "./NewsPage";
import { TimelinePage } from "./TimelinePage";

type Tab = "news" | "timeline" | "events";

/** News & events hub: pick one of the instruments you track, then read its
 * recent news, its contextual timeline, or the upcoming calendar (which can
 * also be shown across every tracked instrument). */
export function NewsHubPage({ initialInstrumentId }: { initialInstrumentId?: string }) {
  const [instruments, setInstruments] = useState<Instrument[]>([]);
  const [instrumentId, setInstrumentId] = useState(initialInstrumentId ?? "");
  const [tab, setTab] = useState<Tab>("news");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listInstruments()
      .then((list) => {
        setInstruments(list);
        if (!instrumentId && list.length > 0) setInstrumentId(list[0].id);
      })
      .catch((err: unknown) => setError(errorMessage(err)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <section aria-label="Actualités et événements">
      <h2>Actualités & événements</h2>
      <p className="muted">
        Faits, synthèses et estimations sourcés pour chaque instrument suivi, avec provenance, dates et niveau de confiance ; calendrier des événements à venir dans votre fuseau. Les sources se configurent dans Paramètres.
      </p>
      {error && <p className="error-state">{error}</p>}
      <div className="inline-form">
        <label>
          Instrument
          <select value={instrumentId} onChange={(e) => setInstrumentId(e.target.value)}>
            <option value="">— tous (événements seulement) —</option>
            {instruments.map((i) => (
              <option key={i.id} value={i.id}>
                {i.symbol} — {i.name}
              </option>
            ))}
          </select>
        </label>
        {instrumentId && <a href={href("markets", instrumentId)}>Ouvrir la fiche de l'instrument</a>}
      </div>
      {instruments.length === 0 && (
        <p className="empty-state">
          Aucun instrument suivi : <a href={href("markets")}>cherchez-en un</a> et ajoutez-le à votre liste de suivi ou à un portefeuille.
        </p>
      )}
      <div role="tablist" className="subtabs" aria-label="Type de contenu">
        {(
          [
            ["news", "Actualités"],
            ["timeline", "Chronologie"],
            ["events", "Événements à venir"],
          ] as [Tab, string][]
        ).map(([id, label]) => (
          <button key={id} role="tab" aria-selected={tab === id} onClick={() => setTab(id)} disabled={id !== "events" && !instrumentId}>
            {label}
          </button>
        ))}
      </div>
      {tab === "news" && instrumentId && <NewsPage instrumentId={instrumentId} />}
      {tab === "timeline" && instrumentId && <TimelinePage instrumentId={instrumentId} />}
      {tab === "events" && <EventsPage instrumentId={instrumentId || undefined} />}
    </section>
  );
}
