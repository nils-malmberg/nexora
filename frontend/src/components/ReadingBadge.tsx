import type { Reading } from "../types";
import { READING_HINTS, READING_LABELS } from "../types";

const ICONS: Record<Reading, string> = { favorable: "▲", defavorable: "▼", neutre: "●", indisponible: "—" };

/** Colour + icon + word: never colour alone (specs/UX_SPEC.md). */
export function ReadingBadge({ reading, compact = false }: { reading: Reading; compact?: boolean }) {
  return (
    <span className={`badge reading reading-${reading}`} title={READING_HINTS[reading]}>
      <span aria-hidden="true">{ICONS[reading]}</span> {compact ? READING_LABELS[reading].slice(0, 3).toLowerCase() + "." : READING_LABELS[reading]}
    </span>
  );
}

export function TallyBar({ tally, label }: { tally: { favorable: number; defavorable: number; neutre: number; indisponible: number; available: number }; label?: string }) {
  const total = tally.available + tally.indisponible;
  if (total === 0) return null;
  const seg = (n: number, cls: string, title: string) => (n > 0 ? <div key={cls} className={`tally-segment tally-${cls}`} style={{ width: `${(n / total) * 100}%` }} title={`${n} ${title}`} /> : null);
  return (
    <div className="tally" aria-label={label ?? "Répartition des lectures"}>
      <div className="tally-bar">
        {seg(tally.favorable, "favorable", "favorable(s)")}
        {seg(tally.neutre, "neutre", "neutre(s)")}
        {seg(tally.defavorable, "defavorable", "défavorable(s)")}
        {seg(tally.indisponible, "indisponible", "indisponible(s)")}
      </div>
      <span className="muted tally-text">
        <span className="reading-favorable-text">▲ {tally.favorable}</span> · <span>● {tally.neutre}</span> · <span className="reading-defavorable-text">▼ {tally.defavorable}</span>
        {tally.indisponible > 0 && <span> · — {tally.indisponible}</span>}
      </span>
    </div>
  );
}
