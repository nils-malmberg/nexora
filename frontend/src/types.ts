// ---------------------------------------------------------------------------
// Identity
// ---------------------------------------------------------------------------

export interface User {
  id: string;
  email: string;
  display_name: string | null;
  reference_currency: string;
  display_timezone: string;
  is_admin: boolean;
  created_at: string;
}

export interface AuthResponse {
  user: User;
  csrf_token: string;
}

export interface Page<T> {
  items: T[];
  next_cursor: string | null;
}

// ---------------------------------------------------------------------------
// Instruments & market
// ---------------------------------------------------------------------------

export const ASSET_CLASSES = ["action", "etf", "crypto", "obligation", "actif_prive", "indice", "devise"] as const;
export type AssetClass = (typeof ASSET_CLASSES)[number];

export const ASSET_CLASS_LABELS: Record<AssetClass, string> = {
  action: "Action",
  etf: "ETF",
  crypto: "Crypto-actif",
  obligation: "Obligation",
  actif_prive: "Actif privé",
  indice: "Indice",
  devise: "Devise",
};

export interface Instrument {
  id: string;
  symbol: string;
  name: string;
  asset_class: AssetClass;
  isin: string | null;
  exchange: string | null;
  currency: string;
  provider: string | null;
  provider_symbol: string | null;
  is_shared: boolean;
  created_at: string;
}

export interface Candidate {
  symbol: string;
  name: string;
  asset_class: AssetClass;
  currency: string | null;
  exchange: string | null;
  provider: string;
  provider_symbol: string;
  instrument_id: string | null;
  in_catalog: boolean;
}

export interface SearchResult {
  query: string;
  candidates: Candidate[];
  providers_queried: string[];
  provider_errors: Record<string, string>;
}

export type QuoteStatus = "fresh" | "cached" | "stale" | "unavailable";
export type Freshness = "a_jour" | "differe" | "estime" | "manquant";

export const FRESHNESS_LABELS: Record<Freshness, string> = {
  a_jour: "À jour",
  differe: "Différé",
  estime: "Estimé",
  manquant: "Manquant",
};

export interface Quote {
  instrument_id: string;
  price: string | null;
  currency: string | null;
  as_of: string | null;
  collected_at: string | null;
  source: string | null;
  is_delayed: boolean;
  is_estimate: boolean;
  status: QuoteStatus;
  reason: string | null;
  freshness: Freshness;
  age_seconds: number | null;
  previous_close: string | null;
  change_pct: string | null;
  provider: string | null;
  license_note: string | null;
  attribution: string | null;
}

export interface Bar {
  as_of: string;
  open: string | null;
  high: string | null;
  low: string | null;
  close: string;
  volume: string | null;
}

export interface MarketHistory {
  instrument_id: string;
  interval: string;
  currency: string | null;
  start: string;
  end: string;
  bars: Bar[];
  has_ohlc: boolean;
  source: string | null;
  status: QuoteStatus;
  reason: string | null;
  license_note: string | null;
  attribution: string | null;
}

export const HISTORY_RANGES = ["1w", "1m", "3m", "6m", "1y", "2y", "5y", "max"] as const;
export type HistoryRange = (typeof HISTORY_RANGES)[number];
export const HISTORY_RANGE_LABELS: Record<HistoryRange, string> = {
  "1w": "1S",
  "1m": "1M",
  "3m": "3M",
  "6m": "6M",
  "1y": "1A",
  "2y": "2A",
  "5y": "5A",
  max: "Max",
};

export interface WatchlistItem {
  id: string;
  held: boolean;
  entry_price: string | null;
  entry_date: string | null;
  quantity: string | null;
  note: string | null;
  instrument: Instrument;
  quote: Quote | null;
  created_at: string;
}

export interface OverviewEntry {
  instrument: Instrument;
  quote: Quote | null;
  held_quantity: string | null;
  watched: boolean;
}

export interface PricePoint {
  id: string;
  instrument_id: string;
  as_of: string;
  price: string;
  currency: string;
  source: string;
  is_estimate: boolean;
  is_delayed: boolean;
  collected_at: string;
}

export interface PrivateValuation {
  id: string;
  instrument_id: string;
  valuation_date: string;
  valuation_amount: string;
  currency: string;
  method: string;
  confidence: string;
  note: string | null;
  created_at: string;
}

// ---------------------------------------------------------------------------
// Portfolio
// ---------------------------------------------------------------------------

export interface Portfolio {
  id: string;
  name: string;
  base_currency: string;
  target_allocation: Record<string, number> | null;
  created_at: string;
  updated_at: string;
}

export const TRANSACTION_TYPES = ["achat", "vente", "dividende", "coupon", "interet", "frais", "depot", "retrait", "split"] as const;
export type TransactionType = (typeof TRANSACTION_TYPES)[number];

export const TRANSACTION_TYPE_LABELS: Record<TransactionType, string> = {
  achat: "Achat",
  vente: "Vente",
  dividende: "Dividende",
  coupon: "Coupon",
  interet: "Intérêts",
  frais: "Frais",
  depot: "Dépôt",
  retrait: "Retrait",
  split: "Split",
};

/** No instrument, quantity fixed to 1, unit_price carries the amount. */
export const CASH_ONLY_TRANSACTION_TYPES: TransactionType[] = ["interet", "frais", "depot", "retrait"];

export interface Transaction {
  id: string;
  portfolio_id: string;
  instrument_id: string | null;
  type: TransactionType | "transfert" | "valorisation_privee";
  trade_date: string;
  quantity: string;
  unit_price: string;
  currency: string;
  fees: string;
  account: string | null;
  external_id: string | null;
  note: string | null;
  reversed_at: string | null;
  reversal_reason: string | null;
  created_at: string;
}

export interface Position {
  instrument_id: string;
  symbol: string;
  name: string;
  asset_class: AssetClass;
  quantity: string;
  average_unit_cost: string;
  cost_currency: string;
  cost_basis: string;
  currency: string;
  price: string | null;
  price_as_of: string | null;
  price_source: string | null;
  market_value: string | null;
  market_value_base: string | null;
  unrealized_pnl: string | null;
  freshness: Freshness;
  matches_base_currency: boolean;
  fx_rate: string | null;
  fx_rate_as_of: string | null;
  fx_source: string | null;
}

export interface FxNote {
  currency: string;
  rate: string;
  rate_as_of: string;
  source: string;
}

export interface Valuation {
  base_currency: string;
  cash: string;
  cash_by_currency: Record<string, string>;
  positions_value: string;
  total_value: string;
  unconverted_currencies: string[];
  has_missing_prices: boolean;
  fx_rates: FxNote[];
  as_of: string;
  positions: Position[];
}

export type RowStatus = "valid" | "duplicate" | "error" | "inserted";

export interface RowResult {
  row_number: number;
  status: RowStatus;
  messages: string[];
  canonical: Record<string, string | null> | null;
}

export type ImportJobStatus = "draft" | "previewed" | "committed";

export interface ImportJobSummary {
  id: string;
  filename: string;
  status: ImportJobStatus;
  total_rows: number;
  valid_count: number;
  duplicate_count: number;
  error_count: number;
  inserted_count: number;
  created_at: string;
  previewed_at: string | null;
  committed_at: string | null;
}

export interface ImportJob extends ImportJobSummary {
  preset: string | null;
  preset_label: string | null;
  delimiter: string;
  encoding: string;
  column_mapping: Record<string, string>;
  suggested_mapping: Record<string, string> | null;
  headers: string[] | null;
  sample_rows: Record<string, string>[] | null;
  rows: RowResult[] | null;
  resolved_isins: Record<string, string> | null;
}

export interface ImportPreset {
  key: string;
  label: string;
  instructions: string[];
  notes: string[];
}

export const CANONICAL_IMPORT_FIELDS = [
  "date",
  "type",
  "symbol",
  "isin",
  "asset_class",
  "quantity",
  "unit_price",
  "currency",
  "fees",
  "account",
  "external_id",
  "note",
] as const;

// ---------------------------------------------------------------------------
// Analytics
// ---------------------------------------------------------------------------

export interface ValuationPoint {
  as_of: string;
  cash: string;
  positions_value: string;
  total_value: string;
  has_missing_prices: boolean;
}

export interface History {
  base_currency: string;
  points: ValuationPoint[];
}

export interface AllocationSlice {
  label: string;
  value: string;
  share: string;
}

export interface Allocation {
  base_currency: string;
  total_value: string;
  by_asset_class: AllocationSlice[];
  by_instrument: AllocationSlice[];
  by_currency: AllocationSlice[];
  unconverted_currencies: string[];
}

export interface Risk {
  has_sufficient_data: boolean;
  volatility_annualized: string | null;
  max_drawdown: string | null;
  observations: number;
  method: string;
}

export interface Performance {
  has_sufficient_data: boolean;
  start: string;
  end: string;
  base_currency: string;
  twr: string | null;
  mwr: string | null;
  external_flow_count: number;
  method: string;
}

export interface Indicators {
  dates: string[];
  prices: string[];
  sma: (string | null)[];
  ema: (string | null)[];
  rsi: (string | null)[];
  macd: (string | null)[];
  macd_signal: (string | null)[];
  sma_window: number;
  ema_window: number;
  rsi_window: number;
  macd_fast: number;
  macd_slow: number;
  macd_signal_window: number;
  bollinger_upper: (string | null)[];
  bollinger_middle: (string | null)[];
  bollinger_lower: (string | null)[];
  bollinger_window: number;
  bollinger_k: number;
  atr: (string | null)[];
  atr_window: number;
  stochastic_k: (string | null)[];
  stochastic_d: (string | null)[];
  stochastic_window: number;
  obv: (string | null)[];
  has_ohlc: boolean;
}

export interface ReturnStats {
  subject: string;
  label: string;
  currency: string | null;
  start: string | null;
  end: string | null;
  has_sufficient_data: boolean;
  observations: number;
  periods_per_year: number;
  risk_free_rate: number;
  mean_return_annualized: number | null;
  volatility_annualized: number | null;
  downside_deviation_annualized: number | null;
  sharpe: number | null;
  sortino: number | null;
  calmar: number | null;
  max_drawdown: number | null;
  skewness: number | null;
  kurtosis_excess: number | null;
  best_period: number | null;
  worst_period: number | null;
  positive_period_share: number | null;
  total_return: number | null;
  cagr: number | null;
  method: string;
}

export interface DrawdownPoint {
  as_of: string;
  value: number;
  drawdown: number;
}

export interface Drawdown {
  subject: string;
  points: DrawdownPoint[];
  max_drawdown: number | null;
  observations: number;
}

export interface VarResult {
  subject: string;
  has_sufficient_data: boolean;
  observations: number;
  confidence: number;
  horizon_periods: number;
  historical_var: number | null;
  historical_cvar: number | null;
  gaussian_var: number | null;
  cornish_fisher_var: number | null;
  current_value: number | null;
  currency: string | null;
  method: string;
}

export interface CapmResult {
  subject: string;
  benchmark: string;
  has_sufficient_data: boolean;
  observations: number;
  beta: number | null;
  alpha_annualized: number | null;
  correlation: number | null;
  r_squared: number | null;
  tracking_error_annualized: number | null;
  information_ratio: number | null;
  risk_free_rate: number;
  method: string;
}

export interface CorrelationResult {
  labels: string[];
  matrix: (number | null)[][];
  observations: number;
  has_sufficient_data: boolean;
  method: string;
}

export interface FrontierPoint {
  expected_return: number;
  volatility: number;
  weights: number[];
  sharpe: number | null;
}

export interface FrontierResult {
  has_sufficient_data: boolean;
  labels: string[];
  observations: number;
  periods_per_year: number;
  risk_free_rate: number;
  expected_returns: number[];
  volatilities: number[];
  frontier: FrontierPoint[];
  min_variance: FrontierPoint | null;
  max_sharpe: FrontierPoint | null;
  equal_weight: FrontierPoint | null;
  current: FrontierPoint | null;
  method: string;
  disclaimer: string;
}

export interface MonteCarloResult {
  subject: string;
  has_sufficient_data: boolean;
  observations: number;
  horizon_periods: number;
  simulations: number;
  seed: number;
  start_value: number | null;
  currency: string | null;
  drift_annualized: number | null;
  volatility_annualized: number | null;
  percentiles: Record<string, number[]>;
  terminal_percentiles: Record<string, number>;
  probability_of_loss: number | null;
  method: string;
  disclaimer: string;
}

// ---------------------------------------------------------------------------
// News & events
// ---------------------------------------------------------------------------

export interface RelatedItemRef {
  news_item_id: string;
  title: string;
  provenance: string;
}

export type NewsKind = "fact" | "synthesis" | "prediction";

export interface NewsItem {
  id: string;
  instrument_ids: string[];
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
  instrument_id: string;
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

// ---------------------------------------------------------------------------
// Providers
// ---------------------------------------------------------------------------

export interface NewsProviderStatus {
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

export interface MarketProviderPublic {
  name: string;
  role: "equity" | "crypto" | "fx";
  enabled: boolean;
  healthy: boolean;
  circuit_state: string;
  last_success_at: string | null;
  attribution: string | null;
  license_note: string | null;
  capabilities: Record<string, unknown>;
}

export interface AutoNewsStatus {
  provider: string;
  configured: boolean;
  env_var: string;
  detail: string;
}

export interface ProvidersOverview {
  market: MarketProviderPublic[];
  news: NewsProviderStatus[];
  auto_news: AutoNewsStatus;
  fundamentals: FundamentalsSource;
  prediction_enabled: boolean;
  quote_freshness_minutes: number;
}

export interface NewsRefresh {
  status: "refreshed" | "cached" | "not_configured" | "not_eligible" | "rate_limited" | "provider_disabled" | "failed";
  detail: string | null;
  items_total: number;
  run_status: string | null;
  error_code: string | null;
  configured: boolean;
  last_collected_at: string | null;
}

export interface MarketProviderState {
  name: string;
  enabled: boolean;
  env_var: string | null;
  license_note: string | null;
  last_attempt_at: string | null;
  last_success_at: string | null;
  last_error: string | null;
  consecutive_failures: number;
  circuit_state: string;
  disabled_reason: string | null;
}

export interface IngestionRun {
  id: string;
  provider_id: string;
  started_at: string;
  ended_at: string | null;
  status: string;
  counts: Record<string, number>;
  error_code: string | null;
  latency_ms: number | null;
}

export interface AuditEntry {
  id: string;
  action: string;
  target_type: string | null;
  target_id: string | null;
  user_id: string | null;
  created_at: string;
  metadata: Record<string, unknown>;
}

// ---------------------------------------------------------------------------
// Education
// ---------------------------------------------------------------------------

export interface EducationSummary {
  slug: string;
  title: string;
  category: string;
  summary: string;
}

export interface EducationSection {
  heading: string;
  body: string;
}

export interface EducationArticle extends EducationSummary {
  what_it_measures: string;
  method: string;
  limitations: string;
  sections: EducationSection[];
  related: string[];
  version: string;
}

// ---------------------------------------------------------------------------
// Prediction (experimental)
// ---------------------------------------------------------------------------

export interface PredictionStatus {
  enabled: boolean;
  available_models: string[];
  min_observations: number;
  max_observations: number;
  disclaimer: string;
}

export interface ExperimentConfig {
  horizon: number;
  lags: number;
  windows: number[];
  models: string[];
  meta_model: "ridge_stacking" | "mean";
  n_folds: number;
  min_train: number;
  seed: number;
  interval_confidence: number;
}

export interface ExperimentSummary {
  id: string;
  instrument_id: string;
  instrument_symbol: string | null;
  name: string;
  status: "pending" | "running" | "completed" | "failed";
  code_version: string;
  n_observations: number;
  trained_at: string | null;
  created_at: string;
  error: string | null;
  horizon: number | null;
}

export interface ModelMetrics {
  mae: number;
  rmse: number;
  direction_accuracy: number;
  bias: number;
  interval_coverage?: number;
  rmse_vs_naive: number | null;
}

export interface Fold {
  index: number;
  train_start: string;
  train_end: string;
  test_start: string;
  test_end: string;
  n_train: number;
  n_test: number;
  metrics: Record<string, ModelMetrics>;
}

export interface Forecast {
  as_of: string;
  horizon: number;
  last_close: number;
  expected_log_return: number;
  interval_confidence: number;
  interval_log_return: [number, number];
  implied_price: number;
  implied_price_interval: [number, number];
  by_model: Record<string, number>;
  disclaimer: string;
}

export interface Experiment extends ExperimentSummary {
  config: Partial<ExperimentConfig>;
  dataset_hash: string | null;
  dataset_start: string | null;
  dataset_end: string | null;
  metrics: { models?: Record<string, ModelMetrics>; meta_weights?: Record<string, number>; feature_names?: string[] };
  folds: Fold[];
  predictions: Record<string, number | string>[];
  latest_forecast: Forecast | null;
  disclaimer: string;
}

export const MODEL_LABELS: Record<string, string> = {
  naive_last: "Naïf (aucun changement)",
  historical_mean: "Moyenne historique",
  ridge: "Régression ridge",
  random_forest: "Forêt aléatoire",
  gradient_boosting: "Gradient boosting",
  meta: "Métamodèle (stacking)",
};

// ---------------------------------------------------------------------------
// Export
// ---------------------------------------------------------------------------

export interface ExportData {
  user: User;
  portfolios: Portfolio[];
  instruments: Instrument[];
  transactions: Transaction[];
  price_points: PricePoint[];
  private_valuations: PrivateValuation[];
  watchlist_instrument_ids: string[];
  import_jobs: ImportJobSummary[];
  prediction_experiments: Record<string, unknown>[];
}

export interface SessionInfo {
  id: string;
  created_at: string;
  last_seen_at: string;
  user_agent: string | null;
  current: boolean;
}

// ---------------------------------------------------------------------------
// Consolidated wealth, realized gains, income
// ---------------------------------------------------------------------------

export interface ConsolidatedPortfolio {
  id: string;
  name: string;
  base_currency: string;
  total_value: string;
  total_value_reference: string | null;
  cash_reference: string | null;
  positions: number;
  has_missing_prices: boolean;
  unconverted_currencies: string[];
  fx_rate: string | null;
  fx_source: string | null;
}

export interface Consolidated {
  reference_currency: string;
  as_of: string;
  total_value: string;
  cash: string;
  positions_value: string;
  portfolios: ConsolidatedPortfolio[];
  by_portfolio: AllocationSlice[];
  by_asset_class: AllocationSlice[];
  by_instrument: AllocationSlice[];
  by_currency: AllocationSlice[];
  unconverted_currencies: string[];
  has_missing_prices: boolean;
}

export interface RealizedSale {
  transaction_id: string;
  instrument_id: string;
  symbol: string;
  name: string;
  trade_date: string;
  quantity: string;
  unit_price: string;
  currency: string;
  proceeds: string;
  cost_basis: string | null;
  realized_pnl: string | null;
  realized_pnl_base: string | null;
  holding_days: number | null;
  mixed_currency: boolean;
  fx_rate: string | null;
  fx_source: string | null;
}

export interface RealizedTotal {
  key: string;
  label: string;
  sales: number;
  realized_pnl_base: string;
  gains_base: string;
  losses_base: string;
}

export interface RealizedReport {
  base_currency: string;
  year: number | null;
  sales: RealizedSale[];
  by_year: RealizedTotal[];
  by_instrument: RealizedTotal[];
  total_realized_pnl_base: string;
  unconverted_currencies: string[];
  mixed_currency_sales: number;
  method: string;
}

export type IncomeRowType = "dividende" | "coupon" | "interet" | "frais" | "frais_transaction";

export const INCOME_TYPE_LABELS: Record<IncomeRowType, string> = {
  dividende: "Dividende",
  coupon: "Coupon",
  interet: "Intérêts",
  frais: "Frais",
  frais_transaction: "Frais de transaction",
};

export interface IncomeRow {
  transaction_id: string;
  trade_date: string;
  type: IncomeRowType;
  instrument_id: string | null;
  symbol: string | null;
  amount: string;
  currency: string;
  amount_base: string | null;
  note: string | null;
}

export interface IncomeTotal {
  key: string;
  label: string;
  income_base: string;
  fees_base: string;
  net_base: string;
  count: number;
}

export interface IncomeReport {
  base_currency: string;
  year: number | null;
  rows: IncomeRow[];
  by_year: IncomeTotal[];
  by_month: IncomeTotal[];
  by_instrument: IncomeTotal[];
  total_income_base: string;
  total_fees_base: string;
  unconverted_currencies: string[];
  method: string;
}

// ---------------------------------------------------------------------------
// Strategy study, comparison
// ---------------------------------------------------------------------------

export const STRATEGY_RULES = ["sma_cross", "price_above_sma", "rsi_reversion"] as const;
export type StrategyRule = (typeof STRATEGY_RULES)[number];
export const STRATEGY_RULE_LABELS: Record<StrategyRule, string> = {
  sma_cross: "Croisement de moyennes mobiles (SMA rapide > SMA lente)",
  price_above_sma: "Prix au-dessus de sa moyenne mobile",
  rsi_reversion: "Retour à la moyenne du RSI (entrée sous le seuil bas, sortie au-dessus du seuil haut)",
};

export interface StrategyTrade {
  entry_date: string;
  exit_date: string | null;
  entry_price: number;
  exit_price: number | null;
  return_pct: number | null;
  holding_days: number | null;
}

export interface StrategyStudy {
  instrument_id: string;
  symbol: string;
  currency: string;
  has_sufficient_data: boolean;
  observations: number;
  rule: StrategyRule;
  params: { fast: number; slow: number; rsi_period: number; rsi_low: number; rsi_high: number };
  fee_bps: number;
  dates: string[];
  strategy_equity: number[];
  benchmark_equity: number[];
  invested: number[];
  trades: StrategyTrade[];
  n_trades: number;
  exposure_share: number | null;
  win_rate: number | null;
  strategy_stats: ReturnStats | null;
  benchmark_stats: ReturnStats | null;
  method: string;
  disclaimer: string;
}

export interface CompareSeries {
  instrument: Instrument;
  values: number[];
  total_return: number | null;
}

export interface Comparison {
  dates: string[];
  base: number;
  series: CompareSeries[];
  observations: number;
  method: string;
}

// ---------------------------------------------------------------------------
// Informational alerts and notifications
// ---------------------------------------------------------------------------

export const ALERT_KINDS = ["price_above", "price_below", "move_pct"] as const;
export type AlertKind = (typeof ALERT_KINDS)[number];
export const ALERT_KIND_LABELS: Record<AlertKind, string> = {
  price_above: "Cours au-dessus de",
  price_below: "Cours en dessous de",
  move_pct: "Variation quotidienne d'au moins (±%)",
};

export interface PriceAlert {
  id: string;
  instrument: Instrument;
  kind: AlertKind;
  kind_label: string;
  threshold: string;
  note: string | null;
  active: boolean;
  created_at: string;
  triggered_at: string | null;
  last_evaluated_at: string | null;
  last_value: string | null;
}

export interface Notification {
  id: string;
  instrument_id: string | null;
  alert_id: string | null;
  kind: string;
  title: string;
  body: string;
  created_at: string;
  read_at: string | null;
}

export interface Notifications {
  items: Notification[];
  unread: number;
}

// ---------------------------------------------------------------------------
// Decision aid
// ---------------------------------------------------------------------------

export type Reading = "favorable" | "defavorable" | "neutre" | "indisponible";
export const READING_LABELS: Record<Reading, string> = {
  favorable: "Favorable",
  defavorable: "Défavorable",
  neutre: "Neutre",
  indisponible: "Indisponible",
};
export const READING_HINTS: Record<Reading, string> = {
  favorable: "lecture manuel : plutôt favorable à un achat ou à la conservation",
  defavorable: "lecture manuel : plutôt défavorable à un achat, favorable à une vente ou à l'abstention",
  neutre: "la méthode ne tranche pas",
  indisponible: "donnée manquante — jamais estimée",
};
export const FAMILY_LABELS: Record<string, string> = {
  tendance: "Tendance",
  momentum: "Momentum",
  volatilite: "Volatilité",
  valorisation: "Valorisation",
  qualite: "Qualité de l'entreprise",
  consensus: "Consensus",
  risque: "Risque",
  prediction: "Prédiction (expérimental)",
  diversification: "Diversification",
  allocation: "Allocation",
  positions: "Positions",
  donnees: "Données",
};
export const EVIDENCE_LABELS: Record<string, string> = { forte: "preuve forte", moyenne: "preuve moyenne", faible: "preuve faible" };

export interface Signal {
  key: string;
  family: string;
  horizon: "court_terme" | "long_terme" | "transversal";
  label: string;
  reading: Reading;
  detail: string;
  value: string | null;
  strength: "faible" | "moyen" | "fort";
  evidence: "forte" | "moyenne" | "faible";
  help_slug: string | null;
}

export interface Tally {
  favorable: number;
  defavorable: number;
  neutre: number;
  indisponible: number;
  available: number;
}

export interface HorizonSummary {
  horizon: "court_terme" | "long_terme" | "transversal";
  label: string;
  tally: Tally;
  text: string;
}

export interface FundamentalsStatus {
  status: "fresh" | "cached" | "stale" | "unavailable" | "not_supported" | "not_configured";
  reason: string | null;
  provider: string | null;
  as_of: string | null;
  source: string | null;
  license_note: string | null;
  env_var: string | null;
}

export interface DecisionAid {
  instrument: Instrument;
  as_of: string;
  observations: number;
  price_source: string | null;
  signals: Signal[];
  tally: Tally;
  horizons: HorizonSummary[];
  overall: string;
  verdicts: Verdict[];
  orientation: Orientation;
  orientation_label: string;
  orientation_confidence: "faible" | "moyenne" | "forte";
  orientation_text: string;
  levels: Levels | null;
  holder: HolderView | null;
  fundamentals: FundamentalsStatus;
  prediction_available: boolean;
  news_last_7_days: number;
  disclaimer: string;
}

export interface DecisionOverviewEntry {
  instrument: Instrument;
  held: boolean;
  watched: boolean;
  orientation: Orientation;
  orientation_label: string;
  orientation_confidence: "faible" | "moyenne" | "forte";
  observations: number;
  tally: Tally;
  trend: Reading;
  momentum: Reading;
  rsi: string | null;
  rsi_reading: Reading;
  valuation: Reading;
  overall: string;
}

export interface DecisionOverview {
  entries: DecisionOverviewEntry[];
  fundamentals_configured: boolean;
  disclaimer: string;
}

export interface AllocationShare {
  label: string;
  share: number;
  target: number | null;
  drift: number | null;
}

export interface PortfolioCheckup {
  portfolio_id: string;
  base_currency: string;
  as_of: string;
  total_value: string;
  signals: Signal[];
  tally: Tally;
  overall: string;
  allocation: AllocationShare[];
  has_targets: boolean;
  disclaimer: string;
}

export interface FundamentalsSource {
  provider: string;
  configured: boolean;
  env_var: string | null;
  detail: string;
}

// ---------------------------------------------------------------------------
// Product config, chart tools, buy/sell verdicts, past validation
// ---------------------------------------------------------------------------

export interface AppConfig {
  single_user: boolean;
  portfolios_enabled: boolean;
  prediction_enabled: boolean;
  environment: string;
}

export interface IchimokuData {
  tenkan: (number | null)[];
  kijun: (number | null)[];
  senkou_a: (number | null)[];
  senkou_b: (number | null)[];
  chikou: (number | null)[];
  future_dates: string[];
  future_senkou_a: (number | null)[];
  future_senkou_b: (number | null)[];
  reading: string;
}

export interface SarData {
  values: (number | null)[];
  trend: number[];
  reading: string;
}

export interface PivotSet {
  period: string;
  based_on: string;
  pivot: number;
  r1: number;
  r2: number;
  r3: number;
  s1: number;
  s2: number;
  s3: number;
}

export interface FibonacciData {
  swing_high: number;
  swing_high_date: string;
  swing_low: number;
  swing_low_date: string;
  direction: "hausse" | "baisse";
  levels: [number, number][];
  nearest_ratio: number | null;
  reading: string;
}

export interface CandlePattern {
  index: number;
  as_of: string;
  name: string;
  direction: "haussier" | "baissier" | "indecision";
  explanation: string;
}

export const PATTERN_LABELS: Record<string, string> = {
  doji: "Doji",
  marteau: "Marteau",
  etoile_filante: "Étoile filante",
  avalement_haussier: "Avalement haussier",
  avalement_baissier: "Avalement baissier",
  etoile_du_matin: "Étoile du matin",
  etoile_du_soir: "Étoile du soir",
};

export interface ChartTools {
  instrument_id: string;
  dates: string[];
  has_ohlc: boolean;
  ichimoku: IchimokuData | null;
  sar: SarData | null;
  pivots: PivotSet[];
  fibonacci: FibonacciData | null;
  supports: number[];
  resistances: number[];
  patterns: CandlePattern[];
  method: string;
}

export type Orientation = "achat" | "vente" | "attendre";
export const ORIENTATION_LABELS: Record<Orientation, string> = { achat: "Plutôt achat", vente: "Plutôt vente", attendre: "Attendre / observer" };

export interface Verdict {
  horizon: "court_terme" | "long_terme";
  label: string;
  orientation: Orientation;
  orientation_label: string;
  confidence: "faible" | "moyenne" | "forte";
  text: string;
  buy_case: string[];
  sell_case: string[];
  available: number;
}

export interface Levels {
  price: number;
  atr: number | null;
  stop_loss: number | null;
  stop_loss_pct: number | null;
  target: number | null;
  target_pct: number | null;
  risk_reward: number | null;
  trailing_stop: number | null;
  supports: number[];
  resistances: number[];
  high_52w: number | null;
  low_52w: number | null;
  position_size: number | null;
  capital: number;
  risk_pct: number;
  risk_amount: number;
  method: string;
}

export interface HolderView {
  held: boolean;
  entry_price: number | null;
  pnl_pct: number | null;
  orientation: Orientation;
  label: string;
  text: string;
  below_stop: boolean | null;
}

export interface OrientationStats {
  orientation: Orientation;
  label: string;
  count: number;
  mean_return: number | null;
  median_return: number | null;
  hit_rate: number | null;
  worst: number | null;
  best: number | null;
}

export interface PastValidation {
  instrument_id: string;
  symbol: string;
  horizon_days: number;
  evaluations: number;
  start: string | null;
  end: string | null;
  by_orientation: OrientationStats[];
  baseline_mean_return: number | null;
  baseline_hit_rate: number | null;
  timeline: { as_of: string; orientation: Orientation; close: number }[];
  text: string;
  method: string;
  disclaimer: string;
}
