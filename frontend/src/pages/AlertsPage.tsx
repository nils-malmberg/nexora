import { useEffect, useState } from "react";
import { deleteAlert, deleteNotification, errorMessage, listAlerts, listNotifications, markNotificationsRead, rearmAlert } from "../api/client";
import { EducationNote } from "../components/EducationNote";
import { notifyNotificationsChanged } from "../components/NotificationsBell";
import { formatAmount, formatDateTime } from "../format";
import { href } from "../router";
import type { Notification, PriceAlert } from "../types";

/** All the user's alerts and the notifications they produced. Informational
 * only: reading, re-arming or deleting — never acting on a market. */
export function AlertsPage() {
  const [alerts, setAlerts] = useState<PriceAlert[]>([]);
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [unread, setUnread] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  function reload() {
    setError(null);
    Promise.all([listAlerts(), listNotifications({ limit: 100 })])
      .then(([a, n]) => {
        setAlerts(a);
        setNotifications(n.items);
        setUnread(n.unread);
        notifyNotificationsChanged();
      })
      .catch((err: unknown) => setError(errorMessage(err)))
      .finally(() => setLoading(false));
  }

  useEffect(reload, []);

  async function act(fn: () => Promise<unknown>) {
    setError(null);
    try {
      await fn();
      reload();
    } catch (err) {
      setError(errorMessage(err, "Action impossible"));
    }
  }

  if (loading) return <p className="loading-state">Chargement…</p>;

  return (
    <section aria-label="Alertes et notifications">
      <h2>Alertes et notifications</h2>
      <p className="muted">
        Une alerte compare le dernier cours connu à votre seuil et produit une notification dans l'application — jamais un ordre, jamais un conseil. Créez-en depuis la fiche d'un instrument (<a href={href("markets")}>Marchés</a>).
      </p>
      {error && <p className="error-state">{error}</p>}

      <div className="card-header">
        <h3>Notifications {unread > 0 && <span className="badge quote-fresh">{unread} non lue(s)</span>}</h3>
        {unread > 0 && (
          <button type="button" className="export-button" onClick={() => act(() => markNotificationsRead())}>
            Tout marquer comme lu
          </button>
        )}
      </div>
      {notifications.length === 0 ? (
        <p className="empty-state">Aucune notification pour l'instant.</p>
      ) : (
        <ul className="notification-list">
          {notifications.map((n) => (
            <li key={n.id} className={n.read_at ? "notification read" : "notification"}>
              <div>
                <strong>{n.instrument_id ? <a href={href("markets", n.instrument_id)}>{n.title}</a> : n.title}</strong>
                <p className="muted">{n.body}</p>
                <span className="muted">{formatDateTime(n.created_at)}</span>
              </div>
              <div className="notification-actions">
                {!n.read_at && (
                  <button type="button" className="link-button" onClick={() => act(() => markNotificationsRead([n.id]))}>
                    Marquer lu
                  </button>
                )}
                <button type="button" className="link-button" onClick={() => act(() => deleteNotification(n.id))}>
                  Supprimer
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}

      <h3>Mes alertes</h3>
      {alerts.length === 0 ? (
        <p className="empty-state">Aucune alerte. Sur la fiche d'un instrument, section « Alertes informatives ».</p>
      ) : (
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Instrument</th>
                <th>Condition</th>
                <th>Seuil</th>
                <th>État</th>
                <th>Dernière valeur</th>
                <th>Évaluée</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {alerts.map((a) => (
                <tr key={a.id}>
                  <td>
                    <a href={href("markets", a.instrument.id)}>
                      <strong>{a.instrument.symbol}</strong>
                    </a>{" "}
                    <span className="muted">{a.instrument.name}</span>
                  </td>
                  <td>{a.kind_label}</td>
                  <td>{a.kind === "move_pct" ? `±${formatAmount(a.threshold, undefined, 2)} %` : formatAmount(a.threshold, a.instrument.currency)}</td>
                  <td>{a.active ? <span className="badge quote-fresh">active</span> : <span className="badge quote-cached">déclenchée</span>}</td>
                  <td>{a.last_value ? formatAmount(a.last_value, a.instrument.currency) : "—"}</td>
                  <td className="muted">{a.last_evaluated_at ? formatDateTime(a.last_evaluated_at) : "pas encore"}</td>
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
      <EducationNote slug="alertes-informatives" />
    </section>
  );
}
