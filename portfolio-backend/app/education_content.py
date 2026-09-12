"""Static, versioned educational content — specs/UX_SPEC.md: "Infobulles et
panneaux 'qu'est-ce que cela mesure ?', 'limites', 'méthode' ; ton neutre,
liens vers sources validées par l'équipe. Interdit : 'achetez', 'vendez',
recommandations adaptées à une personne."

Kept as plain Python data, not a database table: this is editorial content
authored by the team, not user data, and doesn't need a migration to change.
"""

from __future__ import annotations

ARTICLES: dict[str, dict[str, str]] = {
    "valorisation": {
        "title": "Qu'est-ce que la valorisation ?",
        "what_it_measures": (
            "La valeur totale d'un portefeuille à un instant donné : trésorerie plus valeur de "
            "marché de chaque position (quantité × dernier prix connu)."
        ),
        "method": (
            "Recalculée à chaque lecture à partir du solde de trésorerie et du dernier prix connu "
            "par instrument (saisie manuelle ou import CSV)."
        ),
        "limitations": (
            "Un prix manquant n'est jamais estimé : la position concernée est exclue du total et "
            "signalée. Aucune conversion de change n'est appliquée : une devise différente de celle "
            "du portefeuille est exclue du total et listée séparément."
        ),
        "version": "2026-09-13.1",
    },
    "allocation": {
        "title": "Qu'est-ce que la répartition (allocation) ?",
        "what_it_measures": (
            "La part de la valeur totale du portefeuille attribuable à chaque classe d'actif, " "instrument ou devise."
        ),
        "method": (
            "Calculée sur la valorisation courante des positions, dans la devise de référence du "
            "portefeuille uniquement."
        ),
        "limitations": (
            "Les positions dans une autre devise ou sans prix connu sont exclues du calcul et "
            "listées séparément — la somme des parts affichées peut donc être inférieure à 100 %."
        ),
        "version": "2026-09-13.1",
    },
    "twr-mwr": {
        "title": "TWR et MWR : deux façons de mesurer la performance",
        "what_it_measures": (
            "Le TWR (rendement pondéré dans le temps) mesure la performance de la stratégie, "
            "indépendamment des dépôts/retraits. Le MWR (rendement pondéré par l'argent, calculé "
            "par taux de rendement interne) mesure la performance réellement vécue par "
            "l'investisseur, sensible au moment de ses versements."
        ),
        "method": (
            "TWR : rendements chaînés entre chaque dépôt/retrait externe. MWR : taux d'actualisation "
            "qui annule la valeur actuelle nette des flux (dépôts, retraits, valeur de départ et "
            "d'arrivée)."
        ),
        "limitations": (
            "Les dividendes et coupons restent en trésorerie interne et ne sont pas traités comme "
            "des flux externes. Aucune comparaison à un indice de référence n'est fournie. Ces "
            "indicateurs décrivent le passé et ne constituent ni une prévision ni une "
            "recommandation."
        ),
        "version": "2026-09-13.1",
    },
    "volatilite-drawdown": {
        "title": "Volatilité et repli maximum (drawdown)",
        "what_it_measures": (
            "La volatilité mesure l'amplitude des variations de valeur du portefeuille. Le repli "
            "maximum est la plus forte baisse observée entre un sommet et un creux sur la période."
        ),
        "method": (
            "Écart-type des rendements entre points de valorisation successifs, annualisé par "
            "l'intervalle moyen observé (l'échantillonnage n'est pas forcément quotidien)."
        ),
        "limitations": (
            "Un échantillonnage irrégulier ou peu fourni rend l'annualisation approximative. Ces "
            "mesures décrivent le passé ; elles ne prédisent pas la volatilité future."
        ),
        "version": "2026-09-13.1",
    },
    "indicateurs-techniques": {
        "title": "Indicateurs techniques (SMA, EMA, RSI, MACD)",
        "what_it_measures": (
            "Des transformations mathématiques du prix d'un instrument dans le temps : moyennes "
            "mobiles (SMA/EMA), indice de force relative (RSI), convergence/divergence de moyennes "
            "mobiles (MACD)."
        ),
        "method": (
            "Formules standard, calculées sur les prix connus de l'instrument (saisie manuelle ou "
            "import CSV) ; les paramètres (fenêtres) sont visibles et modifiables."
        ),
        "limitations": (
            "Ne constituent ni un signal d'achat/vente, ni une recommandation. Nécessitent un "
            "historique de prix suffisant : une valeur manquante avant que la fenêtre ne soit "
            "remplie est normale, jamais comblée artificiellement."
        ),
        "version": "2026-09-13.1",
    },
}
