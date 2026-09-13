import { useEffect, useState } from "react";
import { getConfig, localLogin, logout as apiLogout, me } from "./api/client";
import { setCsrfToken } from "./authStore";
import { appConfig, setAppConfig } from "./configStore";
import { AdminPage } from "./pages/AdminPage";
import { AlertsPage } from "./pages/AlertsPage";
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
import { HeaderSearch } from "./components/HeaderSearch";
import { NotificationsBell } from "./components/NotificationsBell";
import { href, useRoute } from "./router";
import type { AuthResponse, User } from "./types";

const NAV: { id: string; label: string; needsPortfolios?: boolean }[] = [
  { id: "dashboard", label: "Accueil" },
  { id: "markets", label: "Marchés" },
  { id: "portfolios", label: "Portefeuilles", needsPortfolios: true },
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
    (async () => {
      try {
        setAppConfig(await getConfig());
      } catch {
        // keep the conservative defaults
      }
      try {
        const auth = await me();
        setCsrfToken(auth.csrf_token);
        setUser(auth.user);
      } catch {
        // No valid session: in single-user mode open the local one, else
        // stay on the account screen.
        if (appConfig().single_user) {
          try {
            const auth = await localLogin();
            setCsrfToken(auth.csrf_token);
            setUser(auth.user);
          } catch {
            // the auth screen stays as the fallback
          }
        }
      } finally {
        setCheckingSession(false);
      }
    })();
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
      page = appConfig().portfolios_enabled ? <PortfoliosPage selectedId={arg} initialTab={route.query.tab} /> : <p className="empty-state">La gestion de portefeuille est désactivée (NEXORA_PORTFOLIOS_ENABLED).</p>;
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
    case "alerts":
      page = <AlertsPage />;
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
            {NAV.filter((item) => !item.needsPortfolios || appConfig().portfolios_enabled).map((item) => (
              <a key={item.id} href={href(item.id)} aria-current={section === item.id ? "page" : undefined}>
                {item.label}
              </a>
            ))}
          </nav>
          <div className="header-user">
            <HeaderSearch />
            <NotificationsBell />
            {!appConfig().single_user && (
              <>
                <span className="muted">{user.display_name || user.email}</span>
                <button type="button" className="link-button" onClick={handleLogout}>
                  Se déconnecter
                </button>
              </>
            )}
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
