import { useEffect, useState } from "react";
import { createExperiment, deleteExperiment, errorMessage, getExperiment, getPredictionStatus, listExperiments, listInstruments, rerunExperiment } from "../api/client";
import { LineChart } from "../charts/LineChart";
import { EducationNote } from "../components/EducationNote";
import { formatAmount, formatDateTime, formatNumber, formatPct } from "../format";
import type { Experiment, ExperimentSummary, Instrument, PredictionStatus } from "../types";
import { MODEL_LABELS } from "../types";

const ALL_MODELS = ["naive_last", "historical_mean", "ridge", "random_forest", "gradient_boosting"];

/** Experimental prediction lab (specs/PREDICTION.md): configure and train a
 * stacked meta-model with chronological walk-forward validation, compare it
 * to the naive benchmark, read its calibrated interval. Off by default
 * (server-side kill switch) and framed as education, never advice. */
export function PredictionPage({ initialInstrumentId }: { initialInstrumentId?: string }) {
  const [status, setStatus] = useState<PredictionStatus | null>(null);
  const [instruments, setInstruments] = useState<Instrument[]>([]);
  const [experiments, setExperiments] = useState<ExperimentSummary[]>([]);
  const [selected, setSelected] = useState<Experiment | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState({
    instrument_id: initialInstrumentId ?? "",
    name: "",
    horizon: 5,
    lags: 10,
    windows: "5,20,60",
    models: ["naive_last", "ridge", "random_forest", "gradient_boosting"],
    meta_model: "ridge_stacking" as "ridge_stacking" | "mean",
    n_folds: 5,
    min_train: 120,
    seed: 42,
    interval_confidence: 0.8,
  });
  const [submitting, setSubmitting] = useState(false);

  async function refresh() {
    try {
      const st = await getPredictionStatus();
      setStatus(st);
      if (st.enabled) setExperiments(await listExperiments());
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  useEffect(() => {
    refresh();
    listInstruments()
      .then((list) => {
        setInstruments(list);
        if (!form.instrument_id && list.length > 0) setForm((f) => ({ ...f, instrument_id: list[0].id }));
      })
      .catch(() => setInstruments([]));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Poll while an experiment is running (training happens in a background thread).
  useEffect(() => {
    if (!selected || (selected.status !== "running" && selected.status !== "pending")) return;
    const timer = setInterval(async () => {
      try {
        const exp = await getExperiment(selected.id);
        setSelected(exp);
        if (exp.status === "completed" || exp.status === "failed") setExperiments(await listExperiments());
      } catch {
        // keep polling
      }
    }, 2000);
    return () => clearInterval(timer);
  }, [selected]);

  async function submit(evt: React.FormEvent) {
    evt.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const instrument = instruments.find((i) => i.id === form.instrument_id);
      const exp = await createExperiment({
        instrument_id: form.instrument_id,
        name: form.name || `${instrument?.symbol ?? "exp"} h${form.horizon}`,
        config: {
          horizon: form.horizon,
          lags: form.lags,
          windows: form.windows.split(",").map((w) => Number(w.trim())).filter((w) => w >= 2),
          models: form.models,
          meta_model: form.meta_model,
          n_folds: form.n_folds,
          min_train: form.min_train,
          seed: form.seed,
          interval_confidence: form.interval_confidence,
        },
      });
      setSelected(exp);
      setExperiments(await listExperiments());
    } catch (err) {
      setError(errorMessage(err, "Création impossible"));
    } finally {
      setSubmitting(false);
    }
  }

  async function open(id: string) {
    try {
      setSelected(await getExperiment(id));
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  async function remove(id: string) {
    if (!window.confirm("Supprimer cette expérience ?")) return;
    try {
      await deleteExperiment(id);
      if (selected?.id === id) setSelected(null);
      setExperiments(await listExperiments());
    } catch (err) {
      setError(errorMessage(err, "Suppression impossible"));
    }
  }

  if (!status) return <p className="loading-state">Chargement…</p>;

  return (
    <section aria-label="Prédiction expérimentale">
      <h2>Prédiction — module expérimental</h2>
      <p className="prediction-warning" role="note">
        {status.disclaimer}
      </p>
      {!status.enabled && (
        <p className="empty-state">
          Le module est désactivé sur ce serveur (interrupteur <code>NEXORA_PREDICTION_ENABLED</code>). Un administrateur peut l'activer après lecture de specs/PREDICTION.md.
        </p>
      )}
      {error && <p className="error-state">{error}</p>}
      {status.enabled && (
        <div className="two-columns">
          <form className="card" onSubmit={submit} aria-label="Nouvelle expérience">
            <h3>Entraîner un métamodèle</h3>
            <div className="form-grid">
              <label>
                Instrument (≥ {status.min_observations} clôtures quotidiennes)
                <select value={form.instrument_id} onChange={(e) => setForm({ ...form, instrument_id: e.target.value })} required>
                  {instruments.map((i) => (
                    <option key={i.id} value={i.id}>
                      {i.symbol} — {i.name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Nom
                <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="optionnel" maxLength={120} />
              </label>
              <label>
                Horizon (jours de cotation)
                <input type="number" min={1} max={60} value={form.horizon} onChange={(e) => setForm({ ...form, horizon: Number(e.target.value) })} />
              </label>
              <label>
                Retards de rendement (lags)
                <input type="number" min={1} max={60} value={form.lags} onChange={(e) => setForm({ ...form, lags: Number(e.target.value) })} />
              </label>
              <label>
                Fenêtres glissantes (jours, séparés par des virgules)
                <input value={form.windows} onChange={(e) => setForm({ ...form, windows: e.target.value })} />
              </label>
              <fieldset className="checkbox-group">
                <legend>Modèles de base</legend>
                {ALL_MODELS.map((m) => (
                  <label key={m} className="inline-check">
                    <input
                      type="checkbox"
                      checked={form.models.includes(m)}
                      onChange={(e) => setForm({ ...form, models: e.target.checked ? [...form.models, m] : form.models.filter((x) => x !== m) })}
                    />{" "}
                    {MODEL_LABELS[m]}
                  </label>
                ))}
              </fieldset>
              <label>
                Métamodèle
                <select value={form.meta_model} onChange={(e) => setForm({ ...form, meta_model: e.target.value as "ridge_stacking" | "mean" })}>
                  <option value="ridge_stacking">Stacking (poids positifs, moindres carrés)</option>
                  <option value="mean">Moyenne simple</option>
                </select>
              </label>
              <label>
                Plis walk-forward
                <input type="number" min={2} max={12} value={form.n_folds} onChange={(e) => setForm({ ...form, n_folds: Number(e.target.value) })} />
              </label>
              <label>
                Entraînement minimal (observations)
                <input type="number" min={60} max={2000} value={form.min_train} onChange={(e) => setForm({ ...form, min_train: Number(e.target.value) })} />
              </label>
              <label>
                Confiance de l'intervalle
                <select value={form.interval_confidence} onChange={(e) => setForm({ ...form, interval_confidence: Number(e.target.value) })}>
                  <option value={0.5}>50 %</option>
                  <option value={0.8}>80 %</option>
                  <option value={0.9}>90 %</option>
                  <option value={0.95}>95 %</option>
                </select>
              </label>
              <label>
                Graine aléatoire
                <input type="number" min={0} value={form.seed} onChange={(e) => setForm({ ...form, seed: Number(e.target.value) })} />
              </label>
            </div>
            <button type="submit" className="primary-button" disabled={submitting || form.models.length === 0 || !form.instrument_id}>
              {submitting ? "Entraînement…" : "Entraîner et valider"}
            </button>
          </form>
          <div>
            <h3>Expériences</h3>
            {experiments.length === 0 ? (
              <p className="empty-state">Aucune expérience.</p>
            ) : (
              <ul className="plain-list">
                {experiments.map((e) => (
                  <li key={e.id}>
                    <button type="button" className="link-button" onClick={() => open(e.id)}>
                      {e.name}
                    </button>{" "}
                    <span className="muted">
                      {e.instrument_symbol} · h={e.horizon} · {e.status} · {e.trained_at ? formatDateTime(e.trained_at) : "—"}
                    </span>{" "}
                    <button type="button" className="link-button danger" onClick={() => remove(e.id)}>
                      supprimer
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}
      {selected && <ExperimentDetail experiment={selected} onRerun={async () => setSelected(await rerunExperiment(selected.id))} />}
      <EducationNote slug="prediction-walk-forward" />
      <EducationNote slug="metamodeles-stacking" />
    </section>
  );
}

function ExperimentDetail({ experiment, onRerun }: { experiment: Experiment; onRerun: () => Promise<void> }) {
  const models = experiment.metrics.models ?? {};
  const weights = experiment.metrics.meta_weights ?? {};
  const forecast = experiment.latest_forecast;
  return (
    <section className="card" aria-label={`Expérience ${experiment.name}`}>
      <h3>
        {experiment.name} <span className="muted">— {experiment.instrument_symbol}</span>
      </h3>
      <p className="muted">
        Statut : <strong>{experiment.status}</strong> · {experiment.n_observations} observations{experiment.dataset_start ? ` (${formatDateTime(experiment.dataset_start)} → ${formatDateTime(experiment.dataset_end)})` : ""} · code {experiment.code_version} · jeu de données {experiment.dataset_hash?.slice(0, 12) ?? "—"} · graine {experiment.config.seed}
      </p>
      {experiment.status === "running" && <p className="loading-state">Entraînement en cours…</p>}
      {experiment.status === "failed" && <p className="error-state">Échec : {experiment.error}</p>}
      {experiment.status === "completed" && (
        <>
          <h4>Performance hors échantillon (walk-forward)</h4>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Modèle</th>
                  <th>MAE</th>
                  <th>RMSE</th>
                  <th>RMSE / naïf</th>
                  <th>Bonne direction</th>
                  <th>Biais</th>
                  <th>Couverture intervalle</th>
                  <th>Poids dans le métamodèle</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(models).map(([name, m]) => (
                  <tr key={name} className={name === "meta" ? "row-highlight" : undefined}>
                    <td>{MODEL_LABELS[name] ?? name}</td>
                    <td>{formatNumber(m.mae, 5)}</td>
                    <td>{formatNumber(m.rmse, 5)}</td>
                    <td>{m.rmse_vs_naive === null ? "—" : formatNumber(m.rmse_vs_naive, 3)}</td>
                    <td>{formatPct(m.direction_accuracy, 1)}</td>
                    <td>{formatNumber(m.bias, 5)}</td>
                    <td>{m.interval_coverage === undefined ? "—" : formatPct(m.interval_coverage, 0)}</td>
                    <td>{name in weights ? formatPct(weights[name], 0) : name === "meta" ? "—" : ""}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="muted">
            Erreurs en log-rendement à {experiment.config.horizon} jours (0,01 ≈ 1 %). Un RMSE/naïf ≥ 1 signifie que le modèle ne fait pas mieux que « aucun changement ». {experiment.folds.length} plis chronologiques.
          </p>
          <h4>Prédictions hors échantillon vs réalisé</h4>
          <LineChart
            series={[
              { label: "Réalisé", color: "#4b5563", points: experiment.predictions.map((p) => ({ x: new Date(String(p.date)), y: Number(p.actual) })) },
              { label: "Métamodèle", color: "#1d4ed8", points: experiment.predictions.map((p) => ({ x: new Date(String(p.date)), y: Number(p.meta) })) },
            ]}
            referenceLines={[{ y: 0 }]}
            yFormatter={(v) => formatPct(v, 1)}
            height={220}
            ariaLabel="Prédictions hors échantillon"
          />
          <h4>Plis</h4>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>#</th>
                  <th>Entraînement</th>
                  <th>Test</th>
                  <th>n train / test</th>
                  <th>RMSE métamodèle-candidats</th>
                </tr>
              </thead>
              <tbody>
                {experiment.folds.map((f) => (
                  <tr key={f.index}>
                    <td>{f.index + 1}</td>
                    <td>
                      {f.train_start.slice(0, 10)} → {f.train_end.slice(0, 10)}
                    </td>
                    <td>
                      {f.test_start.slice(0, 10)} → {f.test_end.slice(0, 10)}
                    </td>
                    <td>
                      {f.n_train} / {f.n_test}
                    </td>
                    <td className="muted">
                      {Object.entries(f.metrics)
                        .map(([m, v]) => `${MODEL_LABELS[m] ?? m}: ${v.rmse.toFixed(4)}`)
                        .join(" · ")}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {forecast && (
            <>
              <h4>Projection actuelle (expérimentale)</h4>
              <p className="prediction-warning" role="note">
                {forecast.disclaimer}
              </p>
              <div className="stat-grid">
                <div className="stat">
                  <span className="stat-label">Au {formatDateTime(forecast.as_of)}, dernier cours</span>
                  <strong>{formatAmount(forecast.last_close)}</strong>
                </div>
                <div className="stat">
                  <span className="stat-label">Log-rendement attendu à {forecast.horizon} j</span>
                  <strong>{formatPct(forecast.expected_log_return)}</strong>
                </div>
                <div className="stat">
                  <span className="stat-label">Intervalle à {formatPct(forecast.interval_confidence, 0)}</span>
                  <strong>
                    {formatPct(forecast.interval_log_return[0])} … {formatPct(forecast.interval_log_return[1])}
                  </strong>
                </div>
                <div className="stat">
                  <span className="stat-label">Prix impliqué (médian, fourchette)</span>
                  <strong>
                    {formatAmount(forecast.implied_price)} ({formatAmount(forecast.implied_price_interval[0])} – {formatAmount(forecast.implied_price_interval[1])})
                  </strong>
                </div>
              </div>
              <p className="muted">Par modèle : {Object.entries(forecast.by_model).map(([m, v]) => `${MODEL_LABELS[m] ?? m} ${formatPct(v)}`).join(" · ")}</p>
            </>
          )}
        </>
      )}
      <div className="toolbar">
        <button type="button" className="export-button" onClick={onRerun} disabled={experiment.status === "running"}>
          Ré-entraîner (reproductible)
        </button>
      </div>
    </section>
  );
}
