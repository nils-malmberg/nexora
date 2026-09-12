export function formatDateTime(iso: string | null): string {
  if (!iso) return "date inconnue";
  try {
    return new Intl.DateTimeFormat("fr-FR", { dateStyle: "medium", timeStyle: "short" }).format(new Date(iso));
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

/** Decimal amounts arrive as full-precision strings (specs/API_SPEC.md:
 * "Les montants sont des chaînes décimales afin d'éviter les erreurs
 * binaires"). This is purely a display concern: parse for formatting only,
 * never for further arithmetic. */
export function formatAmount(value: string | null, currency?: string): string {
  if (value === null) return "—";
  const parsed = Number(value);
  if (Number.isNaN(parsed)) return value;
  const formatted = new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 2, minimumFractionDigits: 2 }).format(
    parsed,
  );
  return currency ? `${formatted} ${currency}` : formatted;
}

export function formatQuantity(value: string): string {
  const parsed = Number(value);
  if (Number.isNaN(parsed)) return value;
  return new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 8 }).format(parsed);
}
