import { useEffect, useState } from "react";
import { errorMessage, getEducationArticle, listEducation, listEducationCategories } from "../api/client";
import { href } from "../router";
import type { EducationArticle, EducationSummary } from "../types";

/** The help centre: every measure and method used in the app, explained
 * (what it measures, how it's computed, its limits, the theory behind it),
 * searchable, cross-linked. Editorial, neutral, never prescriptive. */
export function HelpPage({ slug }: { slug?: string }) {
  const [articles, setArticles] = useState<EducationSummary[]>([]);
  const [categories, setCategories] = useState<{ key: string; label: string }[]>([]);
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("");
  const [article, setArticle] = useState<EducationArticle | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listEducationCategories().then(setCategories).catch(() => setCategories([]));
  }, []);

  useEffect(() => {
    let cancelled = false;
    listEducation({ q: query || undefined, category: category || undefined })
      .then((list) => !cancelled && setArticles(list))
      .catch((err: unknown) => !cancelled && setError(errorMessage(err)));
    return () => {
      cancelled = true;
    };
  }, [query, category]);

  useEffect(() => {
    if (!slug) {
      setArticle(null);
      return;
    }
    let cancelled = false;
    getEducationArticle(slug)
      .then((a) => !cancelled && setArticle(a))
      .catch((err: unknown) => !cancelled && setError(errorMessage(err)));
    return () => {
      cancelled = true;
    };
  }, [slug]);

  const byCategory = new Map<string, EducationSummary[]>();
  for (const a of articles) byCategory.set(a.category, [...(byCategory.get(a.category) ?? []), a]);
  const labelOf = (key: string) => categories.find((c) => c.key === key)?.label ?? key;

  return (
    <section aria-label="Aide" className="help-layout">
      <aside className="help-sidebar">
        <h2>Aide</h2>
        <p className="muted">La théorie derrière chaque chiffre : définitions, formules, méthodes et limites.</p>
        <input type="search" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Rechercher (ex. Sharpe, VaR, FIFO)" aria-label="Rechercher dans l'aide" className="search-input" />
        <select value={category} onChange={(e) => setCategory(e.target.value)} aria-label="Catégorie">
          <option value="">Toutes les catégories</option>
          {categories.map((c) => (
            <option key={c.key} value={c.key}>
              {c.label}
            </option>
          ))}
        </select>
        {error && <p className="error-state">{error}</p>}
        {[...byCategory.entries()].map(([key, list]) => (
          <div key={key}>
            <h4>{labelOf(key)}</h4>
            <ul className="help-list">
              {list.map((a) => (
                <li key={a.slug}>
                  <a href={href("help", a.slug)} aria-current={a.slug === slug ? "page" : undefined}>
                    {a.title}
                  </a>
                </li>
              ))}
            </ul>
          </div>
        ))}
        {articles.length === 0 && !error && <p className="muted">Aucun article ne correspond.</p>}
      </aside>
      <article className="help-article">
        {article ? (
          <>
            <p className="breadcrumb">
              <a href={href("help")}>Aide</a> › {labelOf(article.category)}
            </p>
            <h2>{article.title}</h2>
            <p className="lead">{article.summary}</p>
            <h3>Ce que cela mesure</h3>
            <p>{article.what_it_measures}</p>
            <h3>Méthode</h3>
            <p>{article.method}</p>
            {article.sections.map((s) => (
              <div key={s.heading}>
                <h3>{s.heading}</h3>
                <p>{s.body}</p>
              </div>
            ))}
            <h3>Limites</h3>
            <p>{article.limitations}</p>
            {article.related.length > 0 && (
              <p className="muted">
                Voir aussi :{" "}
                {article.related.map((r, i) => (
                  <span key={r}>
                    {i > 0 && " · "}
                    <a href={href("help", r)}>{r}</a>
                  </span>
                ))}
              </p>
            )}
            <p className="muted">Contenu éditorial versionné ({article.version}). Aucune recommandation personnalisée : ces explications décrivent des méthodes, pas des décisions.</p>
          </>
        ) : (
          <>
            <h2>Bienvenue dans l'aide</h2>
            <p>
              Chaque graphique et chaque indicateur de NeXora renvoie ici. Choisissez un article dans la liste, ou recherchez un terme. Les articles sont organisés par thème : bases de la valorisation, performance et risque, théorie du portefeuille, analyse technique, prédiction et validation, données et sources.
            </p>
            <p className="muted">Ton neutre, pas de « achetez » ni de « vendez » : NeXora est un outil d'information et d'organisation, pas un service de conseil.</p>
          </>
        )}
      </article>
    </section>
  );
}
