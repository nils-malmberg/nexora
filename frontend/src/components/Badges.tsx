import type { Freshness, NewsKind, QuoteStatus } from "../types";
import { FRESHNESS_LABELS } from "../types";

const KIND_LABELS: Record<NewsKind, string> = {
  fact: "Fait",
  synthesis: "Synthèse",
  prediction: "Estimation",
};

export function KindBadge({ kind }: { kind: NewsKind }) {
  return <span className={`badge kind-${kind}`}>{KIND_LABELS[kind]}</span>;
}

export function StaleBadge({ stale }: { stale: boolean }) {
  if (!stale) return null;
  return <span className="badge stale">Données non fraîches</span>;
}

export function ConfidenceBadge({ confidence }: { confidence: number }) {
  return <span className="badge confidence">Confiance {Math.round(confidence * 100)}%</span>;
}

export function CollectionFreshnessBadge({ freshness }: { freshness: string }) {
  const labels: Record<string, string> = {
    realtime: "Temps réel",
    delayed: "Différé",
    estimated: "Estimé",
    unknown: "Fraîcheur inconnue",
  };
  return <span className="badge">{labels[freshness] ?? freshness}</span>;
}

/** Price freshness (à jour / différé / estimé / manquant) - always text, never
 * colour alone. */
export function FreshnessBadge({ freshness }: { freshness: Freshness }) {
  return <span className={`badge freshness-${freshness}`}>{FRESHNESS_LABELS[freshness]}</span>;
}

const QUOTE_STATUS_LABELS: Record<QuoteStatus, string> = {
  fresh: "Rafraîchi",
  cached: "En cache",
  stale: "Périmé",
  unavailable: "Indisponible",
};

const REASON_LABELS: Record<string, string> = {
  rate_limited: "quota atteint",
  circuit_open: "fournisseur en pause",
  unavailable: "fournisseur injoignable",
  not_found: "symbole inconnu",
  not_supported: "non pris en charge",
  misconfigured: "clé manquante",
  no_live_source: "saisie manuelle",
  no_data: "aucune donnée",
};

export function QuoteStatusBadge({ status, reason }: { status: QuoteStatus; reason: string | null }) {
  const label = QUOTE_STATUS_LABELS[status];
  const detail = reason ? REASON_LABELS[reason] ?? reason : null;
  return (
    <span className={`badge quote-${status}`} title={detail ?? undefined}>
      {label}
      {detail ? ` · ${detail}` : ""}
    </span>
  );
}

export function AssetClassBadge({ assetClass, label }: { assetClass: string; label: string }) {
  return <span className={`badge class-${assetClass}`}>{label}</span>;
}
