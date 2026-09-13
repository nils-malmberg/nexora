import { useEffect, useState } from "react";
import { getEducationArticle } from "../api/client";
import { href } from "../router";
import type { EducationArticle } from "../types";

/** "Qu'est-ce que cela mesure ?" panel next to a figure, backed by the
 * versioned educational content (never a recommendation), with a link to
 * the full article in the help section. */
export function EducationNote({ slug }: { slug: string }) {
  const [article, setArticle] = useState<EducationArticle | null>(null);

  useEffect(() => {
    let cancelled = false;
    getEducationArticle(slug)
      .then((a) => {
        if (!cancelled) setArticle(a);
      })
      .catch(() => {
        // the figure stays usable without its note
      });
    return () => {
      cancelled = true;
    };
  }, [slug]);

  if (!article) return null;
  return (
    <details className="education-note">
      <summary>Qu'est-ce que cela mesure ? — {article.title}</summary>
      <p>{article.what_it_measures}</p>
      <p>
        <strong>Méthode.</strong> {article.method}
      </p>
      <p>
        <strong>Limites.</strong> {article.limitations}
      </p>
      <p className="muted">
        <a href={href("help", slug)}>Lire l'article complet</a> · version {article.version}
      </p>
    </details>
  );
}
