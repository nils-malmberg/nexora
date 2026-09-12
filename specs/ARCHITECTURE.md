# Architecture cible

## Vue logique
- **Web client** : tableaux, graphiques, import guidé, accessibilité.
- **API** : authentification, portefeuille, import, analytics, aide ; validation stricte et pagination.
- **Workers** : synchronisation de marché, normalisation, calculs asynchrones et notifications de fraîcheur.
- **Domaine** : instruments, lots, transactions, prix, valorisations, métriques ; indépendant des fournisseurs.
- **Adaptateurs** : Yahoo-compatible par défaut, CSV, connecteurs optionnels en feature flags.
- **Persistance** : PostgreSQL pour le domaine ; stockage objet chiffré pour imports/exports temporaires ; cache avec TTL pour cotations.
- **Observabilité** : logs structurés, métriques, traces et alertes sans données sensibles.

## Flux de cotation
Scheduler → adaptateur fournisseur → validation de schéma/devise → normalisation → stockage avec provenance → calcul de valorisation → cache/API. Respecter rate limits, backoff et absence de données : ne pas remplacer silencieusement un prix.

## Modèle minimal
`User`, `Portfolio`, `Instrument`, `Transaction`, `PositionLot`, `PricePoint`, `PrivateValuation`, `ImportJob`, `AuditEvent`, `ProviderCredentialRef`. Clés et index par tenant ; timestamps UTC ; montants décimaux, jamais flottants pour les valeurs financières.

## Déploiement
Docker compose en local ; images immuables en CI/CD ; migrations versionnées et réversibles quand possible ; sauvegardes chiffrées testées ; environnements séparés. HTTPS en production, configuration par environnement, feature flags pour connecteurs et prédiction.

## Résilience
Idempotency key sur imports et jobs ; files avec reprise ; circuit breaker fournisseur ; health/readiness checks ; dégradation lisible (dernier prix avec âge affiché). Aucun secret dans le dépôt, les images, logs ou fixtures.
