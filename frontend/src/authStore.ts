/**
 * Holds the CSRF token in memory only (never localStorage) — it is handed to
 * us once by register/login/me and must be echoed back as a header on every
 * mutating request (see api/client.ts). Losing it on a hard page reload is
 * fine: the next `me()` call (issued on app boot) hands back the current
 * session's token again, since the session cookie itself is still valid.
 */
let csrfToken: string | null = null;

export function setCsrfToken(token: string | null): void {
  csrfToken = token;
}

export function getCsrfToken(): string | null {
  return csrfToken;
}
