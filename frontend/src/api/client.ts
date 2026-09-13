import { getCsrfToken } from "../authStore";
import type {
  Allocation,
  AuditEntry,
  AuthResponse,
  CalendarEvent,
  CapmResult,
  CorrelationResult,
  Drawdown,
  EducationArticle,
  EducationSummary,
  Experiment,
  ExperimentConfig,
  ExperimentSummary,
  ExportData,
  FrontierResult,
  History,
  ImportJob,
  ImportJobSummary,
  ImportPreset,
  Indicators,
  IngestionRun,
  Instrument,
  MarketHistory,
  MarketProviderState,
  MonteCarloResult,
  NewsItem,
  NewsProviderStatus,
  NewsRefresh,
  OverviewEntry,
  Page,
  Performance,
  Portfolio,
  Position,
  PredictionStatus,
  PricePoint,
  PrivateValuation,
  ProvidersOverview,
  Quote,
  ReturnStats,
  Risk,
  SearchResult,
  SessionInfo,
  TimelineEntry,
  Transaction,
  User,
  Valuation,
  VarResult,
  WatchlistItem,
} from "../types";

// Same-origin by default: nginx (docker) and the vite dev server both proxy
// /api to the backend, so the session cookie is first-party and no CORS is
// involved. VITE_API_BASE_URL only exists for unusual setups.
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? window.location.origin;

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public requestId?: string,
  ) {
    super(message);
  }
}

const MUTATING_METHODS = new Set(["POST", "PATCH", "DELETE"]);

type Params = Record<string, string | number | boolean | undefined>;

async function request<T>(path: string, options: { method?: string; body?: unknown; params?: Params } = {}): Promise<T> {
  const { method = "GET", body, params } = options;
  const url = new URL(path, API_BASE_URL);
  if (params) {
    for (const [key, value] of Object.entries(params)) {
      if (value !== undefined && value !== "") url.searchParams.set(key, String(value));
    }
  }
  const headers: Record<string, string> = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (MUTATING_METHODS.has(method)) {
    const csrfToken = getCsrfToken();
    if (csrfToken) headers["X-CSRF-Token"] = csrfToken;
  }
  const response = await fetch(url.toString(), {
    method,
    headers,
    credentials: "include", // the session lives in an HttpOnly cookie
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (response.status === 204) return undefined as T;
  if (!response.ok) {
    let message = `Erreur ${response.status}`;
    let requestId: string | undefined;
    try {
      const errorBody = await response.json();
      message = errorBody.message ?? message;
      requestId = errorBody.request_id;
      if (errorBody.details?.errors?.length) {
        const first = errorBody.details.errors[0];
        message = `${message} : ${first.msg ?? JSON.stringify(first)}`;
      }
    } catch {
      // keep default message
    }
    throw new ApiError(message, response.status, requestId);
  }
  return response.json() as Promise<T>;
}

export function errorMessage(err: unknown, fallback = "Erreur de chargement"): string {
  return err instanceof ApiError ? err.message : fallback;
}

// --- auth / me ----------------------------------------------------------------

export function register(email: string, password: string, referenceCurrency = "EUR"): Promise<AuthResponse> {
  return request("/api/v1/auth/register", { method: "POST", body: { email, password, reference_currency: referenceCurrency } });
}
export function login(email: string, password: string): Promise<AuthResponse> {
  return request("/api/v1/auth/login", { method: "POST", body: { email, password } });
}
export function logout(): Promise<void> {
  return request("/api/v1/auth/logout", { method: "POST" });
}
export function me(): Promise<AuthResponse> {
  return request("/api/v1/auth/me");
}
export function updateProfile(input: { display_name?: string; reference_currency?: string; display_timezone?: string }): Promise<User> {
  return request("/api/v1/me", { method: "PATCH", body: input });
}
export function listSessions(): Promise<SessionInfo[]> {
  return request("/api/v1/me/sessions");
}
export function revokeOtherSessions(): Promise<void> {
  return request("/api/v1/me/sessions/revoke-others", { method: "POST" });
}
export function exportMyData(): Promise<ExportData> {
  return request("/api/v1/me/export");
}
export function deleteMyAccount(password: string): Promise<void> {
  return request("/api/v1/me", { method: "DELETE", body: { password } });
}

// --- portfolios ---------------------------------------------------------------

export function listPortfolios(): Promise<Portfolio[]> {
  return request("/api/v1/portfolios");
}
export function createPortfolio(name: string, baseCurrency = "EUR"): Promise<Portfolio> {
  return request("/api/v1/portfolios", { method: "POST", body: { name, base_currency: baseCurrency } });
}
export function updatePortfolio(portfolioId: string, name: string): Promise<Portfolio> {
  return request(`/api/v1/portfolios/${portfolioId}`, { method: "PATCH", body: { name } });
}
export function deletePortfolio(portfolioId: string): Promise<void> {
  return request(`/api/v1/portfolios/${portfolioId}`, { method: "DELETE" });
}
export function listTransactions(portfolioId: string, cursor?: string): Promise<Page<Transaction>> {
  return request(`/api/v1/portfolios/${portfolioId}/transactions`, { params: { cursor } });
}

export interface TransactionInput {
  instrument_id?: string | null;
  type: string;
  trade_date: string;
  quantity: string;
  unit_price: string;
  currency: string;
  fees?: string;
  account?: string;
  external_id?: string;
  note?: string;
}
export function createTransaction(portfolioId: string, input: TransactionInput): Promise<Transaction> {
  return request(`/api/v1/portfolios/${portfolioId}/transactions`, { method: "POST", body: input });
}
export function reverseTransaction(portfolioId: string, transactionId: string, reason: string): Promise<Transaction> {
  return request(`/api/v1/portfolios/${portfolioId}/transactions/${transactionId}/reverse`, { method: "POST", body: { reason } });
}
export function getPositions(portfolioId: string): Promise<Position[]> {
  return request(`/api/v1/portfolios/${portfolioId}/positions`);
}
export function getValuation(portfolioId: string): Promise<Valuation> {
  return request(`/api/v1/portfolios/${portfolioId}/valuation`);
}

// --- instruments (private) ------------------------------------------------------

export function listInstruments(): Promise<Instrument[]> {
  return request("/api/v1/instruments");
}
export function getInstrument(instrumentId: string): Promise<Instrument> {
  return request(`/api/v1/instruments/${instrumentId}`);
}
export interface InstrumentInput {
  symbol: string;
  name: string;
  asset_class: string;
  isin?: string;
  currency: string;
  exchange?: string;
}
export function createInstrument(input: InstrumentInput): Promise<Instrument> {
  return request("/api/v1/instruments", { method: "POST", body: input });
}
export function deleteInstrument(instrumentId: string): Promise<void> {
  return request(`/api/v1/instruments/${instrumentId}`, { method: "DELETE" });
}
export function listPrices(instrumentId: string): Promise<PricePoint[]> {
  return request(`/api/v1/instruments/${instrumentId}/prices`);
}
export function createPrice(instrumentId: string, input: { as_of: string; price: string; currency: string; is_estimate?: boolean }): Promise<PricePoint> {
  return request(`/api/v1/instruments/${instrumentId}/prices`, { method: "POST", body: input });
}
export function listPrivateValuations(instrumentId: string): Promise<PrivateValuation[]> {
  return request(`/api/v1/instruments/${instrumentId}/private-valuations`);
}
export function createPrivateValuation(
  instrumentId: string,
  input: { valuation_date: string; valuation_amount: string; currency: string; method: string; confidence?: string; note?: string },
): Promise<PrivateValuation> {
  return request(`/api/v1/instruments/${instrumentId}/private-valuations`, { method: "POST", body: input });
}

export interface IndicatorParams extends Params {
  sma?: number;
  ema?: number;
  rsi?: number;
  macd_fast?: number;
  macd_slow?: number;
  macd_signal?: number;
  bollinger?: number;
  bollinger_k?: number;
  atr?: number;
  stochastic?: number;
  days?: number;
}
export function getIndicators(instrumentId: string, params: IndicatorParams = {}): Promise<Indicators> {
  return request(`/api/v1/instruments/${instrumentId}/indicators`, { params });
}

// --- market ---------------------------------------------------------------------

export function searchMarket(q: string, assetClass?: string, limit = 12): Promise<SearchResult> {
  return request("/api/v1/market/search", { params: { q, asset_class: assetClass, limit } });
}
export function addToCatalog(input: {
  provider: string;
  provider_symbol: string;
  symbol: string;
  name: string;
  asset_class: string;
  currency?: string | null;
  exchange?: string | null;
}): Promise<{ instrument: Instrument; created: boolean; warning: string | null }> {
  return request("/api/v1/market/catalog", { method: "POST", body: input });
}
export function getQuote(instrumentId: string): Promise<Quote> {
  return request(`/api/v1/market/instruments/${instrumentId}/quote`);
}
export function getMarketHistory(instrumentId: string, range = "1y"): Promise<MarketHistory> {
  return request(`/api/v1/market/instruments/${instrumentId}/history`, { params: { range } });
}
export function listWatchlist(): Promise<WatchlistItem[]> {
  return request("/api/v1/market/watchlist");
}
export function addToWatchlist(instrumentId: string): Promise<WatchlistItem> {
  return request("/api/v1/market/watchlist", { method: "POST", body: { instrument_id: instrumentId } });
}
export function removeFromWatchlist(itemId: string): Promise<void> {
  return request(`/api/v1/market/watchlist/${itemId}`, { method: "DELETE" });
}
export function quickBuy(
  instrumentId: string,
  input: {
    portfolio_id: string;
    quantity: string;
    unit_price: string;
    currency: string;
    trade_date?: string;
    fees?: string;
    note?: string;
    fund_with_deposit?: boolean;
  },
): Promise<Transaction> {
  return request(`/api/v1/market/instruments/${instrumentId}/quick-buy`, { method: "POST", body: input });
}
export function getMarketOverview(): Promise<OverviewEntry[]> {
  return request("/api/v1/market/overview");
}

// --- imports ----------------------------------------------------------------------

export async function uploadImport(portfolioId: string, file: File): Promise<ImportJob> {
  const formData = new FormData();
  formData.append("file", file);
  const csrfToken = getCsrfToken();
  const headers: Record<string, string> = {};
  if (csrfToken) headers["X-CSRF-Token"] = csrfToken;
  // A FormData body must not get a manual Content-Type: the browser sets the
  // multipart boundary itself.
  const response = await fetch(new URL(`/api/v1/portfolios/${portfolioId}/imports`, API_BASE_URL).toString(), {
    method: "POST",
    headers,
    credentials: "include",
    body: formData,
  });
  if (!response.ok) {
    let message = `Erreur ${response.status}`;
    try {
      message = (await response.json()).message ?? message;
    } catch {
      // keep default
    }
    throw new ApiError(message, response.status);
  }
  return response.json() as Promise<ImportJob>;
}
export function listImports(portfolioId: string): Promise<ImportJobSummary[]> {
  return request(`/api/v1/portfolios/${portfolioId}/imports`);
}
export function getImport(portfolioId: string, jobId: string): Promise<ImportJob> {
  return request(`/api/v1/portfolios/${portfolioId}/imports/${jobId}`);
}
export function previewImport(
  portfolioId: string,
  jobId: string,
  columnMapping: Record<string, string>,
  defaultTimezone = "UTC",
  preset?: string | null,
): Promise<ImportJob> {
  return request(`/api/v1/portfolios/${portfolioId}/imports/${jobId}/preview`, {
    method: "POST",
    body: { column_mapping: columnMapping, default_timezone: defaultTimezone, preset: preset === undefined ? null : preset },
  });
}
export function listImportPresets(): Promise<ImportPreset[]> {
  return request("/api/v1/portfolios/_/imports/presets");
}
export function commitImport(portfolioId: string, jobId: string): Promise<ImportJob> {
  return request(`/api/v1/portfolios/${portfolioId}/imports/${jobId}/commit`, { method: "POST" });
}

// --- analytics ----------------------------------------------------------------------

export interface DateRange extends Params {
  start?: string;
  end?: string;
}
export function getHistory(portfolioId: string, range: DateRange = {}): Promise<History> {
  return request(`/api/v1/portfolios/${portfolioId}/analytics/history`, { params: range });
}
export function getAllocation(portfolioId: string): Promise<Allocation> {
  return request(`/api/v1/portfolios/${portfolioId}/analytics/allocation`);
}
export function getRisk(portfolioId: string, range: DateRange = {}): Promise<Risk> {
  return request(`/api/v1/portfolios/${portfolioId}/analytics/risk`, { params: range });
}
export function getPerformance(portfolioId: string, range: DateRange = {}): Promise<Performance> {
  return request(`/api/v1/portfolios/${portfolioId}/analytics/performance`, { params: range });
}

export interface Subject extends Params {
  portfolio_id?: string;
  instrument_id?: string;
}
export function getReturnStats(subject: Subject, days = 365, riskFreeRate = 0): Promise<ReturnStats> {
  return request("/api/v1/quant/stats", { params: { ...subject, days, risk_free_rate: riskFreeRate } });
}
export function getDrawdown(subject: Subject, days = 365): Promise<Drawdown> {
  return request("/api/v1/quant/drawdown", { params: { ...subject, days } });
}
export function getVar(subject: Subject, days = 365, confidence = 0.95, horizon = 1): Promise<VarResult> {
  return request("/api/v1/quant/var", { params: { ...subject, days, confidence, horizon } });
}
export function getCapm(subject: Subject, benchmarkInstrumentId: string, days = 365, riskFreeRate = 0): Promise<CapmResult> {
  return request("/api/v1/quant/capm", {
    params: { ...subject, benchmark_instrument_id: benchmarkInstrumentId, days, risk_free_rate: riskFreeRate },
  });
}
export function getCorrelation(portfolioId: string, days = 365): Promise<CorrelationResult> {
  return request(`/api/v1/portfolios/${portfolioId}/quant/correlation`, { params: { days } });
}
export function getFrontier(portfolioId: string, days = 365, riskFreeRate = 0, points = 25): Promise<FrontierResult> {
  return request(`/api/v1/portfolios/${portfolioId}/quant/frontier`, { params: { days, risk_free_rate: riskFreeRate, points } });
}
export function getMonteCarlo(subject: Subject, days = 365, horizon = 252, simulations = 2000, seed = 42): Promise<MonteCarloResult> {
  return request("/api/v1/quant/montecarlo", { params: { ...subject, days, horizon, simulations, seed } });
}

// --- news & events --------------------------------------------------------------

export function listInstrumentNews(
  instrumentId: string,
  options: { category?: string; kind?: string; cursor?: string; limit?: number; q?: string } = {},
): Promise<Page<NewsItem>> {
  return request(`/api/v1/instruments/${instrumentId}/news`, { params: options });
}
export function refreshInstrumentNews(instrumentId: string): Promise<NewsRefresh> {
  return request(`/api/v1/instruments/${instrumentId}/news/refresh`, { method: "POST" });
}
export function getInstrumentTimeline(instrumentId: string, options: { granularity?: string; category?: string } = {}): Promise<TimelineEntry[]> {
  return request(`/api/v1/instruments/${instrumentId}/timeline`, { params: options });
}
export function listUpcomingEvents(options: { instrumentId?: string; status?: string; tz?: string; limit?: number } = {}): Promise<CalendarEvent[]> {
  return request("/api/v1/events/upcoming", {
    params: { instrument_id: options.instrumentId, status: options.status, tz: options.tz, limit: options.limit },
  });
}

// --- education ------------------------------------------------------------------

export function listEducation(options: { q?: string; category?: string } = {}): Promise<EducationSummary[]> {
  return request("/api/v1/education", { params: options });
}
export function listEducationCategories(): Promise<{ key: string; label: string }[]> {
  return request("/api/v1/education/categories");
}
export function getEducationArticle(slug: string): Promise<EducationArticle> {
  return request(`/api/v1/education/${slug}`);
}

// --- providers / admin ------------------------------------------------------------

export function getProvidersStatus(): Promise<ProvidersOverview> {
  return request("/api/v1/providers/status");
}
export function adminListMarketProviders(): Promise<MarketProviderState[]> {
  return request("/api/v1/admin/market-providers");
}
export function adminSetMarketProvider(name: string, enabled: boolean, reason?: string): Promise<MarketProviderState> {
  return request(`/api/v1/admin/market-providers/${name}/enabled`, { method: "POST", body: { enabled, reason } });
}
export function adminListNewsProviders(): Promise<NewsProviderStatus[]> {
  return request("/api/v1/admin/news-providers");
}
export function adminSetNewsProvider(providerId: string, enabled: boolean, reason?: string): Promise<NewsProviderStatus> {
  return request(`/api/v1/admin/news-providers/${providerId}/enabled`, { method: "POST", body: { enabled, reason } });
}
export function adminSyncNewsProvider(providerId: string): Promise<IngestionRun> {
  return request(`/api/v1/admin/news-providers/${providerId}/sync`, { method: "POST" });
}
export function adminListRuns(providerId: string): Promise<IngestionRun[]> {
  return request(`/api/v1/admin/news-providers/${providerId}/runs`);
}
export function adminAudit(): Promise<AuditEntry[]> {
  return request("/api/v1/admin/audit");
}

// --- prediction (experimental) ----------------------------------------------------

export function getPredictionStatus(): Promise<PredictionStatus> {
  return request("/api/v1/prediction/status");
}
export function listExperiments(): Promise<ExperimentSummary[]> {
  return request("/api/v1/prediction/experiments");
}
export function createExperiment(input: { instrument_id: string; name: string; config: Partial<ExperimentConfig>; run_now?: boolean }): Promise<Experiment> {
  return request("/api/v1/prediction/experiments", { method: "POST", body: input });
}
export function getExperiment(experimentId: string): Promise<Experiment> {
  return request(`/api/v1/prediction/experiments/${experimentId}`);
}
export function rerunExperiment(experimentId: string): Promise<Experiment> {
  return request(`/api/v1/prediction/experiments/${experimentId}/run`, { method: "POST" });
}
export function deleteExperiment(experimentId: string): Promise<void> {
  return request(`/api/v1/prediction/experiments/${experimentId}`, { method: "DELETE" });
}
