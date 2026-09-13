import { useEffect, useState } from "react";
import { ApiError, deleteMyAccount, errorMessage, exportMyData, getProvidersStatus, listSessions, revokeOtherSessions, updateProfile } from "../api/client";
import { exportAsJson } from "../export";
import { formatDateTime } from "../format";
import { href } from "../router";
import type { ProvidersOverview, SessionInfo, User } from "../types";

export function SettingsPage({ user, onAccountDeleted, onUserUpdated }: { user: User; onAccountDeleted: () => void; onUserUpdated: (user: User) => void }) {
  const [password, setPassword] = useState("");
  const [confirming, setConfirming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [displayName, setDisplayName] = useState(user.display_name ?? "");
  const [referenceCurrency, setReferenceCurrency] = useState(user.reference_currency);
  const [timezone, setTimezone] = useState(user.display_timezone);
  const [saved, setSaved] = useState<string | null>(null);
  const [sessions, setSessions] = useState<SessionInfo[]>([]);
  const [providers, setProviders] = useState<ProvidersOverview | null>(null);

  useEffect(() => {
    listSessions().then(setSessions).catch(() => setSessions([]));
    getProvidersStatus().then(setProviders).catch(() => setProviders(null));
  }, []);

  async function saveProfile(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSaved(null);
    try {
      const updated = await updateProfile({ display_name: displayName, reference_currency: referenceCurrency, display_timezone: timezone });
      onUserUpdated(updated);
      setSaved("Profil enregistré.");
    } catch (err) {
      setError(errorMessage(err, "Enregistrement impossible"));
    }
  }

  async function revokeOthers() {
    try {
      await revokeOtherSessions();
      setSessions(await listSessions());
      setSaved("Les autres sessions ont été déconnectées.");
    } catch (err) {
      setError(errorMessage(err, "Action impossible"));
    }
  }

  async function handleExport() {
    try {
      const data = await exportMyData();
      exportAsJson(`nexora-export-${user.id}.json`, data);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Export impossible");
    }
  }

  async function handleDelete(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await deleteMyAccount(password);
      onAccountDeleted();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Mot de passe incorrect");
    }
  }

  return (
    <section aria-label="Paramètres">
      <h2>Paramètres</h2>
      <form className="card" onSubmit={saveProfile}>
        <h3>Profil</h3>
        <p>
          Connecté en tant que <strong>{user.email}</strong>
          {user.is_admin && <span className="badge"> administrateur</span>}
        </p>
        <div className="form-grid">
          <label>
            Nom affiché
            <input value={displayName} onChange={(e) => setDisplayName(e.target.value)} maxLength={120} />
          </label>
          <label>
            Devise de référence
            <input value={referenceCurrency} onChange={(e) => setReferenceCurrency(e.target.value.toUpperCase())} maxLength={8} />
          </label>
          <label>
            Fuseau horaire d'affichage (IANA)
            <input value={timezone} onChange={(e) => setTimezone(e.target.value)} maxLength={64} />
          </label>
          <button type="submit" className="primary-button">
            Enregistrer
          </button>
        </div>
        {saved && <p className="muted" role="status">{saved}</p>}
      </form>

      <div className="card">
        <h3>Sessions actives</h3>
        <ul className="plain-list">
          {sessions.map((s) => (
            <li key={s.id}>
              {s.current ? <strong>Cette session</strong> : "Autre session"} — dernière activité {formatDateTime(s.last_seen_at)} — {s.user_agent ?? "navigateur inconnu"}
            </li>
          ))}
        </ul>
        <button type="button" className="export-button" onClick={revokeOthers} disabled={sessions.length < 2}>
          Déconnecter les autres sessions
        </button>
      </div>

      <div className="card">
        <h3>Sources de données</h3>
        {providers ? (
          <>
            <ul className="plain-list">
              {providers.market.map((m) => (
                <li key={m.role}>
                  <strong>{m.role === "equity" ? "Actions / ETF / indices" : m.role === "crypto" ? "Crypto-actifs" : "Taux de change"}</strong> : {m.name} — {m.enabled ? (m.healthy ? "opérationnel" : `dégradé (${m.circuit_state})`) : "désactivé"}
                  {m.attribution && <span className="muted"> · {m.attribution}</span>}
                  {m.license_note && <div className="muted">{m.license_note}</div>}
                </li>
              ))}
              {providers.news.map((n) => (
                <li key={n.id}>
                  <strong>Actualités</strong> : {n.name} ({n.type}) — {n.enabled ? (n.healthy ? "opérationnel" : `dégradé (${n.circuit_state})`) : "désactivé"}
                  {n.license_note && <div className="muted">{n.license_note}</div>}
                </li>
              ))}
              <li>
                <strong>Actualités par société</strong> : {providers.auto_news.provider} — {providers.auto_news.configured ? "configuré" : "non configuré"}
                <div className="muted">{providers.auto_news.detail}</div>
                {!providers.auto_news.configured && (
                  <div className="muted">
                    Créez un compte gratuit sur finnhub.io, copiez la clé API dans <code>{providers.auto_news.env_var}=…</code> du fichier <code>.env</code>, puis
                    redémarrez (<code>docker compose up -d</code>). Les feeds sont créés automatiquement pour chaque action ou ETF suivi.
                  </div>
                )}
              </li>
              <li>
                <strong>Fondamentaux (aide à la décision)</strong> : {providers.fundamentals.provider} — {providers.fundamentals.configured ? "configuré" : "non configuré"}
                <div className="muted">{providers.fundamentals.detail}</div>
              </li>
              {providers.news.length === 0 && <li className="muted">Aucune autre source d'actualités configurée (flux RSS/ICS : voir Paramètres › Administration).</li>}
            </ul>
            <p className="muted">
              Cotations rafraîchies au plus toutes les {providers.quote_freshness_minutes} minutes. Module de prédiction : {providers.prediction_enabled ? "activé" : "désactivé"}.
            </p>
          </>
        ) : (
          <p className="muted">Statut indisponible.</p>
        )}
        {user.is_admin && (
          <p>
            <a href={href("admin")}>Administration des sources</a>
          </p>
        )}
      </div>

      <div className="card">
        <h3>Export des données</h3>
        <p className="muted">Télécharge un fichier JSON avec tous vos portefeuilles, instruments, transactions, liste de suivi, imports et expériences.</p>
        <button type="button" className="export-button" onClick={handleExport}>
          Exporter mes données (JSON)
        </button>
      </div>

      <div className="card">
        <h3>Supprimer le compte</h3>
        <p className="muted">
          Action irréversible : supprime définitivement le compte et toutes les données associées (portefeuilles,
          instruments, transactions).
        </p>
        {!confirming ? (
          <button type="button" className="danger-button" onClick={() => setConfirming(true)}>
            Supprimer mon compte
          </button>
        ) : (
          <form onSubmit={handleDelete} className="inline-form">
            <label>
              Confirmez votre mot de passe
              <input type="password" required value={password} onChange={(e) => setPassword(e.target.value)} />
            </label>
            <button type="submit" className="danger-button">
              Confirmer la suppression définitive
            </button>
            <button type="button" onClick={() => setConfirming(false)}>
              Annuler
            </button>
          </form>
        )}
        {error && <p className="error-state">{error}</p>}
      </div>
    </section>
  );
}
