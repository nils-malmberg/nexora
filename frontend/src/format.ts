export function formatDateTime(iso: string | null, timeZone?: string): string {
  if (!iso) return "date inconnue";
  try {
    return new Intl.DateTimeFormat("fr-FR", {
      dateStyle: "medium",
      timeStyle: "short",
      timeZone,
    }).format(new Date(iso));
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
