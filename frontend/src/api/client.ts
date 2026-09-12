import type { Asset, CalendarEvent, NewsItem, Page, ProviderStatus, TimelineEntry } from "../types";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public requestId?: string,
  ) {
    super(message);
  }
}

async function request<T>(path: string, params?: Record<string, string | number | undefined>): Promise<T> {
  const url = new URL(path, API_BASE_URL);
  if (params) {
    for (const [key, value] of Object.entries(params)) {
      if (value !== undefined && value !== "") url.searchParams.set(key, String(value));
    }
  }
  const response = await fetch(url.toString());
  if (!response.ok) {
    let message = `Erreur ${response.status}`;
    let requestId: string | undefined;
    try {
      const body = await response.json();
      message = body.message ?? message;
      requestId = body.request_id;
    } catch {
      // ignore body parse failure, keep default message
    }
    throw new ApiError(message, response.status, requestId);
  }
  return response.json() as Promise<T>;
}

export function listAssets(query?: string): Promise<Asset[]> {
  return request<Asset[]>("/api/v1/assets", { q: query });
}

export function getAsset(assetId: string): Promise<Asset> {
  return request<Asset>(`/api/v1/assets/${assetId}`);
}

export function listAssetNews(
  assetId: string,
  options: { category?: string; kind?: string; cursor?: string; limit?: number } = {},
): Promise<Page<NewsItem>> {
  return request<Page<NewsItem>>(`/api/v1/assets/${assetId}/news`, options);
}

export function getAssetTimeline(
  assetId: string,
  options: { granularity?: string; category?: string } = {},
): Promise<TimelineEntry[]> {
  return request<TimelineEntry[]>(`/api/v1/assets/${assetId}/timeline`, options);
}

export function listUpcomingEvents(
  options: { assetId?: string; status?: string; tz?: string } = {},
): Promise<CalendarEvent[]> {
  return request<CalendarEvent[]>("/api/v1/events/upcoming", {
    asset_id: options.assetId,
    status: options.status,
    tz: options.tz,
  });
}

export function getProvidersStatus(): Promise<ProviderStatus[]> {
  return request<ProviderStatus[]>("/api/v1/providers/status");
}
