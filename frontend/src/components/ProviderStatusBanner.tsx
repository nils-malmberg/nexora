import { useEffect, useState } from "react";
import { getProvidersStatus } from "../api/client";
import type { ProvidersOverview } from "../types";

/** Degraded-mode banner: which market/news sources are paused or down. The
 * data already known stays displayed; the banner just says why it may be
 * stale (specs/NEWS_AND_EVENTS.md, specs/ARCHITECTURE.md "dégradation lisible"). */
export function ProviderStatusBanner() {
  const [overview, setOverview] = useState<ProvidersOverview | null>(null);

  useEffect(() => {
    let cancelled = false;
    getProvidersStatus()
      .then((o) => {
        if (!cancelled) setOverview(o);
      })
      .catch(() => {
        // a failing status check must never block the page
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (!overview) return null;
  const degradedMarket = overview.market.filter((m) => !m.healthy);
  const degradedNews = overview.news.filter((n) => !n.healthy || !n.enabled);
  if (degradedMarket.length === 0 && degradedNews.length === 0) return null;

  return (
    <div className="provider-banner" role="status">
      Mode dégradé :{" "}
      {degradedMarket.length > 0 && (
        <>
          données de marché « {degradedMarket.map((m) => `${m.name} (${m.role})`).join(", ")} » indisponibles ou en pause
          {degradedNews.length > 0 ? " ; " : ". "}
        </>
      )}
      {degradedNews.length > 0 && <>sources d'actualités indisponibles : {degradedNews.map((n) => n.name).join(", ")}. </>}
      Les dernières données connues restent affichées avec leur âge.
    </div>
  );
}
