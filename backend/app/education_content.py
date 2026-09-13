"""Static, versioned educational content — the "fichier d'aide" behind every
figure the dashboard shows (specs/UX_SPEC.md: panneaux « qu'est-ce que cela
mesure ? », « méthode », « limites » ; ton neutre ; jamais « achetez » /
« vendez » ni de recommandation adaptée à une personne).

Plain Python data, not a database table: editorial content authored by the
team, identical for every user, versioned with the code. Formulas are written
in plain text so they render everywhere.
"""

from __future__ import annotations

VERSION = "2026-09-13.3"

CATEGORIES = {
    "bases": "Bases de la valorisation",
    "performance": "Performance et risque",
    "theorie": "Théorie du portefeuille",
    "technique": "Analyse technique",
    "prediction": "Prédiction et validation",
    "donnees": "Données et sources",
    "suivi": "Suivi, revenus et fiscalité",
}


def _a(title, category, summary, what, method, limitations, sections, related=()):
    return {
        "title": title,
        "category": category,
        "summary": summary,
        "what_it_measures": what,
        "method": method,
        "limitations": limitations,
        "sections": [{"heading": h, "body": b} for h, b in sections],
        "related": list(related),
        "version": VERSION,
    }


ARTICLES: dict[str, dict] = {
    # ------------------------------------------------------------------ bases
    "valorisation": _a(
        "Valorisation d'un portefeuille",
        "bases",
        "Comment la valeur totale est calculée à partir des positions, des prix et de la trésorerie.",
        "La valeur totale d'un portefeuille à un instant donné : trésorerie plus valeur de marché de chaque "
        "position (quantité détenue × dernier prix applicable), exprimée dans la devise de référence.",
        "Les transactions sont rejouées dans l'ordre chronologique (méthode FIFO pour les lots) pour obtenir la "
        "quantité et le coût de revient de chaque position. Le prix applicable est l'observation la plus récente "
        "connue (cotation du fournisseur, clôture quotidienne, saisie manuelle ou valorisation privée). Les "
        "montants dans une autre devise sont convertis avec le taux de référence daté le plus récent.",
        "Un prix manquant n'est jamais estimé : la position est exclue du total et signalée. Une devise sans taux "
        "connu reste non convertie et listée à part. Les cotations peuvent être différées ; l'âge de chaque donnée "
        "est affiché. Une valorisation privée est une estimation, marquée comme telle.",
        [
            (
                "Formule",
                "Valeur totale = Σ (quantité_i × prix_i × taux_i) + Σ trésorerie_devise × taux_devise. "
                "Le taux vaut 1 pour la devise de référence.",
            ),
            (
                "Coût de revient et méthode FIFO",
                "Chaque achat ouvre un lot (quantité, coût unitaire frais inclus). Une vente consomme les lots les "
                "plus anciens d'abord (First In, First Out). Le coût moyen affiché est la moyenne pondérée des lots "
                "restants. La plus-value latente = valeur de marché − coût de revient des lots restants (même devise).",
            ),
            (
                "Splits et dividendes",
                "Un split multiplie les quantités et divise les coûts unitaires par le ratio, sans effet sur la "
                "valeur. Un dividende ou un coupon est un mouvement de trésorerie interne : il augmente le cash sans "
                "être un apport externe (important pour la performance TWR/MWR).",
            ),
            (
                "Immuabilité des transactions",
                "Une transaction validée n'est jamais modifiée ni supprimée : une erreur se corrige par une "
                "annulation auditée qui l'exclut des calculs. Cela garantit une piste d'audit complète.",
            ),
        ],
        ("allocation", "taux-de-change", "fraicheur-des-donnees"),
    ),
    "allocation": _a(
        "Allocation et concentration",
        "bases",
        "Répartition de la valeur investie par classe d'actif, instrument et devise.",
        "La part de chaque classe d'actif, de chaque instrument et de chaque devise dans la valeur de marché des "
        "positions (hors trésorerie, qui est affichée séparément).",
        "Pour chaque position valorisée et convertie dans la devise de référence : part = valeur de la position ÷ "
        "valeur totale des positions. Les parts sont exprimées en pourcentage et somment à 100 % sur les positions "
        "convertibles.",
        "Une position sans prix ou sans taux de change est exclue du dénominateur et signalée. L'allocation est "
        "une photographie : elle change avec les prix, pas seulement avec vos transactions. Les catégories sont "
        "celles déclarées à la création de l'instrument.",
        [
            (
                "Concentration",
                "Une forte part sur un seul instrument, une seule devise ou un seul secteur signifie que la valeur "
                "dépend fortement d'un petit nombre de facteurs. L'indice de Herfindahl (Σ parts²) résume cette "
                "concentration : 1 = tout sur une ligne, 1/N = N lignes égales.",
            ),
            (
                "Pourquoi séparer la trésorerie",
                "La trésorerie n'est pas un placement à risque de marché ; la mêler aux positions masquerait la "
                "structure réelle de la partie investie. Elle apparaît dans sa propre carte du tableau de bord.",
            ),
        ],
        ("correlation-diversification", "markowitz"),
    ),
    "taux-de-change": _a(
        "Devises et taux de change",
        "bases",
        "Conversion des positions et de la trésorerie étrangères dans la devise de référence.",
        "La valeur, dans la devise de référence, d'un montant libellé dans une autre devise, au taux de référence "
        "daté le plus récent disponible.",
        "Montant converti = montant × taux(base→devise de référence). Les taux proviennent d'une source de "
        "référence (taux quotidiens de la Banque centrale européenne via Frankfurter) et sont stockés avec leur "
        "date et leur provenance ; l'historique utilise le taux du jour concerné (ou le dernier jour ouvré "
        "précédent).",
        "Un taux de référence est fixé une fois par jour ouvré : ce n'est pas le taux auquel vous pourriez "
        "réellement changer de l'argent (spread, frais). Sans taux connu, le montant reste non converti et est "
        "listé séparément — jamais converti à un taux inventé.",
        [
            (
                "Effet de change sur la performance",
                "Un actif en dollars détenu par un portefeuille en euros gagne ou perd aussi avec EUR/USD. La "
                "performance affichée dans la devise de référence inclut cet effet ; celle de l'instrument dans sa "
                "propre devise l'exclut.",
            ),
        ],
        ("valorisation",),
    ),
    "fraicheur-des-donnees": _a(
        "Fraîcheur, provenance et licences des données",
        "donnees",
        "D'où viennent les cotations, à quel point elles sont récentes et ce que cela implique.",
        "L'origine (source), l'horodatage et le statut (à jour, différé, estimé, manquant) de chaque prix affiché.",
        "Chaque donnée porte sa source et sa date. Les cotations sont rafraîchies au plus toutes les 15 minutes "
        "pour les instruments suivis (et à la demande, dans la limite des quotas) ; entre deux rafraîchissements "
        "la dernière valeur connue est servie avec son âge. Les fournisseurs sont interchangeables et configurés "
        "par l'administrateur ; en cas de panne, la dernière donnée connue reste affichée comme telle.",
        "Les fournisseurs gratuits publient des données souvent différées (15 minutes ou plus selon la place), "
        "destinées à un usage personnel, non redistribuables, et peuvent changer sans préavis. Aucune garantie de "
        "temps réel. Les clés d'API restent côté serveur et ne sont jamais exposées.",
        [
            (
                "Statuts affichés",
                "« À jour » : observation plus récente que le seuil configuré. « Différé » : plus ancienne. "
                "« Estimé » : valorisation privée ou estimation. « Manquant » : aucune observation — la position "
                "est exclue du total.",
            ),
            (
                "Pourquoi limiter les requêtes",
                "Chaque fournisseur impose des quotas ; les dépasser conduit à un blocage de l'adresse IP. "
                "L'application applique un budget local par fournisseur, un cache et un disjoncteur qui désactive "
                "une source qui échoue de façon répétée.",
            ),
        ],
        ("valorisation",),
    ),
    # ------------------------------------------------------------ performance
    "twr-mwr": _a(
        "Performance : TWR et MWR (TRI)",
        "performance",
        "Deux façons complémentaires de mesurer un rendement quand il y a des apports et des retraits.",
        "Le rendement du portefeuille sur une période. Le TWR (Time-Weighted Return) mesure la performance des "
        "placements indépendamment du moment des apports/retraits ; le MWR (Money-Weighted Return, taux de "
        "rendement interne) mesure le rendement effectivement obtenu par l'investisseur compte tenu de la "
        "chronologie de ses flux.",
        "TWR : la période est découpée à chaque flux externe (dépôt, retrait) ; le rendement de chaque "
        "sous-période r_k = V_fin / V_début − 1 est calculé juste avant le flux, puis chaîné : "
        "TWR = Π (1 + r_k) − 1. MWR : taux r tel que la valeur actuelle nette des flux soit nulle : "
        "Σ flux_t / (1 + r)^(t/365) + V_fin / (1 + r)^(T/365) − V_début = 0 (XIRR, résolu numériquement).",
        "Sensible aux prix manquants aux dates des flux. Sur une période courte ou avec peu de points, les deux "
        "mesures sont fragiles. Le MWR peut n'avoir aucune solution ou plusieurs quand les flux changent de signe "
        "plusieurs fois. Aucune des deux ne dit si la performance est « bonne » : cela dépend du risque pris et "
        "d'une comparaison de même couverture.",
        [
            (
                "Quand utiliser l'une ou l'autre",
                "TWR pour comparer des gestions ou un indice (le gérant ne contrôle pas les apports). MWR pour "
                "répondre à « combien ai-je gagné par an sur mon argent ? ». Les dividendes et coupons sont des "
                "flux internes : ils ne découpent pas la période.",
            ),
            (
                "Annualisation",
                "Un rendement de période se ramène à un taux annuel par (1 + R)^(365 / jours) − 1. Sur moins d'un "
                "an, annualiser extrapole et exagère : l'application l'indique.",
            ),
        ],
        ("valorisation", "sharpe-sortino-calmar"),
    ),
    "volatilite-drawdown": _a(
        "Volatilité et repli maximum",
        "performance",
        "Les deux mesures de risque descriptif les plus courantes : dispersion des rendements et pire perte "
        "depuis un sommet.",
        "La volatilité mesure l'amplitude des variations de valeur (écart-type des rendements, annualisé). Le repli "
        "maximum (max drawdown) mesure la plus forte baisse entre un sommet et le creux qui l'a suivi sur la période.",
        "Volatilité = écart-type des rendements simples de période × √(nombre de périodes par an) — 252 jours de "
        "cotation pour une série quotidienne. Drawdown_t = V_t / max(V_0..V_t) − 1 ; le repli maximum est le "
        "minimum de cette série.",
        "La volatilité traite symétriquement hausses et baisses et suppose une dispersion stable, ce que les "
        "marchés contredisent (regroupements de volatilité, queues épaisses). Le repli maximum dépend fortement de "
        "la période observée et d'un seul épisode. Ces mesures décrivent le passé ; elles ne sont pas des "
        "prévisions ni des recommandations.",
        [
            (
                "Lire une volatilité",
                "Une volatilité annualisée de 20 % signifie qu'environ deux tiers des années, sous hypothèse "
                "normale, le rendement s'écarte de sa moyenne de moins de 20 points — hypothèse commode mais "
                "optimiste pour les extrêmes.",
            ),
            (
                "Durée de récupération",
                "Le temps entre un sommet et le retour au même niveau (« underwater period ») complète le repli "
                "maximum : deux pertes de 30 % n'ont pas la même gravité si l'une met six mois et l'autre six ans "
                "à se résorber.",
            ),
        ],
        ("sharpe-sortino-calmar", "var-cvar"),
    ),
    "sharpe-sortino-calmar": _a(
        "Ratios rendement / risque : Sharpe, Sortino, Calmar",
        "performance",
        "Mettre le rendement en regard du risque pris, avec trois définitions du risque.",
        "Le rendement excédentaire (au-delà d'un taux sans risque) obtenu par unité de risque : volatilité totale "
        "(Sharpe), volatilité des seules baisses (Sortino) ou repli maximum (Calmar).",
        "Sharpe = (R_annualisé − r_f) / σ_annualisée. Sortino = (R_annualisé − r_f) / σ_baisse, où σ_baisse est "
        "l'écart-type des rendements excédentaires négatifs uniquement (semi-déviation). Calmar = taux de "
        "croissance annuel composé / |repli maximum|. Le taux sans risque r_f est un paramètre affiché.",
        "Un ratio n'a de sens que comparé à un autre calculé sur la même période, la même fréquence et le même "
        "taux sans risque. Il est instable sur des périodes courtes, sensible aux valeurs extrêmes et repose sur "
        "des estimations passées. Un Sharpe élevé n'est pas une garantie future.",
        [
            (
                "Interprétation courante",
                "Sharpe autour de 0 : le placement n'a pas rémunéré le risque au-delà du sans-risque ; autour de 1 : "
                "un rendement excédentaire égal à la volatilité. Ces repères sont des conventions, pas des seuils "
                "de décision.",
            ),
            (
                "Pourquoi Sortino",
                "La volatilité pénalise aussi les fortes hausses. Sortino ne compte que les baisses par rapport au "
                "seuil : plus proche de l'intuition « le risque, c'est perdre ».",
            ),
        ],
        ("volatilite-drawdown", "twr-mwr", "capm-beta"),
    ),
    "var-cvar": _a(
        "Value-at-Risk (VaR) et Expected Shortfall (CVaR)",
        "performance",
        "Quantifier une perte « rare » à un niveau de confiance donné, et la perte moyenne au-delà.",
        "La VaR à 95 % sur 1 jour est la perte que l'on ne dépasse pas 95 jours sur 100 (selon le modèle). La CVaR "
        "(Expected Shortfall) est la perte moyenne les 5 % de jours restants — elle décrit la gravité de la queue, "
        "pas seulement son seuil.",
        "Historique : quantile empirique des rendements passés ; CVaR = moyenne des rendements sous ce quantile. "
        "Gaussienne : VaR = −(μ + z_α σ), avec z_α le quantile de la loi normale. Cornish-Fisher : z_α corrigé par "
        "l'asymétrie et l'aplatissement observés. Horizon de h jours : multiplication par √h. Résultat exprimé en "
        "fraction de la valeur courante.",
        "La VaR historique suppose que le passé récent est représentatif ; la gaussienne sous-estime les extrêmes ; "
        "la mise à l'échelle en √h suppose des rendements indépendants. Aucune VaR ne dit combien on peut perdre "
        "au pire — seulement un seuil à une fréquence donnée. À manier comme un ordre de grandeur.",
        [
            (
                "Exemple de lecture",
                "VaR 95 % 1 jour = 2,1 % et CVaR = 3,4 % : environ un jour sur vingt la perte dépasse 2,1 %, et ces "
                "jours-là elle vaut 3,4 % en moyenne.",
            ),
            (
                "Pourquoi la CVaR est préférée en régulation",
                "La VaR n'est pas sous-additive (diversifier peut l'augmenter) ; l'Expected Shortfall est une mesure "
                "de risque cohérente qui respecte la diversification.",
            ),
        ],
        ("volatilite-drawdown", "monte-carlo"),
    ),
    "capm-beta": _a(
        "MEDAF (CAPM) : bêta et alpha",
        "theorie",
        "Décomposer le rendement d'un actif en exposition au marché (bêta) et reste inexpliqué (alpha).",
        "Le bêta mesure la sensibilité du rendement d'un actif (ou portefeuille) à celui d'un indice de référence ; "
        "l'alpha est le rendement excédentaire moyen non expliqué par cette exposition. Le R² indique la part de "
        "variance expliquée par le benchmark.",
        "Régression linéaire (moindres carrés) des rendements excédentaires de l'actif sur ceux du benchmark : "
        "r_a − r_f = α + β (r_b − r_f) + ε. β = Cov(r_a, r_b) / Var(r_b). L'alpha est annualisé. La tracking error "
        "est l'écart-type de (r_a − r_b) annualisé ; le ratio d'information = excès moyen / tracking error.",
        "Le MEDAF suppose un marché efficient, un seul facteur et des estimations stables ; empiriquement le bêta "
        "varie dans le temps et d'autres facteurs (taille, valeur, momentum) comptent. Un alpha positif passé peut "
        "être du hasard, une prime de risque non modélisée ou une erreur de benchmark.",
        [
            (
                "Lire un bêta",
                "β = 1,2 : quand le benchmark varie de 1 %, l'actif varie en moyenne de 1,2 % dans le même sens. "
                "β < 0 : mouvement en sens inverse en moyenne. β proche de 0 avec un faible R² : peu de lien.",
            ),
            (
                "Choisir un benchmark",
                "Un indice de même univers (place, devise, classe d'actif). Comparer un fonds monde à un indice "
                "sectoriel donne un bêta sans signification.",
            ),
        ],
        ("sharpe-sortino-calmar", "markowitz", "efficience-des-marches"),
    ),
    "markowitz": _a(
        "Théorie moderne du portefeuille (Markowitz)",
        "theorie",
        "La frontière efficiente : pour un niveau de risque, la combinaison d'actifs qui maximise le rendement espéré.",
        "Pour un ensemble d'actifs, l'ensemble des portefeuilles « efficients » : ceux qu'aucun autre ne domine à "
        "la fois en rendement espéré et en variance. Trois points remarquables : variance minimale, ratio de Sharpe "
        "maximal (portefeuille tangent) et équipondération, comparés au portefeuille actuel.",
        "Rendements espérés μ et matrice de covariance Σ estimés sur les rendements quotidiens passés puis "
        "annualisés. Pour chaque rendement cible, minimisation de w'Σw sous contraintes Σw = 1 et w ≥ 0 (pas de vente "
        "à découvert), par optimisation quadratique (SLSQP). Rendement du portefeuille = w'μ, volatilité = √(w'Σw).",
        "Les résultats sont extrêmement sensibles aux estimations de μ et Σ, elles-mêmes bruitées : l'optimiseur "
        "« maximise l'erreur d'estimation » (poids extrêmes sur les actifs ayant eu de la chance). Coûts, "
        "fiscalité, liquidité et contraintes personnelles sont ignorés. La frontière décrit le passé de cet "
        "échantillon ; ce n'est pas une allocation recommandée.",
        [
            (
                "Diversification",
                "La variance d'un portefeuille n'est pas la moyenne des variances : les termes de covariance "
                "(corrélations) la réduisent. Deux actifs de même volatilité et corrélés à 0 donnent, à parts "
                "égales, une volatilité divisée par √2.",
            ),
            (
                "Portefeuille tangent et droite de marché des capitaux",
                "Avec un actif sans risque, tout investisseur combinerait, en théorie, ce dernier avec le "
                "portefeuille de Sharpe maximal. C'est la justification théorique du MEDAF.",
            ),
            (
                "Extensions",
                "Black-Litterman (incorporer des vues), parité de risque (égaliser les contributions au risque), "
                "contraintes de poids et d'exposition, rééchantillonnage pour stabiliser. Non implémentées ici.",
            ),
        ],
        ("correlation-diversification", "capm-beta", "allocation"),
    ),
    "correlation-diversification": _a(
        "Corrélation et diversification",
        "theorie",
        "Mesurer à quel point deux actifs bougent ensemble et ce que cela change pour le risque global.",
        "Le coefficient de corrélation de Pearson entre les rendements quotidiens de deux actifs, entre −1 (opposés) "
        "et +1 (identiques). La matrice de corrélation couvre toutes les paires des positions du portefeuille.",
        "ρ = Cov(r_a, r_b) / (σ_a σ_b), calculée sur les seules dates communes aux deux séries (aucune valeur n'est "
        "interpolée). Un minimum de 30 observations communes est exigé.",
        "Les corrélations sont instables et tendent à augmenter dans les crises — précisément quand on voudrait "
        "qu'elles protègent. Une corrélation linéaire ne capture pas les dépendances extrêmes. Corrélation n'est "
        "pas causalité.",
        [
            (
                "Effet sur la volatilité du portefeuille",
                "σ_p² = Σ_i Σ_j w_i w_j σ_i σ_j ρ_ij. Plus les ρ_ij sont faibles, plus la volatilité totale est "
                "inférieure à la moyenne pondérée des volatilités individuelles.",
            ),
        ],
        ("markowitz", "allocation"),
    ),
    "monte-carlo": _a(
        "Simulation de Monte Carlo (mouvement brownien géométrique)",
        "theorie",
        "Générer de nombreuses trajectoires aléatoires cohérentes avec la volatilité passée pour visualiser "
        "la dispersion.",
        "Une distribution de valeurs futures possibles sous une hypothèse de processus donnée, résumée par des "
        "percentiles (5, 25, 50, 75, 95) à chaque horizon et par la probabilité d'être sous la valeur de départ.",
        "Rendements logarithmiques quotidiens : dérive μ et volatilité σ estimées sur l'historique. Chaque "
        "trajectoire suit S_{t+1} = S_t × exp((μ − σ²/2) + σ ε_t) avec ε_t ~ N(0,1) indépendants. N simulations "
        "(graine fixée : résultat reproductible), percentiles calculés par date.",
        "Le modèle suppose des rendements normaux, indépendants et une volatilité constante — les marchés "
        "présentent des queues épaisses, des sauts et une volatilité variable. La dérive estimée sur quelques "
        "années est très incertaine et pèse énormément sur les percentiles lointains. C'est une illustration de "
        "l'incertitude, jamais une prévision.",
        [
            (
                "Pourquoi μ − σ²/2",
                "La moyenne d'un rendement logarithmique est inférieure à celle du rendement simple : c'est la "
                "correction d'Itô. Sans elle, la médiane des trajectoires serait biaisée vers le haut.",
            ),
            (
                "Ce qu'on peut en tirer",
                "Un ordre de grandeur de la fourchette plausible et de l'asymétrie (la distribution log-normale est "
                "étirée vers le haut, bornée à zéro vers le bas), pas une valeur cible.",
            ),
        ],
        ("var-cvar", "volatilite-drawdown", "efficience-des-marches"),
    ),
    "efficience-des-marches": _a(
        "Efficience des marchés et marche aléatoire",
        "theorie",
        "Pourquoi prévoir les prix est difficile, et ce que cela implique pour l'analyse et la prédiction.",
        "L'hypothèse d'efficience (Fama) : les prix intègrent l'information disponible, si bien que les variations "
        "futures sont essentiellement imprévisibles à partir de cette information (forme faible : les prix passés ; "
        "semi-forte : l'information publique ; forte : toute information).",
        "Ce n'est pas une mesure mais un cadre. Tests classiques : autocorrélation des rendements, tests de "
        "ratio de variance, capacité de stratégies à battre un indice après coûts, sur longue période.",
        "Les marchés ne sont pas parfaitement efficients (anomalies documentées : momentum, effets calendaires, "
        "sur-réactions) mais les écarts sont faibles, instables et souvent absorbés par les coûts. Une régularité "
        "trouvée sur le passé disparaît souvent quand on la teste hors échantillon.",
        [
            (
                "Conséquence pour l'analyse technique et la prédiction",
                "Sous efficience faible, les indicateurs techniques décrivent mais ne prédisent pas ; un modèle doit "
                "au minimum battre le benchmark « aucun changement » hors échantillon, après coûts, pour prétendre "
                "à une valeur informative. C'est le critère utilisé par le module de prédiction.",
            ),
            (
                "Marche aléatoire",
                "Si le log-prix suit une marche aléatoire, la meilleure prévision du prix de demain est celui "
                "d'aujourd'hui (plus une dérive). Le benchmark naïf des expériences implémente exactement cela.",
            ),
        ],
        ("prediction-walk-forward", "indicateurs-techniques", "monte-carlo"),
    ),
    # -------------------------------------------------------------- technique
    "chandeliers": _a(
        "Lire un graphique en chandeliers (OHLC) et le volume",
        "technique",
        "Ce que représentent l'ouverture, le plus haut, le plus bas, la clôture et le volume d'une période.",
        "Pour chaque période (ici une journée) : le premier prix (open), le plus haut, le plus bas et le dernier "
        "(close). Le corps du chandelier va de l'open au close ; les mèches vont jusqu'aux extrêmes. Le volume est "
        "la quantité échangée sur la période.",
        "Les barres proviennent telles quelles du fournisseur ; aucune valeur n'est interpolée. Quand une source ne "
        "publie que des clôtures (certaines données crypto), le graphique affiche une ligne, jamais des chandeliers "
        "reconstitués.",
        "Un chandelier isolé n'a pas de pouvoir prédictif démontré ; les « figures » chartistes sont surtout des "
        "descriptions a posteriori. Les volumes ne sont pas toujours disponibles ni comparables entre places.",
        [
            (
                "Couleurs",
                "Clôture au-dessus de l'ouverture : chandelier haussier (vert) ; en dessous : baissier (rouge). Le "
                "code couleur est doublé par la forme, jamais l'unique signal.",
            ),
            (
                "Fenêtres temporelles",
                "1S/1M/3M/6M/1A/2A/5A/Max : la fenêtre change l'échelle, pas les données. Une tendance visible sur "
                "un mois peut être un détail sur cinq ans.",
            ),
        ],
        ("indicateurs-techniques", "fraicheur-des-donnees"),
    ),
    "indicateurs-techniques": _a(
        "Indicateurs techniques : SMA, EMA, RSI, MACD, Bollinger, ATR, Stochastique, OBV",
        "technique",
        "Définitions, formules et limites des indicateurs calculés sur la série de prix.",
        "Des transformations descriptives de la série de prix (et de volume) : tendance (moyennes mobiles, MACD), "
        "dynamique (RSI, stochastique), dispersion (bandes de Bollinger, ATR) et flux (OBV). Les paramètres "
        "(fenêtres) sont toujours affichés.",
        "SMA_n = moyenne des n dernières clôtures. EMA_n : EMA_t = α C_t + (1 − α) EMA_{t−1}, α = 2/(n+1), "
        "amorcée par la SMA des n premières valeurs. RSI_n = 100 − 100/(1 + gain moyen / perte moyenne) sur n "
        "périodes (lissage de Wilder). MACD = EMA_12 − EMA_26, signal = EMA_9 du MACD, histogramme = différence. "
        "Bollinger : SMA_20 ± k × écart-type_20 (k = 2). ATR_n : moyenne de Wilder du True Range = max(H − L, "
        "|H − C_{t−1}|, |L − C_{t−1}|). Stochastique %K = 100 × (C − min_n L) / (max_n H − min_n L), %D = SMA_3 de %K. "
        "OBV : cumul du volume signé par le sens de la clôture.",
        "Tous ces indicateurs dérivent du passé avec retard ; ils ne prévoient rien par eux-mêmes et donnent de "
        "nombreux faux signaux, surtout en marché sans tendance. Une valeur est absente tant que sa fenêtre n'est "
        "pas remplie (jamais extrapolée). Aucune alerte prescriptive n'est produite.",
        [
            (
                "Moyennes mobiles",
                "Lissent la série pour rendre la tendance lisible ; plus la fenêtre est longue, plus le lissage et "
                "le retard sont importants. L'EMA réagit plus vite que la SMA de même fenêtre.",
            ),
            (
                "RSI et stochastique",
                "Oscillateurs bornés 0–100. Les seuils 30/70 (RSI) ou 20/80 (stochastique) sont des conventions "
                "descriptives de « survente/surachat », pas des signaux d'action.",
            ),
            (
                "Bandes de Bollinger et ATR",
                "Mesurent la dispersion récente : bandes étroites = volatilité faible, larges = forte. L'ATR "
                "exprime la volatilité en unités de prix (utile pour comparer des amplitudes).",
            ),
            (
                "OBV",
                "Additionne le volume les jours de hausse, le soustrait les jours de baisse : une lecture du flux "
                "d'échanges accompagnant les mouvements de prix. Requiert des volumes fiables.",
            ),
        ],
        ("chandeliers", "efficience-des-marches"),
    ),
    # ------------------------------------------------------------- prediction
    "prediction-walk-forward": _a(
        "Prédiction : fuites temporelles, walk-forward et benchmark naïf",
        "prediction",
        "Comment évaluer honnêtement un modèle de prévision de rendements, et pourquoi la plupart échouent.",
        "La capacité d'un modèle à prévoir le rendement à h jours *hors échantillon*, mesurée par l'erreur absolue "
        "moyenne (MAE), la racine de l'erreur quadratique moyenne (RMSE), le taux de bonne direction et la "
        "couverture de ses intervalles — toujours comparée au benchmark « aucun changement ».",
        "Variables construites uniquement avec le passé (rendements retardés, moyennes/écarts-types glissants, "
        "momentum, RSI), cible = log(P_{t+h}/P_t). Validation walk-forward par fenêtre croissante : le modèle est "
        "entraîné sur [0, k) et testé sur [k + h − 1, k'), sans chevauchement, puis la fenêtre avance. Les "
        "normalisations sont ajustées sur l'entraînement seul. Intervalles = quantiles empiriques des résidus hors "
        "échantillon. Jeu de données haché, graine fixée, version du code enregistrée : chaque expérience est "
        "reproductible.",
        "Un modèle qui ne bat pas le naïf (RMSE relatif ≥ 1) n'apporte rien. Même un modèle légèrement meilleur "
        "hors échantillon peut ne pas l'être après coûts, ni demain (dérive). Un taux de bonne direction de 52 % "
        "sur 100 points est indiscernable du hasard. Ce module est expérimental : ses sorties ne sont ni des "
        "objectifs de prix, ni des signaux, ni des conseils.",
        [
            (
                "Fuites temporelles (look-ahead)",
                "Utiliser, même involontairement, une information postérieure à la date de prévision : "
                "normaliser avec la moyenne de toute la série, mélanger aléatoirement train et test, calculer un "
                "indicateur centré, utiliser des données révisées. Chaque fuite gonfle les scores de façon "
                "invisible ; les tests automatisés injectent des sentinelles futures pour la détecter.",
            ),
            (
                "Pourquoi pas de split aléatoire",
                "Les rendements voisins sont dépendants (volatilité regroupée) : un split aléatoire laisse le "
                "modèle « voir » le voisinage de chaque point de test. Seul un découpage chronologique avec un "
                "écart d'au moins h périodes reflète l'usage réel.",
            ),
            (
                "Lire les métriques",
                "MAE/RMSE en unités de log-rendement (0,01 ≈ 1 %). RMSE relatif au naïf < 1 : le modèle réduit "
                "l'erreur. Couverture d'un intervalle à 80 % ≈ 0,80 : intervalle bien calibré ; très inférieure : "
                "trop étroit (sur-confiance).",
            ),
        ],
        ("metamodeles-stacking", "efficience-des-marches"),
    ),
    "metamodeles-stacking": _a(
        "Métamodèles : ensembles et stacking",
        "prediction",
        "Combiner plusieurs modèles de base en un modèle de second niveau, et pourquoi cela aide (parfois).",
        "Un métamodèle apprend à pondérer les prédictions de modèles de base (ici : naïf, moyenne historique, "
        "régression ridge, forêt aléatoire, gradient boosting) pour produire une prédiction combinée.",
        "Stacking : chaque modèle de base produit ses prédictions hors échantillon (walk-forward) ; une régression "
        "à poids positifs sommant à 1 (moindres carrés non négatifs) est ajustée sur ces prédictions pour "
        "expliquer la cible réelle. Les poids obtenus sont affichés. Alternative : moyenne simple. Le métamodèle "
        "n'est jamais ajusté sur des prédictions faites sur des données d'entraînement (sinon il favoriserait le "
        "modèle qui sur-apprend le plus).",
        "Un ensemble réduit la variance, pas le biais : si tous les modèles de base sont mauvais, l'ensemble aussi. "
        "Avec peu de points hors échantillon, les poids sont instables — l'application bascule alors sur la "
        "moyenne simple. Plus de modèles = plus de risque de sur-ajustement du niveau 2.",
        [
            (
                "Compromis biais-variance",
                "Un modèle simple (ridge) est stable mais peut manquer des structures ; un modèle flexible (forêt, "
                "boosting) capture plus mais varie d'un échantillon à l'autre. Les combiner lisse ces défauts.",
            ),
            (
                "Modèles de base implémentés",
                "Naïf : prévoit 0 (aucun changement). Moyenne historique : prévoit la moyenne des rendements "
                "passés. Ridge : régression linéaire pénalisée sur variables standardisées. Forêt aléatoire : "
                "moyenne d'arbres sur des sous-échantillons. Gradient boosting : arbres ajoutés séquentiellement "
                "pour corriger les résidus.",
            ),
            (
                "Gouvernance",
                "Chaque expérience enregistre configuration, empreinte du jeu de données, version du code, "
                "métriques par pli et date d'entraînement ; un interrupteur global permet de désactiver le module. "
                "Aucune décision automatisée n'en découle.",
            ),
        ],
        ("prediction-walk-forward",),
    ),
    # ------------------------------------------------------------------ suivi
    "patrimoine-consolide": _a(
        "Patrimoine consolidé (tous portefeuilles)",
        "suivi",
        "Comment plusieurs portefeuilles, parfois dans des devises différentes, deviennent un seul total.",
        "La somme de la valeur de tous vos portefeuilles (Trade Republic, Revolut, PEA, crypto…) exprimée dans "
        "votre devise de référence, avec la répartition globale par portefeuille, classe d'actifs, instrument et "
        "devise.",
        "Chaque portefeuille est d'abord valorisé dans sa propre devise de base (voir « Valorisation »). Son total "
        "est ensuite converti dans la devise de référence de votre profil au taux de référence daté le plus récent "
        "(source et taux affichés par portefeuille). La trésorerie apparaît comme une classe à part entière dans la "
        "répartition consolidée, puisqu'ici l'objectif est la photographie complète du patrimoine.",
        "Un portefeuille dont la devise n'a pas de taux connu est listé mais exclu du total (jamais converti à un "
        "taux inventé). Les prix manquants sont signalés. Les taux sont ceux de la Banque centrale européenne (ou "
        "de la source configurée), pas ceux que votre courtier vous appliquerait. Les positions identiques dans "
        "deux portefeuilles sont regroupées par symbole.",
        [
            (
                "Pourquoi une devise de référence",
                "Additionner 1 000 € et 1 000 $ n'a pas de sens ; le total consolidé passe par un taux daté et "
                "sourcé. Changer la devise de référence dans Paramètres recalcule tout — rien n'est stocké converti.",
            ),
            (
                "Ce que la répartition permet",
                "Repérer une concentration (un titre, une devise, une classe) qui n'apparaît pas à l'échelle d'un "
                "seul compte. C'est une mesure, pas une cible : il n'existe pas de « bonne » répartition universelle.",
            ),
        ],
        ("valorisation", "taux-de-change", "allocation"),
    ),
    "plus-values-realisees": _a(
        "Plus-values réalisées (FIFO)",
        "suivi",
        "Ce qu'une vente a réellement rapporté ou coûté, une fois rapprochée des achats correspondants.",
        "Pour chaque vente : le produit net (quantité × prix − frais de vente) moins le coût des titres vendus "
        "(prix d'achat + frais d'achat des lots consommés), par vente, par année et par instrument.",
        "Méthode FIFO (premier entré, premier sorti) : une vente consomme d'abord les titres achetés le plus tôt. "
        "C'est exactement le même appariement que celui qui calcule vos positions ouvertes ; un split ajuste la "
        "quantité et le coût unitaire des lots avant la vente. Le résultat est converti dans la devise du "
        "portefeuille au taux daté du jour de la vente.",
        "La règle fiscale applicable peut différer (en France, le prix moyen pondéré d'acquisition — PMP — est la "
        "méthode de référence pour les titres ; d'autres pays utilisent FIFO ou l'identification spécifique). Ce "
        "rapport est un outil de suivi, pas une déclaration : vérifiez avec les documents de votre courtier et, au "
        "besoin, un professionnel. Une vente dans une autre devise que celle des achats est signalée sans P&L. "
        "Les dividendes ne sont pas des plus-values (voir « Revenus du portefeuille »).",
        [
            (
                "Exemple",
                "Achat de 10 titres à 100 € (frais 10 €) puis 10 à 120 €. Vente de 15 titres à 130 € (frais 5 €) : "
                "produit 1 945 € ; coût = 10 × 101 € + 5 × 120 € = 1 610 € ; plus-value réalisée = 335 €.",
            ),
            (
                "FIFO vs PMP",
                "Avec le PMP, le coût des 15 titres serait 15 × 110,5 € = 1 657,5 € et la plus-value 287,5 €. Les "
                "deux méthodes donnent le même total sur la vie complète de la position ; elles répartissent "
                "différemment le résultat entre les ventes successives.",
            ),
            (
                "Durée de détention",
                "Le nombre de jours affiché va du lot le plus ancien consommé jusqu'à la vente ; certaines fiscalités "
                "en dépendent (abattements, distinction court/long terme).",
            ),
        ],
        ("valorisation", "revenus-du-portefeuille"),
    ),
    "revenus-du-portefeuille": _a(
        "Revenus du portefeuille et frais",
        "suivi",
        "Dividendes, coupons, intérêts et frais : ce que le portefeuille verse et ce qu'il coûte, par période.",
        "Les montants encaissés (dividendes d'actions et d'ETF distribuants, coupons d'obligations, intérêts sur "
        "la trésorerie) et les montants décaissés en frais (frais autonomes comme les droits de garde, frais inclus "
        "dans chaque achat ou vente), par année, par mois et par instrument.",
        "Chaque opération est prise au montant net saisi ou importé (les retenues à la source déjà déduites par le "
        "courtier ne sont pas reconstituées). Les montants dans une autre devise sont convertis au taux daté du "
        "jour de l'opération. Les dépôts et retraits ne sont pas des revenus : ce sont des flux externes.",
        "Le rendement sur dividendes (« dividend yield ») n'est pas calculé automatiquement : il dépend du prix de "
        "référence choisi (prix d'achat, cours actuel) et prête à confusion. Un ETF capitalisant ne verse rien : "
        "sa performance est dans son cours. La fiscalité (prélèvement forfaitaire, crédit d'impôt sur retenue à la "
        "source étrangère) n'est pas modélisée.",
        [
            (
                "Lecture",
                "La vue par mois montre la saisonnalité (beaucoup de dividendes européens tombent au printemps) ; la "
                "vue par instrument montre d'où viennent les revenus. Frais nets = ce que coûte réellement "
                "l'activité de l'année.",
            ),
            (
                "Revenus et performance",
                "Le TWR/MWR inclut déjà les revenus (ils augmentent la trésorerie) ; ce rapport les isole pour les "
                "lire à part, il ne s'y ajoute pas.",
            ),
        ],
        ("plus-values-realisees", "twr-mwr"),
    ),
    "alertes-informatives": _a(
        "Alertes informatives",
        "suivi",
        "Être prévenu quand un seuil est franchi — et pourquoi l'application s'arrête là.",
        "Une alerte compare le dernier cours connu d'un instrument à un seuil que vous fixez : cours au-dessus ou en "
        "dessous d'un niveau, ou variation quotidienne (en valeur absolue) supérieure à un pourcentage. Quand la "
        "condition est vraie, une notification apparaît dans l'application.",
        "Les alertes sont évaluées avec les données déjà en cache (rafraîchies par la tâche de fond au rythme "
        "configuré, 15 minutes par défaut, uniquement pour les instruments détenus ou suivis) et quand vous ouvrez "
        "vos notifications : aucune requête supplémentaire vers un fournisseur. Une alerte déclenchée est désactivée "
        "(une seule notification) et peut être réarmée. La variation quotidienne compare le dernier cours à la "
        "clôture de la veille.",
        "Les cotations peuvent être différées (15 à 20 minutes selon la place) ou anciennes hors séance : une alerte "
        "reflète l'état des données, pas le marché en temps réel. Aucune action n'en découle : pas d'ordre, pas de "
        "recommandation — l'application se limite à informer. Pas d'e-mail ni de notification mobile : la "
        "notification est visible à la prochaine ouverture.",
        [
            (
                "Bon usage",
                "Une alerte est un rappel d'aller regarder, pas un signal. Fixer un seuil ne dit rien de ce qu'il "
                "faudrait faire s'il est atteint ; ce jugement reste le vôtre, avec les informations de la fiche.",
            ),
        ],
        ("fraicheur-des-donnees", "efficience-des-marches"),
    ),
    "etude-de-strategie": _a(
        "Étude de stratégie (backtest) et ses pièges",
        "technique",
        "Ce que vaut « j'aurais acheté quand la moyenne courte passe au-dessus de la longue » — et pourquoi il faut "
        "s'en méfier.",
        "La simulation historique d'une règle mécanique simple (croisement de moyennes mobiles, prix au-dessus de "
        "sa moyenne, retour à la moyenne du RSI) sur un instrument : courbe de valeur de la règle contre « acheter "
        "et conserver », nombre de passages, exposition, statistiques de rendement et de risque de chacune.",
        "Le signal est calculé sur la clôture du jour t et la position (0 % ou 100 %, jamais à découvert, jamais à "
        "levier) s'applique à partir du jour t+1 : la règle ne voit jamais le futur. Des frais proportionnels "
        "(points de base) sont prélevés à chaque changement de position. Les deux courbes partent de 1 sur la même "
        "période et sont comparées avec les mêmes statistiques (voir « Ratios de Sharpe, Sortino et Calmar »).",
        "Sur-ajustement : avec assez de paramètres et de périodes essayés, on trouve toujours une règle qui « aurait "
        "marché » ; cela ne dit rien de l'avenir. Biais de survie : l'instrument étudié existe encore. Écarts "
        "d'exécution, liquidité, dividendes (absents des cours de clôture ajustés ou non selon la source), fiscalité "
        "des passages fréquents : ignorés. Une règle qui bat l'indice sur une période le sous-performe souvent sur "
        "la suivante. Rien ici n'est un signal ni une recommandation.",
        [
            (
                "Règles disponibles",
                "Croisement de moyennes (SMA rapide > SMA lente) ; prix au-dessus de sa SMA ; RSI : entrée quand le "
                "RSI passe sous un seuil bas, sortie quand il dépasse un seuil haut.",
            ),
            (
                "Comment lire le résultat",
                "Comparez d'abord le drawdown maximal et la volatilité, pas seulement le rendement final. Regardez "
                "le nombre de passages (chacun coûte des frais) et l'exposition (une règle peu investie rate les "
                "hausses). Changez les paramètres de peu : si le résultat bascule, il est fragile.",
            ),
            (
                "Lien avec l'efficience des marchés",
                "Si les prix intègrent l'information disponible, une règle mécanique sur les seuls prix passés ne "
                "devrait pas battre durablement le marché après frais — c'est ce que la majorité des études "
                "académiques trouvent (voir « Efficience des marchés »).",
            ),
        ],
        ("indicateurs-techniques", "efficience-des-marches", "sharpe-sortino-calmar"),
    ),
    "comparaison-base-100": _a(
        "Comparer des instruments en base 100",
        "technique",
        "Mettre plusieurs cours sur un même graphique sans que les niveaux de prix brouillent la lecture.",
        "La trajectoire relative de plusieurs instruments : chaque série est divisée par sa valeur au premier jour "
        "commun puis multipliée par 100, de sorte que toutes partent de 100 et que l'écart lu est un rendement "
        "cumulé.",
        "Seules les dates présentes dans toutes les séries sont conservées (pas d'interpolation ni de report de "
        "valeur). Chaque instrument reste dans sa propre devise.",
        "Une série en dollars et une en euros comparent des rendements en devises différentes : l'effet de change "
        "n'est pas neutralisé. Le point de départ change tout : décaler la fenêtre d'un mois peut inverser le "
        "classement. Les dividendes ne sont pas réinvestis dans un cours simple.",
        [
            (
                "Usage",
                "Comparer un titre à son indice ou à un ETF de référence, ou deux ETF sur le même thème, sur une "
                "fenêtre donnée — pour décrire, pas pour extrapoler.",
            ),
        ],
        ("capm-beta", "correlation-diversification"),
    ),
}
