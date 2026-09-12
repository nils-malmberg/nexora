import { getCsrfToken } from "../authStore";
import type {
  AuthResponse,
  ExportData,
  Instrument,
  Page,
  Portfolio,
  Position,
  PricePoint,
  PrivateValuation,
  ProviderStatus,
  Transaction,
  Valuation,
} from "../types";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8001";

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

async function request<T>(
  path: string,
  options: { method?: string; body?: unknown; params?: Record<string, string | number | undefined> } = {},
): Promise<T> {
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
    } catch {
      // ignore body parse failure, keep default message
    }
    throw new ApiError(message, response.status, requestId);
  }
  return response.json() as Promise<T>;
}

export function register(email: string, password: string, referenceCurrency = "EUR"): Promise<AuthResponse> {
  return request<AuthResponse>("/api/v1/auth/register", {
    method: "POST",
    body: { email, password, reference_currency: referenceCurrency },
  });
}

export function login(email: string, password: string): Promise<AuthResponse> {
  return request<AuthResponse>("/api/v1/auth/login", { method: "POST", body: { email, password } });
}

export function logout(): Promise<void> {
  return request<void>("/api/v1/auth/logout", { method: "POST" });
}

export function me(): Promise<AuthResponse> {
  return request<AuthResponse>("/api/v1/auth/me");
}

export function listPortfolios(): Promise<Portfolio[]> {
  return request<Portfolio[]>("/api/v1/portfolios");
}

export function createPortfolio(name: string, baseCurrency = "EUR"): Promise<Portfolio> {
  return request<Portfolio>("/api/v1/portfolios", { method: "POST", body: { name, base_currency: baseCurrency } });
}

export function updatePortfolio(portfolioId: string, name: string): Promise<Portfolio> {
  return request<Portfolio>(`/api/v1/portfolios/${portfolioId}`, { method: "PATCH", body: { name } });
}

export function deletePortfolio(portfolioId: string): Promise<void> {
  return request<void>(`/api/v1/portfolios/${portfolioId}`, { method: "DELETE" });
}

export function listTransactions(portfolioId: string, cursor?: string): Promise<Page<Transaction>> {
  return request<Page<Transaction>>(`/api/v1/portfolios/${portfolioId}/transactions`, { params: { cursor } });
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
  return request<Transaction>(`/api/v1/portfolios/${portfolioId}/transactions`, { method: "POST", body: input });
}

export function reverseTransaction(portfolioId: string, transactionId: string, reason: string): Promise<Transaction> {
  return request<Transaction>(`/api/v1/portfolios/${portfolioId}/transactions/${transactionId}/reverse`, {
    method: "POST",
    body: { reason },
  });
}

export function getPositions(portfolioId: string): Promise<Position[]> {
  return request<Position[]>(`/api/v1/portfolios/${portfolioId}/positions`);
}

export function getValuation(portfolioId: string): Promise<Valuation> {
  return request<Valuation>(`/api/v1/portfolios/${portfolioId}/valuation`);
}

export function listInstruments(): Promise<Instrument[]> {
  return request<Instrument[]>("/api/v1/instruments");
}

export function searchInstruments(q: string): Promise<Instrument[]> {
  return request<Instrument[]>("/api/v1/instruments/search", { params: { q } });
}

export interface InstrumentInput {
  symbol: string;
  name: string;
  asset_class: string;
  isin?: string;
  currency: string;
}

export function createInstrument(input: InstrumentInput): Promise<Instrument> {
  return request<Instrument>("/api/v1/instruments", { method: "POST", body: input });
}

export function listPrices(instrumentId: string): Promise<PricePoint[]> {
  return request<PricePoint[]>(`/api/v1/instruments/${instrumentId}/prices`);
}

export function createPrice(
  instrumentId: string,
  input: { as_of: string; price: string; currency: string; is_estimate?: boolean },
): Promise<PricePoint> {
  return request<PricePoint>(`/api/v1/instruments/${instrumentId}/prices`, { method: "POST", body: input });
}

export function listPrivateValuations(instrumentId: string): Promise<PrivateValuation[]> {
  return request<PrivateValuation[]>(`/api/v1/instruments/${instrumentId}/private-valuations`);
}

export function createPrivateValuation(
  instrumentId: string,
  input: { valuation_date: string; valuation_amount: string; currency: string; method: string; confidence?: string; note?: string },
): Promise<PrivateValuation> {
  return request<PrivateValuation>(`/api/v1/instruments/${instrumentId}/private-valuations`, {
    method: "POST",
    body: input,
  });
}

export function getProvidersStatus(): Promise<ProviderStatus> {
  return request<ProviderStatus>("/api/v1/providers/status");
}

export function exportMyData(): Promise<ExportData> {
  return request<ExportData>("/api/v1/me/export");
}

export function deleteMyAccount(password: string): Promise<void> {
  return request<void>("/api/v1/me", { method: "DELETE", body: { password } });
}
