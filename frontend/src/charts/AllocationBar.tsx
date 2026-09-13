const PALETTE = ["#1d4ed8", "#a3690a", "#1f7a3d", "#a33a00", "#7c3aed", "#0891b2", "#be185d", "#4b5563"];

export interface AllocationSliceInput {
  label: string;
  share: string; // "0"-"1" decimal string
}

/** Horizontal stacked bar + text legend - no charting dependency, and fully
 * readable without relying on color alone (percentages are always printed
 * as text) - specs/UX_SPEC.md: "Les couleurs ne sont jamais l'unique
 * signal." */
export function AllocationBar({ slices }: { slices: AllocationSliceInput[] }) {
  if (slices.length === 0) {
    return <p className="empty-state">Aucune position à répartir.</p>;
  }
  return (
    <div>
      <div className="allocation-bar">
        {slices.map((s, i) => {
          const pct = Number(s.share) * 100;
          if (pct <= 0) return null;
          return (
            <div
              key={s.label}
              className="allocation-segment"
              style={{ width: `${pct}%`, background: PALETTE[i % PALETTE.length] }}
              title={`${s.label} — ${pct.toFixed(1)}%`}
            />
          );
        })}
      </div>
      <ul className="allocation-legend">
        {slices.map((s, i) => (
          <li key={s.label}>
            <span className="chart-swatch" style={{ background: PALETTE[i % PALETTE.length] }} />
            {s.label} — {(Number(s.share) * 100).toFixed(1)}%
          </li>
        ))}
      </ul>
    </div>
  );
}
