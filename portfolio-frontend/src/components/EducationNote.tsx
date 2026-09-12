import { useEffect, useState } from "react";
import { getEducationArticle } from "../api/client";
import type { EducationArticle } from "../types";

/** specs/UX_SPEC.md: "Infobulles et panneaux 'qu'est-ce que cela mesure ?',
 * 'limites', 'méthode'". Fetched lazily per slug, fails silently (no article
 * shown) rather than breaking the metric it accompanies. */
export function EducationNote({ slug }: { slug: string }) {
  const [article, setArticle] = useState<EducationArticle | null>(null);

  useEffect(() => {
    let cancelled = false;
    getEducationArticle(slug)
      .then((a) => {
        if (!cancelled) setArticle(a);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [slug]);

  if (!article) return null;

  return (
    <details className="details-toggle education-note">
      <summary>Qu'est-ce que cela mesure ?</summary>
      <dl className="details-grid">
        <dt>Mesure</dt>
        <dd>{article.what_it_measures}</dd>
        <dt>Méthode</dt>
        <dd>{article.method}</dd>
        <dt>Limites</dt>
        <dd>{article.limitations}</dd>
      </dl>
    </details>
  );
}
