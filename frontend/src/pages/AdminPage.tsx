import { useEffect, useState } from "react";
import {
  adminAudit,
  adminListMarketProviders,
  adminListNewsProviders,
  adminListRuns,
  adminSetMarketProvider,
  adminSetNewsProvider,
  adminSyncNewsProvider,
  errorMessage,
} from "../api/client";
import { formatDateTime } from "../format";
import type { AuditEntry, IngestionRun, MarketProviderState, NewsProviderStatus } from "../types";

/** Admin console (admin role only): pause/resume market providers, manage
 * news sources and their ingestion runs, read the audit trail. Never shows a
 * credential — only the *name* of the env var holding it. */
export function AdminPage() {
  const [market, setMarket] = useState<MarketProviderState[]>([]);
  const [news, setNews] = useState<NewsProviderStatus[]>([]);
  const [runs, setRuns] = useState<Record<string, IngestionRun[]>>({});
  const [audit, setAudit] = useState<AuditEntry[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  async function reload() {
    try {
      const [m, n, a] = await Promise.all([adminListMarketProviders(), adminListNewsProviders(), adminAudit()]);
      setMarket(m);
      setNews(n);
      setAudit(a);
    } catch (err) {
      setError(errorMessage(err, "Accès refusé"));
    }
  }

  useEffect(() => {
    reload();
  }, []);

  async function toggleMarket(name: string, enabled: boolean) {
    setBusy(name);
    try {
      await adminSetMarketProvider(name, enabled, enabled ? undefined : "désactivé par l'administrateur");
      await reload();
    } catch (err) {
      setError(errorMessage(err, "Action impossible"));
    } finally {
      setBusy(null);
    }
  }

  async function toggleNews(id: string, enabled: boolean) {
    setBusy(id);
    try {
      await adminSetNewsProvider(id, enabled);
      await reload();
    } catch (err) {
      setError(errorMessage(err, "Action impossible"));
    } finally {
      setBusy(null);
    }
  }

  async function sync(id: string) {
    setBusy(id);
    setError(null);
    try {
      await adminSyncNewsProvider(id);
      setRuns({ ...runs, [id]: await adminListRuns(id) });
      await reload();
    } catch (err) {
      setError(errorMessage(err, "Synchronisation impossible"));
    } finally {
      setBusy(null);
    }
  }

  async function showRuns(id: string) {
    try {
      setRuns({ ...runs, [id]: await adminListRuns(id) });
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  return (
    <section aria-label="Administration">
      <h2>Administration</h2>
      <p className="muted">
        Réservé aux administrateurs. Une source désactivée ne fait plus aucune requête ; une source qui échoue de façon répétée se désactive d'elle-même (disjoncteur) et doit être réactivée ici après enquête — jamais de re-tentative en boucle.
      </p>
      {error && <p className="error-state">{error}</p>}

      <h3>Fournisseurs de données de marché</h3>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>Fournisseur</th>
              <th>État</th>
              <th>Disjoncteur</th>
              <th>Échecs consécutifs</th>
              <th>Dernier succès</th>
              <th>Dernière erreur</th>
              <th>Variable d'env. (clé)</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {market.map((m) => (
              <tr key={m.name}>
                <td>
                  <strong>{m.name}</strong>
                  {m.license_note && <div className="muted">{m.license_note}</div>}
                </td>
                <td>{m.enabled ? "activé" : `désactivé (${m.disabled_reason ?? "—"})`}</td>
                <td>{m.circuit_state}</td>
                <td>{m.consecutive_failures}</td>
                <td>{m.last_success_at ? formatDateTime(m.last_success_at) : "—"}</td>
                <td className="muted">{m.last_error ?? "—"}</td>
                <td className="muted">{m.env_var ?? "aucune"}</td>
                <td>
                  <button type="button" className="link-button" disabled={busy === m.name} onClick={() => toggleMarket(m.name, !m.enabled)}>
                    {m.enabled ? "Désactiver" : "Réactiver"}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <h3>Sources d'actualités et d'événements</h3>
      {news.length === 0 ? (
        <p className="empty-state">Aucune source configurée. Ajoutez-en avec les scripts du dossier backend/scripts (SEC EDGAR, Finnhub…) après vérification des licences.</p>
      ) : (
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Source</th>
                <th>Type</th>
                <th>État</th>
                <th>Disjoncteur</th>
                <th>Échecs</th>
                <th>Dernier succès</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {news.map((n) => (
                <tr key={n.id}>
                  <td>
                    <strong>{n.name}</strong>
                    {n.license_note && <div className="muted">{n.license_note}</div>}
                  </td>
                  <td>{n.type}</td>
                  <td>{n.enabled ? "activée" : "désactivée"}</td>
                  <td>{n.circuit_state}</td>
                  <td>{n.consecutive_failures}</td>
                  <td>{n.last_success_at ? formatDateTime(n.last_success_at) : "—"}</td>
                  <td>
                    <button type="button" className="link-button" disabled={busy === n.id} onClick={() => toggleNews(n.id, !n.enabled)}>
                      {n.enabled ? "Désactiver" : "Réactiver"}
                    </button>{" "}
                    <button type="button" className="link-button" disabled={busy === n.id || !n.enabled} onClick={() => sync(n.id)} title="Une seule requête, jamais en boucle">
                      Synchroniser maintenant
                    </button>{" "}
                    <button type="button" className="link-button" onClick={() => showRuns(n.id)}>
                      Historique
                    </button>
                    {runs[n.id] && (
                      <ul className="plain-list">
                        {runs[n.id].slice(0, 10).map((r) => (
                          <li key={r.id}>
                            {formatDateTime(r.started_at)} — {r.status} {r.error_code ? `(${r.error_code})` : ""} — {JSON.stringify(r.counts)}
                          </li>
                        ))}
                      </ul>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <h3>Journal d'audit (100 derniers)</h3>
      <ul className="plain-list">
        {audit.map((a) => (
          <li key={a.id}>
            {formatDateTime(a.created_at)} — <strong>{a.action}</strong> {a.target_type ? `${a.target_type} ${a.target_id ?? ""}` : ""} {Object.keys(a.metadata).length > 0 && <span className="muted">{JSON.stringify(a.metadata)}</span>}
          </li>
        ))}
      </ul>
    </section>
  );
}
