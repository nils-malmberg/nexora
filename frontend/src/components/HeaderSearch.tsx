import { useEffect, useRef, useState } from "react";
import { addToCatalog, errorMessage, searchMarket } from "../api/client";
import { navigate } from "../router";
import type { Candidate } from "../types";
import { ASSET_CLASS_LABELS } from "../types";

/** Compact instrument search available on every page: type a name, symbol
 * or ISIN, pick a result, land on its page. Debounced; the server rate-limits
 * provider fan-out, so typing never becomes a burst of requests. */
export function HeaderSearch() {
  const [input, setInput] = useState("");
  const [results, setResults] = useState<Candidate[]>([]);
  const [open, setOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const q = input.trim();
    if (q.length < 2) {
      setResults([]);
      return;
    }
    const timer = setTimeout(() => {
      searchMarket(q, undefined, 8)
        .then((r) => {
          setResults(r.candidates);
          setOpen(true);
        })
        .catch((err: unknown) => setError(errorMessage(err, "Recherche impossible")));
    }, 500);
    return () => clearTimeout(timer);
  }, [input]);

  useEffect(() => {
    function onClick(evt: MouseEvent) {
      if (box.current && !box.current.contains(evt.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);

  async function pick(c: Candidate) {
    setOpen(false);
    setError(null);
    try {
      const added = await addToCatalog({
        provider: c.provider,
        provider_symbol: c.provider_symbol,
        symbol: c.symbol,
        name: c.name,
        asset_class: c.asset_class,
        currency: c.currency,
        exchange: c.exchange,
      });
      setInput("");
      navigate("markets", added.instrument.id);
    } catch (err) {
      setError(errorMessage(err, "Impossible d'ouvrir cet instrument"));
    }
  }

  return (
    <div className="header-search" ref={box}>
      <input
        type="search"
        value={input}
        onChange={(e) => setInput(e.target.value)}
        onFocus={() => results.length > 0 && setOpen(true)}
        placeholder="Rechercher un titre, un ETF, une crypto, un ISIN…"
        aria-label="Rechercher un instrument"
      />
      {open && (results.length > 0 || error) && (
        <ul className="header-search-results" role="listbox">
          {error && <li className="muted">{error}</li>}
          {results.map((c) => (
            <li key={`${c.provider}:${c.provider_symbol}`}>
              <button type="button" role="option" aria-selected="false" onClick={() => pick(c)}>
                <strong>{c.symbol}</strong> {c.name}
                <span className="muted">
                  {" "}
                  · {ASSET_CLASS_LABELS[c.asset_class] ?? c.asset_class}
                  {c.exchange ? ` · ${c.exchange}` : ""}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
