# Spécification API (contrat V1)

Base `/api/v1`, JSON, UTC, identifiants opaques. Authentification via session/token court ; permissions vérifiées sur chaque ressource. Réponses d’erreur : `{code, message, details, request_id}` sans secret.

## Endpoints
- `GET/POST /portfolios`, `GET/PATCH/DELETE /portfolios/{id}`
- `GET/POST /portfolios/{id}/transactions` ; `GET /positions`, `GET /valuation`
- `GET /instruments/search?q=` et `GET /instruments/{id}/prices?from=&to=&interval=`
- `POST /imports/preview`, `POST /imports/{id}/commit`, `GET /imports/{id}`
- `GET /analytics/performance`, `/allocation`, `/risk`
- `GET /portfolios/consolidated` (tous les portefeuilles dans la devise de référence) ; `GET /portfolios/{id}/analytics/realized?year=`, `/income?year=`
- `GET /instruments/{id}/analytics/strategy-study?rule=&fast=&slow=&rsi_period=&rsi_low=&rsi_high=&fee_bps=&days=` ; `GET /market/compare?instrument_ids=&days=`
- `GET /instruments/{id}/decision-aid?refresh_fundamentals=` ; `GET /market/decision-overview` (données en cache uniquement) ; `GET /portfolios/{id}/checkup?days=` ; `PATCH /portfolios/{id}/targets` (allocation cible par classe, fractions sommant à 1)
- `GET/POST /alerts`, `POST /alerts/{id}/rearm`, `DELETE /alerts/{id}` ; `GET /notifications?unread_only=`, `POST /notifications/read`, `DELETE /notifications/{id}` — informatives uniquement, aucune action
- `GET /education/{slug}`
- `GET /providers/status`; administration séparée pour configuration et quotas
- `GET /me/export`, `DELETE /me` (confirmation et réauthentification)

## Conventions
Pagination curseur, filtres bornés, ETag/cache pour historiques, idempotency key sur mutations/imports, version de schéma et limites de payload. Ne jamais exposer secret provider ni données d’un autre utilisateur.

## Exemple de position
```json
{"instrument_id":"opaque-id","quantity":"2.500000","market_value":"1234.56","currency":"EUR","price_as_of":"2026-09-12T08:15:00Z","freshness":"delayed"}
```
Les montants sont des chaînes décimales afin d’éviter les erreurs binaires. Documenter OpenAPI dans le dépôt lors de l’implémentation.
