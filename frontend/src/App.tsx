import { useEffect, useState } from "react";
import { ApiError, listAssets } from "./api/client";
import { AssetPicker } from "./components/AssetPicker";
import { ProviderStatusBanner } from "./components/ProviderStatusBanner";
import { NewsPage } from "./pages/NewsPage";
import { TimelinePage } from "./pages/TimelinePage";
import { EventsPage } from "./pages/EventsPage";
import type { Asset } from "./types";

type Tab = "news" | "timeline" | "events";

const TABS: { id: Tab; label: string }[] = [
  { id: "news", label: "Actualités récentes" },
  { id: "timeline", label: "Chronologie" },
  { id: "events", label: "Événements à venir" },
];

export function App() {
  const [assets, setAssets] = useState<Asset[]>([]);
  const [selectedAssetId, setSelectedAssetId] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<Tab>("news");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listAssets()
      .then((list) => {
        setAssets(list);
        if (list.length > 0) setSelectedAssetId(list[0].id);
      })
      .catch((err: unknown) => setError(err instanceof ApiError ? err.message : "Impossible de charger les actifs"));
  }, []);

  return (
    <>
      <header className="app-header">
        <h1>Actualités et événements</h1>
        <p>Faits, synthèses et estimations sourcés — outil d'information, pas un conseil financier.</p>
      </header>

      <p className="disclaimer">
        Les informations affichées proviennent de sources tierces (flux RSS/Atom, API et calendriers officiels
        configurés). Elles peuvent être incomplètes ou différées ; consultez toujours la source d'origine avant
        toute décision.
      </p>

      <ProviderStatusBanner />

      {error && <p className="error-state">{error}</p>}

      <AssetPicker assets={assets} selectedAssetId={selectedAssetId} onSelect={setSelectedAssetId} />

      {selectedAssetId && (
        <>
          <div role="tablist" aria-label="Vues du module actualités">
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
            {activeTab === "news" && <NewsPage assetId={selectedAssetId} />}
            {activeTab === "timeline" && <TimelinePage assetId={selectedAssetId} />}
            {activeTab === "events" && <EventsPage assetId={selectedAssetId} />}
          </div>
        </>
      )}

      {!selectedAssetId && assets.length === 0 && !error && (
        <p className="empty-state">Aucun actif configuré pour le moment.</p>
      )}
    </>
  );
}
