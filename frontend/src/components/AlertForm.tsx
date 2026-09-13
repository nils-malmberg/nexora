import { useEffect, useState } from "react";
import { createAlert, deleteAlert, errorMessage, listAlerts, rearmAlert } from "../api/client";
import { formatAmount, formatDateTime } from "../format";
import { href } from "../router";
import { notifyNotificationsChanged } from "./NotificationsBell";
import type { AlertKind, Instrument, PriceAlert, Quote } from "../types";
import { ALERT_KINDS, ALERT_KIND_LABELS } from "../types";

/** Create and manage informational alerts for one instrument. A triggered
 * alert only produces an in-app notification: nothing is ever executed. */
export function AlertForm({ instrument, quote }: { instrument: Instrument; quote: Quote | null }) {
  const [alerts, setAlerts] = useState<PriceAlert[]>([]);
  const [kind, setKind] = useState<AlertKind>("price_above");
  const [threshold, setThreshold] = useState("");
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  function reload() {
    listAlerts(instrument.id)
      .then((a) => {
        setAlerts(a);
        notifyNotificationsChanged();
      })
      .catch((err: unknown) => setError(errorMessage(err)));
  }

  useEffect(reload, [instrument.id]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setMessage(null);
    setBusy(true);
    try {
      const created = await createAlert({ instrument_id: instrument.id, kind, threshold, note: note || undefined });
      setThreshold("");
      setNote("");
      setMessage(created.active ? "Alerte enregistrée : elle sera évaluée à chaque rafraîchissement des cours." : "Seuil déjà franchi avec les données en cache : une notification a été créée.");
      reload();
    } catch (err) {
      setError(errorMessage(err, "Impossible de créer l'alerte"));
    } finally {
      setBusy(false);
    }
  }

  async function act(fn: () => Promise<unknown>) {
    setError(null);
    try {
      await fn();
      reload();
    } catch (err) {
      setError(errorMessage(err, "Action impossible"));
    }
  }

  const unit = kind === "move_pct" ? "%" : quote?.currency ?? instrument.currency;

  return (
    <section aria-label="Alertes informatives" className="alert-form">
      <h3>Alertes informatives</h3>
      <p className="muted">
        Soyez prévenu (dans l'application uniquement) quand le cours franchit un seuil. Évaluées sur les données en cache, sans requête supplémentaire ; une alerte déclenchée se désactive et peut être réarmée. Rien n'est exécuté. <a href={href("help", "alertes-informatives")}>En savoir plus</a>
      </p>
      <form className="inline-form" onSubmit={submit}>
        <label>
          Condition
          <select value={kind} onChange={(e) => setKind(e.target.value as AlertKind)}>
            {ALERT_KINDS.map((k) => (
              <option key={k} value={k}>
                {ALERT_KIND_LABELS[k]}
              </option>
            ))}
          </select>
        </label>
        <label>
          Seuil ({unit})
          <input type="number" step="any" min="0" required value={threshold} onChange={(e) => setThreshold(e.target.value)} placeholder={kind === "move_pct" ? "5" : quote?.price ?? ""} />
        </label>
        <label>
          Note
          <input type="text" maxLength={200} value={note} onChange={(e) => setNote(e.target.value)} placeholder="facultatif" />
        </label>
        <button type="submit" className="primary-button" disabled={busy || !threshold}>
          Créer l'alerte
        </button>
      </form>
      {message && (
        <p className="muted" role="status">
          {message}
        </p>
      )}
      {error && <p className="error-state">{error}</p>}
      {alerts.length > 0 && (
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Condition</th>
                <th>Seuil</th>
                <th>État</th>
                <th>Dernière valeur</th>
                <th>Note</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {alerts.map((a) => (
                <tr key={a.id}>
                  <td>{a.kind_label}</td>
                  <td>{a.kind === "move_pct" ? `±${formatAmount(a.threshold, undefined, 2)} %` : formatAmount(a.threshold, instrument.currency)}</td>
                  <td>
                    {a.active ? <span className="badge quote-fresh">active</span> : <span className="badge quote-cached">déclenchée {a.triggered_at ? formatDateTime(a.triggered_at) : ""}</span>}
                  </td>
                  <td>{a.last_value ? formatAmount(a.last_value, instrument.currency) : "—"}</td>
                  <td className="muted">{a.note ?? ""}</td>
                  <td>
                    {!a.active && (
                      <button type="button" className="link-button" onClick={() => act(() => rearmAlert(a.id))}>
                        Réarmer
                      </button>
                    )}{" "}
                    <button type="button" className="link-button" onClick={() => act(() => deleteAlert(a.id))}>
                      Supprimer
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
