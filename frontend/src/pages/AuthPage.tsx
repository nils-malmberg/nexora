import { useState } from "react";
import { ApiError, login, register } from "../api/client";
import type { AuthResponse } from "../types";

export function AuthPage({ onAuthenticated }: { onAuthenticated: (auth: AuthResponse) => void }) {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [referenceCurrency, setReferenceCurrency] = useState("EUR");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const auth = mode === "login" ? await login(email, password) : await register(email, password, referenceCurrency);
      onAuthenticated(auth);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Erreur de connexion");
    } finally {
      setLoading(false);
    }
  }

  return (
    <section aria-label={mode === "login" ? "Connexion" : "Créer un compte"} className="auth-card">
      <h1>NeXora — Portefeuille</h1>
      <p className="disclaimer">
        Consultation et analyse uniquement. Aucun passage d'ordre, aucune recommandation personnalisée.
      </p>
      <div role="tablist" aria-label="Mode d'authentification">
        <button type="button" role="tab" aria-selected={mode === "login"} onClick={() => setMode("login")}>
          Connexion
        </button>
        <button type="button" role="tab" aria-selected={mode === "register"} onClick={() => setMode("register")}>
          Créer un compte
        </button>
      </div>
      <form onSubmit={handleSubmit} className="form-grid">
        <label>
          Email
          <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" />
        </label>
        <label>
          Mot de passe
          <input
            type="password"
            required
            minLength={10}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete={mode === "login" ? "current-password" : "new-password"}
          />
        </label>
        {mode === "register" && (
          <label>
            Devise de référence
            <input
              value={referenceCurrency}
              onChange={(e) => setReferenceCurrency(e.target.value.toUpperCase())}
              maxLength={8}
            />
          </label>
        )}
        {error && <p className="error-state">{error}</p>}
        <button type="submit" disabled={loading} className="primary-button">
          {mode === "login" ? "Se connecter" : "Créer le compte"}
        </button>
      </form>
    </section>
  );
}
