import type { AppConfig } from "./types";

/** Product switches fetched once at boot (GET /api/v1/config) and read by
 * pages to hide what is disabled (portfolio bookkeeping) or automatic
 * (single-user session). Defaults are the conservative ones. */
let config: AppConfig = { single_user: false, portfolios_enabled: false, prediction_enabled: false, environment: "unknown" };

export function setAppConfig(next: AppConfig): void {
  config = next;
}

export function appConfig(): AppConfig {
  return config;
}
