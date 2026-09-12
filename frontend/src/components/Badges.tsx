import type { NewsKind } from "../types";

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
  const pct = Math.round(confidence * 100);
  return <span className="badge confidence">Confiance {pct}%</span>;
}

export function FreshnessBadge({ freshness }: { freshness: string }) {
  const labels: Record<string, string> = {
    realtime: "Temps réel",
    delayed: "Différé",
    estimated: "Estimé",
    unknown: "Fraîcheur inconnue",
  };
  return <span className="badge">{labels[freshness] ?? freshness}</span>;
}
