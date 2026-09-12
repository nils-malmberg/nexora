export interface Asset {
  id: string;
  symbol: string;
  name: string;
  isin: string | null;
  market: string | null;
  currency: string | null;
}

export interface RelatedItemRef {
  news_item_id: string;
  title: string;
  provenance: string;
}

export type NewsKind = "fact" | "synthesis" | "prediction";

export interface NewsItem {
  id: string;
  asset_ids: string[];
  provider_id: string;
  provider_name: string;
  kind: NewsKind;
  category: string;
  title: string;
  excerpt: string | null;
  summary: string | null;
  url: string;
  citation: string | null;
  provenance: string;
  publication_at: string;
  event_at: string | null;
  timezone: string;
  confidence: number;
  relevance_score: number;
  relevance_breakdown: Record<string, unknown>;
  language: string | null;
  collected_at: string;
  updated_at: string;
  freshness_at_collection: string;
  stale: boolean;
  verification_status: string;
  duplicate_of: RelatedItemRef[];
  corroborated_by: RelatedItemRef[];
}

export interface Page<T> {
  items: T[];
  next_cursor: string | null;
}

export interface EventSource {
  url: string;
  citation: string | null;
  retrieved_at: string;
  is_primary: boolean;
}

export interface EventStatusHistoryEntry {
  old_status: string | null;
  new_status: string;
  changed_at: string;
  source_url: string | null;
}

export type EventStatus = "confirme" | "previsionnel" | "reporte" | "annule" | "unknown";

export interface CalendarEvent {
  id: string;
  asset_id: string;
  type: string;
  starts_at: string | null;
  period_label: string | null;
  timezone: string;
  status: EventStatus;
  amount: number | null;
  currency: string | null;
  last_verified_at: string;
  stale: boolean;
  sources: EventSource[];
  status_history: EventStatusHistoryEntry[];
}

export interface TimelineEntry {
  entry_type: "news" | "event";
  effective_at: string | null;
  date_basis: "event_date" | "publication_date" | "period" | "unknown";
  bucket: string;
  news_item: NewsItem | null;
  event: CalendarEvent | null;
}

export interface ProviderStatus {
  id: string;
  name: string;
  type: string;
  enabled: boolean;
  circuit_state: "closed" | "open" | "half_open";
  consecutive_failures: number;
  last_attempt_at: string | null;
  last_success_at: string | null;
  healthy: boolean;
  license_note: string | null;
}

export const CATEGORIES = [
  "resultats",
  "dividende",
  "reglementation",
  "operation_titre",
  "gouvernance",
  "marche",
  "macro",
  "autre",
] as const;

export const CATEGORY_LABELS: Record<string, string> = {
  resultats: "Résultats",
  dividende: "Dividende",
  reglementation: "Réglementation",
  operation_titre: "Opération sur titre",
  gouvernance: "Gouvernance",
  marche: "Marché",
  macro: "Macro",
  autre: "Autre",
};
