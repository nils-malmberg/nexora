from app.news.pipeline.summarize import summarize


def test_summarize_returns_none_for_missing_excerpt():
    assert summarize("Title", None) is None
    assert summarize("Title", "   ") is None


def test_summarize_returns_short_excerpt_unchanged():
    excerpt = "Un court extrait."
    assert summarize("Titre", excerpt) == excerpt


def test_summarize_never_exceeds_max_length():
    long_excerpt = " ".join(
        [f"Phrase numero {i} avec du texte supplementaire pour allonger le tout." for i in range(20)]
    )
    result = summarize("Titre pertinent", long_excerpt)
    assert result is not None
    assert len(result) <= 400


def test_summarize_only_uses_words_from_the_source():
    excerpt = (
        "La societe Demo publie ses resultats annuels. Le chiffre d'affaires augmente de dix pourcent. "
        "La direction se dit confiante pour l'annee prochaine. Un nouvel actionnaire est entre au capital."
    )
    result = summarize("resultats annuels Demo", excerpt)
    assert result is not None
    source_words = set(excerpt.lower().replace(".", "").split())
    result_words = set(result.lower().replace(".", "").split())
    assert result_words.issubset(source_words | {""})
