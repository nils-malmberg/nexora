# Module de prédiction — expérimental

## Positionnement
Option désactivée par défaut, destinée à l’expérimentation et à l’éducation. Elle ne donne pas de conseil financier, d’objectif de prix ni de signal d’achat/vente. Afficher incertitude, limites, date d’entraînement et avertissement proéminent.

## Données et fuites
Construire les variables uniquement avec des observations disponibles à l’instant de prédiction : décalage des prix, fenêtres rétrospectives, publication réellement connue. Séparer strictement train/validation/test par temps ; ne jamais mélanger futur, données révisées ou agrégats calculés sur toute la période.

## Validation
Walk-forward ou expanding window, benchmark naïf, comparaison à une stratégie passive seulement descriptive. Mesurer MAE/RMSE pour prévision et calibration des intervalles ; publier couverture, période, univers, coûts supposés et taux de données manquantes. Pas de split aléatoire.

## Gouvernance
Versionner code, paramètres, schéma et hash du dataset sans données personnelles. Revue humaine avant activation, kill switch, suivi de dérive, réentraînement documenté et retrait si métriques dégradées. Pas de trading automatisé en V1.
