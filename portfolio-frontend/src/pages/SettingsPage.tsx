import { useState } from "react";
import { ApiError, deleteMyAccount, exportMyData } from "../api/client";
import { exportAsJson } from "../export";
import type { User } from "../types";

export function SettingsPage({ user, onAccountDeleted }: { user: User; onAccountDeleted: () => void }) {
  const [password, setPassword] = useState("");
  const [confirming, setConfirming] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleExport() {
    try {
      const data = await exportMyData();
      exportAsJson(`nexora-portefeuille-${user.id}.json`, data);
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
      <div className="card">
        <p>
          Connecté en tant que <strong>{user.email}</strong>
        </p>
      </div>

      <div className="card">
        <h3>Export des données</h3>
        <p className="muted">Télécharge un fichier JSON avec tous vos portefeuilles, instruments et transactions.</p>
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
