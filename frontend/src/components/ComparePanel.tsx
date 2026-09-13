import { useState } from "react";
import { compareInstruments, errorMessage } from "../api/client";
import { LineChart } from "../charts/LineChart";
import { formatPct } from "../format";
import { href } from "../router";
import type { Comparison, Instrument } from "../types";
import { EducationNote } from "./EducationNote";

const PALETTE = ["#1d4ed8", "#a33a00", "#1f7a3d", "#7c3aed", "#0891b2", "#be185d"];
const MAX = 6;

/** Rebased (base 100) comparison of up to six tracked instruments on their
 * common dates — relative paths, each in its own currency. */
export function ComparePanel({ instruments }: { instruments: Instrument[] }) {
  const [selected, setSelected] = useState<string[]>([]);
  const [days, setDays] = useState(365);
  const [result, setResult] = useState<Comparison | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function toggle(id: string) {
    setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : s.length < MAX ? [...s, id] : s));
  }

  async function run() {
    setLoading(true);
    setError(null);
    try {
      setResult(await compareInstruments(selected, days));
    } catch (err) {
      setError(errorMessage(err, "Comparaison impossible"));
    } finally {
      setLoading(false);
    }
  }

  if (instruments.length < 2) return null;

  return (
    <section aria-label="Comparer en base 100">
      <h3>Comparer (base 100)</h3>
      <p className="muted">Jusqu'à {MAX} instruments détenus ou suivis, rebasés à 100 au premier jour commun. Trajectoires relatives, chacune dans sa devise.</p>
      <div className="chip-row" role="group" aria-label="Instruments à comparer">
        {instruments.map((i) => (
          <label key={i.id} className={selected.includes(i.id) ? "chip active" : "chip"}>
            <input type="checkbox" checked={selected.includes(i.id)} onChange={() => toggle(i.id)} disabled={!selected.includes(i.id) && selected.length >= MAX} /> {i.symbol}
          </label>
        ))}
      </div>
      <div className="inline-form">
        <label>
          Fenêtre
          <select value={days} onChange={(e) => setDays(Number(e.target.value))}>
            <option value={90}>3 mois</option>
            <option value={180}>6 mois</option>
            <option value={365}>1 an</option>
            <option value={730}>2 ans</option>
            <option value={1825}>5 ans</option>
          </select>
        </label>
        <button type="button" className="primary-button" onClick={run} disabled={loading || selected.length < 2}>
          {loading ? "Calcul…" : "Comparer"}
        </button>
      </div>
      {error && <p className="error-state">{error}</p>}
      {result && result.observations < 2 && <p className="empty-state">Aucune date commune entre ces instruments sur la fenêtre.</p>}
      {result && result.observations >= 2 && (
        <>
          <LineChart
            series={result.series.map((s, i) => ({
              label: s.instrument.symbol,
              color: PALETTE[i % PALETTE.length],
              points: result.dates.map((d, j) => ({ x: new Date(d), y: s.values[j] })),
            }))}
            referenceLines={[{ y: 100, label: "100" }]}
            yFormatter={(v) => v.toFixed(0)}
            height={280}
            ariaLabel="Comparaison en base 100"
          />
          <ul className="allocation-legend">
            {result.series.map((s, i) => (
              <li key={s.instrument.id}>
                <span className="chart-swatch" style={{ background: PALETTE[i % PALETTE.length] }} />
                <a href={href("markets", s.instrument.id)}>{s.instrument.symbol}</a> ({s.instrument.currency}) — {formatPct(s.total_return)}
              </li>
            ))}
          </ul>
          <p className="muted">
            {result.observations} dates communes · {result.method}
          </p>
        </>
      )}
      <EducationNote slug="comparaison-base-100" />
    </section>
  );
}
