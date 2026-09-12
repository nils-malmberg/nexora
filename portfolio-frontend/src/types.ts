export interface User {
  id: string;
  email: string;
  display_name: string | null;
  reference_currency: string;
  created_at: string;
}

export interface AuthResponse {
  user: User;
  csrf_token: string;
}

export interface Portfolio {
  id: string;
  name: string;
  base_currency: string;
  created_at: string;
  updated_at: string;
}

export const ASSET_CLASSES = ["action", "etf", "crypto", "obligation", "actif_prive"] as const;
export type AssetClass = (typeof ASSET_CLASSES)[number];

export const ASSET_CLASS_LABELS: Record<AssetClass, string> = {
  action: "Action",
  etf: "ETF",
  crypto: "Crypto-actif",
  obligation: "Obligation",
  actif_prive: "Actif privé",
};

export interface Instrument {
  id: string;
  symbol: string;
  name: string;
  asset_class: AssetClass;
  isin: string | null;
  currency: string;
  created_at: string;
}

export interface PricePoint {
  id: string;
  instrument_id: string;
  as_of: string;
  price: string;
  currency: string;
  source: string;
  is_estimate: boolean;
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

export const TRANSACTION_TYPES = ["achat", "vente", "dividende", "coupon", "depot", "retrait", "split"] as const;
export type TransactionType = (typeof TRANSACTION_TYPES)[number];

export const TRANSACTION_TYPE_LABELS: Record<TransactionType, string> = {
  achat: "Achat",
  vente: "Vente",
  dividende: "Dividende",
  coupon: "Coupon",
  depot: "Dépôt",
  retrait: "Retrait",
  split: "Split",
};

export const CASH_ONLY_TRANSACTION_TYPES: TransactionType[] = ["depot", "retrait"];

export interface Transaction {
  id: string;
  portfolio_id: string;
  instrument_id: string | null;
  type: TransactionType;
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

export type Freshness = "a_jour" | "differe" | "estime" | "manquant";

export const FRESHNESS_LABELS: Record<Freshness, string> = {
  a_jour: "À jour",
  differe: "Différé",
  estime: "Estimé",
  manquant: "Manquant",
};

export interface Position {
  instrument_id: string;
  symbol: string;
  name: string;
  quantity: string;
  average_unit_cost: string;
  currency: string;
  price: string | null;
  price_as_of: string | null;
  market_value: string | null;
  freshness: Freshness;
  matches_base_currency: boolean;
}

export interface Valuation {
  base_currency: string;
  cash: string;
  cash_by_currency: Record<string, string>;
  positions_value: string;
  total_value: string;
  unconverted_currencies: string[];
  has_missing_prices: boolean;
  positions: Position[];
}

export interface Page<T> {
  items: T[];
  next_cursor: string | null;
}

export interface ProviderStatus {
  name: string;
  healthy: boolean;
  detail: string;
}

export interface ExportData {
  user: User;
  portfolios: Portfolio[];
  instruments: Instrument[];
  transactions: Transaction[];
  price_points: PricePoint[];
  private_valuations: PrivateValuation[];
}
