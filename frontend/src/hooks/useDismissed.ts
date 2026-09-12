import { useEffect, useState } from "react";

const STORAGE_KEY = "nexora-dismissed-items";

function readStoredSet(): Set<string> {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? new Set(JSON.parse(raw) as string[]) : new Set();
  } catch {
    // Private browsing / disabled storage: masquage local ne persiste pas,
    // mais la page reste utilisable pour la session en cours.
    return new Set();
  }
}

/** "Suppression/masquage local" (specs/NEWS_AND_EVENTS.md): hides an item
 * for this browser only - never deletes anything server-side, and every
 * other viewer still sees it normally. */
export function useDismissed() {
  const [dismissed, setDismissed] = useState<Set<string>>(() => readStoredSet());

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify([...dismissed]));
    } catch {
      // ignore quota/private-mode errors
    }
  }, [dismissed]);

  const dismiss = (id: string) => setDismissed((prev) => new Set(prev).add(id));
  const restore = (id: string) =>
    setDismissed((prev) => {
      const next = new Set(prev);
      next.delete(id);
      return next;
    });

  return { dismissed, dismiss, restore };
}
