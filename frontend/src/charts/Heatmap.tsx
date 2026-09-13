/** Correlation matrix: colour is never the only signal - every cell shows
 * its value, and the colour scale is labelled. */
export function Heatmap({ labels, matrix }: { labels: string[]; matrix: (number | null)[][] }) {
  if (labels.length === 0) return <p className="empty-state">Aucune donnée.</p>;
  const color = (v: number | null) => {
    if (v === null) return "transparent";
    // -1 -> blue, 0 -> neutral, +1 -> orange; alpha grows with |v|
    const alpha = Math.min(1, Math.abs(v)) * 0.75;
    return v >= 0 ? `rgba(214, 143, 0, ${alpha})` : `rgba(29, 78, 216, ${alpha})`;
  };
  return (
    <div className="table-scroll">
      <table className="heatmap" aria-label="Matrice de corrélation">
        <thead>
          <tr>
            <th />
            {labels.map((l) => (
              <th key={l} scope="col">
                {l}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {labels.map((row, i) => (
            <tr key={row}>
              <th scope="row">{row}</th>
              {labels.map((col, j) => {
                const v = matrix[i]?.[j] ?? null;
                return (
                  <td key={col} style={{ background: color(v) }} title={`${row} / ${col}`}>
                    {v === null ? "—" : v.toFixed(2)}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
      <p className="muted">Échelle : bleu = corrélation négative, orange = positive, intensité ∝ |ρ|.</p>
    </div>
  );
}
