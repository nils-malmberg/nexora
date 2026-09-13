import { useEffect, useState } from "react";
import {
  ApiError,
  commitImport,
  getImport,
  listImportPresets,
  listImports,
  previewImport,
  uploadImport,
} from "../api/client";
import { exportAsJson } from "../export";
import { formatDateTime } from "../format";
import { CANONICAL_IMPORT_FIELDS, type ImportJob, type ImportJobSummary, type ImportPreset } from "../types";

const FIELD_LABELS: Record<string, string> = {
  date: "Date",
  type: "Type",
  symbol: "Symbole",
  isin: "ISIN",
  asset_class: "Classe d'actif",
  quantity: "Quantité",
  unit_price: "Prix / Montant",
  currency: "Devise",
  fees: "Frais",
  account: "Compte",
  external_id: "Identifiant externe",
  note: "Note",
};

const GENERIC_INSTRUCTIONS = [
  "Un fichier CSV avec une ligne d'en-tête ; séparateur virgule, point-virgule ou tabulation, détecté automatiquement.",
  "Colonnes reconnues : date, type, symbol ou isin, asset_class, quantity, unit_price, currency, fees, account, external_id, note.",
  "Types acceptés : achat, vente, dividende, coupon, intérêts, frais, dépôt, retrait, split (ou leurs équivalents anglais/allemands).",
];

const MAX_DISPLAYED_ROWS = 200;

function statusLabel(status: string): string {
  switch (status) {
    case "valid":
      return "Valide";
    case "duplicate":
      return "Doublon (ignoré)";
    case "error":
      return "Erreur";
    case "inserted":
      return "Importée";
    default:
      return status;
  }
}

export function ImportWizard({ portfolioId, onCommitted }: { portfolioId: string; onCommitted: () => void }) {
  const [job, setJob] = useState<ImportJob | null>(null);
  const [mapping, setMapping] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [history, setHistory] = useState<ImportJobSummary[]>([]);
  const [presets, setPresets] = useState<ImportPreset[]>([]);
  const [chosenPreset, setChosenPreset] = useState<string>("auto");

  function reloadHistory() {
    listImports(portfolioId).then(setHistory).catch(() => undefined);
  }

  useEffect(reloadHistory, [portfolioId]);
  useEffect(() => {
    listImportPresets().then(setPresets).catch(() => setPresets([]));
  }, []);

  async function handleFileSelected(file: File) {
    setError(null);
    setBusy(true);
    try {
      const created = await uploadImport(portfolioId, file);
      setJob(created);
      setMapping(created.column_mapping);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Impossible d'analyser ce fichier");
    } finally {
      setBusy(false);
    }
  }

  async function handlePreview() {
    if (!job) return;
    setError(null);
    setBusy(true);
    try {
      const presetOverride = chosenPreset === "auto" ? null : chosenPreset === "generic" ? "" : chosenPreset;
      const updated = await previewImport(portfolioId, job.id, mapping, "UTC", presetOverride);
      setJob(updated);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Impossible de valider ce mapping");
    } finally {
      setBusy(false);
    }
  }

  async function handleCommit() {
    if (!job) return;
    if (!window.confirm("Confirmer l'import ? Les lignes valides seront ajoutées au portefeuille.")) return;
    setError(null);
    setBusy(true);
    try {
      const updated = await commitImport(portfolioId, job.id);
      setJob(updated);
      reloadHistory();
      onCommitted();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Impossible de confirmer cet import");
    } finally {
      setBusy(false);
    }
  }

  function handleReset() {
    setJob(null);
    setMapping({});
    setError(null);
  }

  async function handleOpenHistoryJob(jobId: string) {
    setError(null);
    try {
      setJob(await getImport(portfolioId, jobId));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Impossible de charger cet import");
    }
  }

  function handleDownloadReport() {
    if (!job) return;
    exportAsJson(`nexora-import-${job.id}.json`, job);
  }

  const guideKey = chosenPreset === "auto" ? null : chosenPreset;
  const guide = guideKey && guideKey !== "generic" ? presets.find((p) => p.key === guideKey) : null;
  const activePreset = job?.preset ? presets.find((p) => p.key === job.preset) : null;

  return (
    <section aria-label="Importer des opérations">
      <h3>Importer depuis un courtier ou un fichier CSV</h3>
      <p className="muted">
        Trade Republic, Revolut et les autres courtiers n'offrent pas d'accès en lecture seule sécurisé à un compte personnel : la voie sûre est
        l'export de l'application, importé ici. Rien n'est écrit avant votre confirmation, chaque ligne est vérifiée et un doublon est ignoré,
        jamais compté deux fois.
      </p>
      {error && <p className="error-state">{error}</p>}

      {!job && (
        <>
          <div className="preset-grid" role="radiogroup" aria-label="Source du fichier">
            {[{ key: "auto", label: "Détection automatique", instructions: ["Le format est reconnu d'après les colonnes du fichier."], notes: [] }, ...presets, { key: "generic", label: "CSV générique", instructions: GENERIC_INSTRUCTIONS, notes: [] }].map((p) => (
              <label key={p.key} className={chosenPreset === p.key ? "preset-card selected" : "preset-card"}>
                <input type="radio" name="preset" value={p.key} checked={chosenPreset === p.key} onChange={() => setChosenPreset(p.key)} />
                <strong>{p.label}</strong>
              </label>
            ))}
          </div>
          {(guide ?? (chosenPreset === "generic" ? { instructions: GENERIC_INSTRUCTIONS, notes: [] } : null)) && (
            <ol className="instructions">
              {(guide?.instructions ?? GENERIC_INSTRUCTIONS).map((step, i) => (
                <li key={i}>{step}</li>
              ))}
            </ol>
          )}
          {guide && guide.notes.length > 0 && (
            <ul className="plain-list">
              {guide.notes.map((n) => (
                <li key={n}>{n}</li>
              ))}
            </ul>
          )}
          <div className="inline-form">
            <input
              type="file"
              accept=".csv,text/csv,.txt"
              disabled={busy}
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) void handleFileSelected(file);
                e.target.value = "";
              }}
            />
            {busy && <span className="muted">Analyse du fichier…</span>}
          </div>
        </>
      )}

      {job && job.status === "draft" && (
        <div>
          <p className="muted">
            {job.filename} — {job.total_rows} ligne(s) détectée(s), séparateur {job.delimiter === "\t" ? "tabulation" : job.delimiter!}, encodage {job.encoding}.
          </p>
          {job.preset ? (
            <p className="provider-banner" role="status">
              Format reconnu : <strong>{job.preset_label}</strong>. Les colonnes et les types d'opération sont convertis automatiquement ; vérifiez l'aperçu puis validez.
              {activePreset?.notes.map((n) => (
                <span key={n}>
                  <br />
                  {n}
                </span>
              ))}
              <br />
              <button type="button" className="link-button" onClick={() => setChosenPreset("generic")}>
                Ce n'est pas le bon format ? Utiliser le mapping générique
              </button>
            </p>
          ) : (
            <p className="muted">Aucun format de courtier reconnu : associez chaque colonne ci-dessous.</p>
          )}
          {(!job.preset || chosenPreset === "generic") && <h4>Mapping des colonnes</h4>}
          {(!job.preset || chosenPreset === "generic") && (
          <div className="form-grid">
            {CANONICAL_IMPORT_FIELDS.map((field) => (
              <label key={field}>
                {FIELD_LABELS[field]}
                <select
                  value={mapping[field] ?? ""}
                  onChange={(e) => setMapping((prev) => ({ ...prev, [field]: e.target.value }))}
                >
                  <option value="">— non mappé —</option>
                  {(job.headers ?? []).map((header) => (
                    <option key={header} value={header}>
                      {header}
                    </option>
                  ))}
                </select>
              </label>
            ))}
          </div>
          )}
          {job.sample_rows && job.sample_rows.length > 0 && (
            <>
              <h4>Aperçu (5 premières lignes{job.preset ? " converties" : " brutes"})</h4>
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      {job.headers?.map((h) => <th key={h}>{h}</th>)}
                    </tr>
                  </thead>
                  <tbody>
                    {job.sample_rows.map((row, i) => (
                      <tr key={i}>
                        {job.headers?.map((h) => <td key={h}>{row[h]}</td>)}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
          <button type="button" className="primary-button" onClick={handlePreview} disabled={busy}>
            Valider (aperçu)
          </button>
          <button type="button" onClick={handleReset} disabled={busy}>
            Annuler
          </button>
        </div>
      )}

      {job && (job.status === "previewed" || job.status === "committed") && (
        <div>
          <p>
            {job.total_rows} ligne(s) —{" "}
            {job.status === "committed" ? (
              <>
                <strong>{job.inserted_count}</strong> importée(s),{" "}
              </>
            ) : (
              <>
                <strong>{job.valid_count}</strong> valide(s),{" "}
              </>
            )}
            <strong>{job.duplicate_count}</strong> doublon(s) ignoré(s), <strong>{job.error_count}</strong> en erreur.
          </p>
          {job.status === "previewed" && (
            <p className="prediction-warning" role="note">
              Aucune donnée n'a encore été enregistrée. Vérifiez le rapport ci-dessous avant de confirmer.
            </p>
          )}
          {job.preset_label && <p className="muted">Format : {job.preset_label}</p>}
          {job.resolved_isins && Object.keys(job.resolved_isins).length > 0 && (
            <p className="muted">
              ISIN reconnus :{" "}
              {Object.entries(job.resolved_isins)
                .map(([isin, symbol]) => `${isin} → ${symbol}`)
                .join(" · ")}
            </p>
          )}
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Ligne</th>
                  <th>Statut</th>
                  <th>Type</th>
                  <th>Symbole</th>
                  <th>Détails</th>
                </tr>
              </thead>
              <tbody>
                {(job.rows ?? []).slice(0, MAX_DISPLAYED_ROWS).map((row) => (
                  <tr key={row.row_number} className={row.status === "error" ? "row-warning" : undefined}>
                    <td>{row.row_number}</td>
                    <td>{statusLabel(row.status)}</td>
                    <td>{row.canonical?.type ?? "—"}</td>
                    <td>{row.canonical?.symbol ?? row.canonical?.isin ?? "—"}</td>
                    <td>{row.messages.join(" · ")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {(job.rows?.length ?? 0) > MAX_DISPLAYED_ROWS && (
            <p className="muted">
              Affichage limité aux {MAX_DISPLAYED_ROWS} premières lignes sur {job.rows?.length}.
            </p>
          )}

          {job.status === "previewed" && (
            <button type="button" className="primary-button" onClick={handleCommit} disabled={busy}>
              Confirmer l'import
            </button>
          )}
          <button type="button" className="export-button" onClick={handleDownloadReport}>
            Télécharger le rapport (JSON)
          </button>
          <button type="button" onClick={handleReset}>
            Nouvel import
          </button>
        </div>
      )}

      {history.length > 0 && (
        <>
          <h4>Imports précédents</h4>
          <ul className="plain-list">
            {history.map((h) => (
              <li key={h.id}>
                <button type="button" className="link-button" onClick={() => handleOpenHistoryJob(h.id)}>
                  {h.filename}
                </button>{" "}
                — {formatDateTime(h.created_at)} — {h.status} — {h.inserted_count} importée(s), {h.error_count} erreur(s)
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
