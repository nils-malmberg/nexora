import { useEffect, useState } from "react";
import { addToCatalog, errorMessage, searchMarket } from "../api/client";
import { navigate } from "../router";
import type { Candidate, Instrument } from "../types";
import { ASSET_CLASSES, ASSET_CLASS_LABELS } from "../types";
import { AssetClassBadge } from "./Badges";

const DEBOUNCE_MS = 450;

/** Search any quoted instrument (local catalog first, then the configured
 * providers — debounced and rate-limited server-side so typing never turns
 * into a burst of provider calls). Picking a result adds it to the shared
 * catalog and hands the instrument back to the caller. */
export function InstrumentSearch({
  onPicked,
  placeholder = "Rechercher une action, un ETF, une crypto… (nom, symbole ou ISIN)",
  autoNavigate = true,
}: {
  onPicked?: (instrument: Instrument) => void;
  placeholder?: string;
  autoNavigate?: boolean;
}) {
  const [input, setInput] = useState("");
  const [assetClass, setAssetClass] = useState("");
  const [query, setQuery] = useState("");
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [providerErrors, setProviderErrors] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  useEffect(() => {
    const timer = setTimeout(() => setQuery(input.trim()), DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [input]);

  useEffect(() => {
    if (query.length < 2) {
      setCandidates([]);
      setProviderErrors({});
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    searchMarket(query, assetClass || undefined)
      .then((result) => {
        if (cancelled) return;
        setCandidates(result.candidates);
        setProviderErrors(result.provider_errors);
      })
      .catch((err: unknown) => !cancelled && setError(errorMessage(err, "Recherche impossible")))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [query, assetClass]);

  async function pick(candidate: Candidate) {
    setBusy(candidate.provider_symbol);
    setError(null);
    try {
      const result = await addToCatalog({
        provider: candidate.provider,
        provider_symbol: candidate.provider_symbol,
        symbol: candidate.symbol,
        name: candidate.name,
        asset_class: candidate.asset_class,
        currency: candidate.currency,
        exchange: candidate.exchange,
      });
      onPicked?.(result.instrument);
      if (autoNavigate) navigate("markets", result.instrument.id);
    } catch (err) {
      setError(errorMessage(err, "Impossible d'ajouter cet instrument"));
    } finally {
      setBusy(null);
    }
  }

  const providerErrorText = Object.entries(providerErrors)
    .map(([name, reason]) => `${name} : ${reason.replaceAll("_", " ")}`)
    .join(" · ");

  return (
    <div className="instrument-search">
      <div className="inline-form">
        <input
          type="search"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder={placeholder}
          aria-label="Rechercher un instrument"
          className="search-input"
        />
        <select value={assetClass} onChange={(e) => setAssetClass(e.target.value)} aria-label="Classe d'actif">
          <option value="">Toutes classes</option>
          {ASSET_CLASSES.filter((c) => c !== "actif_prive" && c !== "obligation").map((c) => (
            <option key={c} value={c}>
              {ASSET_CLASS_LABELS[c]}
            </option>
          ))}
        </select>
      </div>
      {loading && <p className="muted">Recherche…</p>}
      {error && <p className="error-state">{error}</p>}
      {providerErrorText && <p className="prediction-warning">Fournisseur : {providerErrorText} — résultats du catalogue local uniquement.</p>}
      {query.length >= 2 && !loading && candidates.length === 0 && !error && <p className="muted">Aucun résultat.</p>}
      {candidates.length > 0 && (
        <ul className="search-results" aria-label="Résultats">
          {candidates.map((c) => (
            <li key={`${c.provider}:${c.provider_symbol}`}>
              <button type="button" className="search-result" onClick={() => pick(c)} disabled={busy !== null}>
                <span className="search-result-symbol">{c.symbol}</span>
                <span className="search-result-name">{c.name}</span>
                <span className="search-result-meta">
                  <AssetClassBadge assetClass={c.asset_class} label={ASSET_CLASS_LABELS[c.asset_class] ?? c.asset_class} />
                  {c.exchange && <span className="muted">{c.exchange}</span>}
                  {c.currency && <span className="muted">{c.currency}</span>}
                  <span className="muted">{c.in_catalog ? "au catalogue" : `via ${c.provider}`}</span>
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
