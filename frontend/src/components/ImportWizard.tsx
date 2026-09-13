import { useEffect, useState } from "react";
import {
  ApiError,
  commitImport,
  getImport,
  listImports,
  previewImport,
  uploadImport,
} from "../api/client";
import { exportAsJson } from "../export";
import { formatDateTime } from "../format";
import { CANONICAL_IMPORT_FIELDS, type ImportJob, type ImportJobSummary } from "../types";

const FIELD_LABELS: Record<string, string> = {
  date: "Date",
  type: "Type",
  symbol: "Symbole",
  asset_class: "Classe d'actif",
  quantity: "Quantité",
  unit_price: "Prix / Montant",
  currency: "Devise",
  fees: "Frais",
  account: "Compte",
  external_id: "Identifiant externe",
};

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

  function reloadHistory() {
    listImports(portfolioId).then(setHistory).catch(() => undefined);
  }

  useEffect(reloadHistory, [portfolioId]);

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
      const updated = await previewImport(portfolioId, job.id, mapping);
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

  return (
    <section aria-label="Import CSV">
      <h3>Import CSV</h3>
      {error && <p className="error-state">{error}</p>}

      {!job && (
        <div className="inline-form">
          <input
            type="file"
            accept=".csv,text/csv"
            disabled={busy}
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) void handleFileSelected(file);
              e.target.value = "";
            }}
          />
          <span className="muted">Colonnes attendues : date, type, symbol, asset_class, quantity, unit_price, currency, fees, account, external_id</span>
        </div>
      )}

      {job && job.status === "draft" && (
        <div>
          <p className="muted">
            {job.filename} — {job.total_rows} ligne(s) détectée(s), séparateur {job.delimiter === "\t" ? "tabulation" : job.delimiter!}, encodage {job.encoding}.
          </p>
          <h4>Mapping des colonnes</h4>
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
          {job.sample_rows && job.sample_rows.length > 0 && (
            <>
              <h4>Aperçu (5 premières lignes brutes)</h4>
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
                    <td>{row.canonical?.symbol ?? "—"}</td>
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
