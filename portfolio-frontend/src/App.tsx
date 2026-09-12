import { useEffect, useState } from "react";
import { logout as apiLogout, me } from "./api/client";
import { setCsrfToken } from "./authStore";
import { AuthPage } from "./pages/AuthPage";
import { PortfoliosPage } from "./pages/PortfoliosPage";
import { InstrumentsPage } from "./pages/InstrumentsPage";
import { SettingsPage } from "./pages/SettingsPage";
import type { AuthResponse, User } from "./types";

type Tab = "portfolios" | "instruments" | "settings";

const TABS: { id: Tab; label: string }[] = [
  { id: "portfolios", label: "Portefeuilles" },
  { id: "instruments", label: "Instruments" },
  { id: "settings", label: "Paramètres" },
];

export function App() {
  const [user, setUser] = useState<User | null>(null);
  const [checkingSession, setCheckingSession] = useState(true);
  const [activeTab, setActiveTab] = useState<Tab>("portfolios");

  useEffect(() => {
    me()
      .then((auth) => {
        setCsrfToken(auth.csrf_token);
        setUser(auth.user);
      })
      .catch(() => {
        // No valid session - stay on the auth screen, not an error to surface.
      })
      .finally(() => setCheckingSession(false));
  }, []);

  function handleAuthenticated(auth: AuthResponse) {
    setCsrfToken(auth.csrf_token);
    setUser(auth.user);
  }

  async function handleLogout() {
    await apiLogout();
    setCsrfToken(null);
    setUser(null);
  }

  function handleAccountDeleted() {
    setCsrfToken(null);
    setUser(null);
  }

  if (checkingSession) {
    return <p className="loading-state">Chargement…</p>;
  }

  if (!user) {
    return <AuthPage onAuthenticated={handleAuthenticated} />;
  }

  return (
    <>
      <header className="app-header">
        <div className="app-header-row">
          <div>
            <h1>NeXora — Portefeuille</h1>
            <p>Consultation et analyse uniquement. Aucun passage d'ordre, aucune recommandation personnalisée.</p>
          </div>
          <button type="button" className="link-button" onClick={handleLogout}>
            Se déconnecter
          </button>
        </div>
      </header>

      <div role="tablist" aria-label="Navigation principale">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            role="tab"
            aria-selected={activeTab === tab.id}
            aria-controls={`panel-${tab.id}`}
            id={`tab-${tab.id}`}
            onClick={() => setActiveTab(tab.id)}
          >
            {tab.label}
          </button>
        ))}
      </div>

      <div role="tabpanel" id={`panel-${activeTab}`} aria-labelledby={`tab-${activeTab}`}>
        {activeTab === "portfolios" && <PortfoliosPage />}
        {activeTab === "instruments" && <InstrumentsPage />}
        {activeTab === "settings" && <SettingsPage user={user} onAccountDeleted={handleAccountDeleted} />}
      </div>
    </>
  );
}
