export function formatDateTime(iso: string | null, timeZone?: string): string {
  if (!iso) return "date inconnue";
  try {
    return new Intl.DateTimeFormat("fr-FR", { dateStyle: "medium", timeStyle: "short", timeZone }).format(new Date(iso));
  } catch {
    return iso;
  }
}

export function formatDate(iso: string | null): string {
  if (!iso) return "date inconnue";
  try {
    return new Intl.DateTimeFormat("fr-FR", { dateStyle: "medium" }).format(new Date(iso));
  } catch {
    return iso;
  }
}

/** Decimal amounts arrive as full-precision strings (specs/API_SPEC.md). This
 * is purely a display concern: parse for formatting only, never for further
 * arithmetic. */
export function formatAmount(value: string | number | null | undefined, currency?: string, digits = 2): string {
  if (value === null || value === undefined) return "—";
  const parsed = typeof value === "number" ? value : Number(value);
  if (Number.isNaN(parsed)) return String(value);
  const formatted = new Intl.NumberFormat("fr-FR", { maximumFractionDigits: digits, minimumFractionDigits: digits }).format(parsed);
  return currency ? `${formatted} ${currency}` : formatted;
}

export function formatQuantity(value: string | number): string {
  const parsed = typeof value === "number" ? value : Number(value);
  if (Number.isNaN(parsed)) return String(value);
  return new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 8 }).format(parsed);
}

/** A ratio (0.0123) rendered as a percentage ("1,23 %"). */
export function formatPct(value: string | number | null | undefined, digits = 2): string {
  if (value === null || value === undefined) return "—";
  const parsed = typeof value === "number" ? value : Number(value);
  if (Number.isNaN(parsed)) return String(value);
  return `${new Intl.NumberFormat("fr-FR", { maximumFractionDigits: digits, minimumFractionDigits: digits }).format(parsed * 100)} %`;
}

export function formatNumber(value: number | null | undefined, digits = 3): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return new Intl.NumberFormat("fr-FR", { maximumFractionDigits: digits }).format(value);
}

export function formatAge(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return "";
  if (seconds < 90) return "à l'instant";
  const minutes = Math.round(seconds / 60);
  if (minutes < 90) return `il y a ${minutes} min`;
  const hours = Math.round(minutes / 60);
  if (hours < 36) return `il y a ${hours} h`;
  return `il y a ${Math.round(hours / 24)} j`;
}
