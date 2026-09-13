import { useEffect, useState } from "react";
import { logout as apiLogout, me } from "./api/client";
import { setCsrfToken } from "./authStore";
import { AdminPage } from "./pages/AdminPage";
import { AnalysisPage } from "./pages/AnalysisPage";
import { AuthPage } from "./pages/AuthPage";
import { DashboardPage } from "./pages/DashboardPage";
import { HelpPage } from "./pages/HelpPage";
import { InstrumentPage } from "./pages/InstrumentPage";
import { InstrumentsPage } from "./pages/InstrumentsPage";
import { MarketsPage } from "./pages/MarketsPage";
import { NewsHubPage } from "./pages/NewsHubPage";
import { PortfoliosPage } from "./pages/PortfoliosPage";
import { PredictionPage } from "./pages/PredictionPage";
import { SettingsPage } from "./pages/SettingsPage";
import { href, useRoute } from "./router";
import type { AuthResponse, User } from "./types";

const NAV: { id: string; label: string }[] = [
  { id: "dashboard", label: "Tableau de bord" },
  { id: "markets", label: "Marchés" },
  { id: "portfolios", label: "Portefeuilles" },
  { id: "analysis", label: "Analyse" },
  { id: "news", label: "Actualités" },
  { id: "prediction", label: "Prédiction" },
  { id: "help", label: "Aide" },
  { id: "settings", label: "Paramètres" },
];

export function App() {
  const [user, setUser] = useState<User | null>(null);
  const [checkingSession, setCheckingSession] = useState(true);
  const route = useRoute();

  useEffect(() => {
    me()
      .then((auth) => {
        setCsrfToken(auth.csrf_token);
        setUser(auth.user);
      })
      .catch(() => {
        // No valid session: stay on the auth screen.
      })
      .finally(() => setCheckingSession(false));
  }, []);

  function handleAuthenticated(auth: AuthResponse) {
    setCsrfToken(auth.csrf_token);
    setUser(auth.user);
  }

  async function handleLogout() {
    try {
      await apiLogout();
    } finally {
      setCsrfToken(null);
      setUser(null);
    }
  }

  if (checkingSession) return <p className="loading-state">Chargement…</p>;
  if (!user) return <AuthPage onAuthenticated={handleAuthenticated} />;

  const section = route.path[0] || "dashboard";
  const arg = route.path[1];

  let page: JSX.Element;
  switch (section) {
    case "markets":
      page = arg ? <InstrumentPage key={arg} instrumentId={arg} initialTab={route.query.tab} /> : <MarketsPage />;
      break;
    case "portfolios":
      page = <PortfoliosPage selectedId={arg} />;
      break;
    case "instruments":
      page = <InstrumentsPage />;
      break;
    case "analysis":
      page = <AnalysisPage initialPortfolioId={route.query.portfolio} initialInstrumentId={route.query.instrument} />;
      break;
    case "news":
      page = <NewsHubPage initialInstrumentId={route.query.instrument} />;
      break;
    case "prediction":
      page = <PredictionPage initialInstrumentId={route.query.instrument} />;
      break;
    case "help":
      page = <HelpPage slug={arg} />;
      break;
    case "settings":
      page = <SettingsPage user={user} onAccountDeleted={() => setUser(null)} onUserUpdated={setUser} />;
      break;
    case "admin":
      page = user.is_admin ? <AdminPage /> : <p className="error-state">Réservé aux administrateurs.</p>;
      break;
    default:
      page = <DashboardPage user={user} />;
  }

  return (
    <div className="app-shell">
      <header className="app-header">
        <div className="app-header-row">
          <a href={href("dashboard")} className="brand">
            <span className="brand-mark">N</span> NeXora
          </a>
          <nav aria-label="Navigation principale">
            {NAV.map((item) => (
              <a key={item.id} href={href(item.id)} aria-current={section === item.id ? "page" : undefined}>
                {item.label}
              </a>
            ))}
          </nav>
          <div className="header-user">
            <span className="muted">{user.display_name || user.email}</span>
            <button type="button" className="link-button" onClick={handleLogout}>
              Se déconnecter
            </button>
          </div>
        </div>
      </header>
      <main id="main">{page}</main>
      <footer className="app-footer">
        Consultation et analyse uniquement : aucun ordre n'est passé, aucune recommandation personnalisée n'est donnée. Les cotations peuvent être différées, incomplètes ou indisponibles et sont toujours affichées avec leur source et leur âge. <a href={href("help")}>Aide</a>
      </footer>
    </div>
  );
}
