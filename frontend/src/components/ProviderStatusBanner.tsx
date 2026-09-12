import { useEffect, useState } from "react";
import { getProvidersStatus } from "../api/client";
import type { ProviderStatus } from "../types";

export function ProviderStatusBanner() {
  const [degraded, setDegraded] = useState<ProviderStatus[]>([]);

  useEffect(() => {
    let cancelled = false;
    getProvidersStatus()
      .then((statuses) => {
        if (!cancelled) setDegraded(statuses.filter((s) => !s.healthy || !s.enabled));
      })
      .catch(() => {
        // Silently ignore: a failing status check should not block the page.
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (degraded.length === 0) return null;

  return (
    <div className="provider-banner" role="status">
      Mode dégradé : {degraded.length} fournisseur(s) indisponible(s) ou désactivé(s) (
      {degraded.map((p) => p.name).join(", ")}). Les données déjà connues restent affichées.
    </div>
  );
}
