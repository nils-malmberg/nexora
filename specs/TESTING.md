# Stratégie de test et CI

## Pyramide
Unités domaine (lots, frais, splits, devises, TWR/MWR), contract tests fournisseurs, intégration API/DB/migrations, tests import CSV, E2E parcours critiques, accessibilité et performance.

## Cas obligatoires
Dates/fuseaux, crypto 24/7, prix absents/différés, obligations et privés estimés, doublons/idempotence, erreurs partielles, séparation tenant, export/suppression, réauthentification. Tests de non-régression démontrant qu’aucun endpoint d’ordre n’existe en V1.

## Prédiction
Tests anti-fuite avec sentinelles futures, validation chronologique, baseline naïve, reproductibilité et vérification de feature timestamps.

## CI GitHub
Lint/format → tests unitaires → intégration avec services éphémères → migrations depuis zéro puis upgrade → scan secrets et dépendances → SAST → build Docker reproductible. Bloquer merge sur échec ; publier rapports sans données personnelles. Pen-test et revue sécurité avant production.

## Qualité opérationnelle
Fixtures synthétiques uniquement, couverture par module avec seuils justifiés, tests de restauration, smoke test après déploiement, tests de charge sur API/worker et vérification des rate limits.
