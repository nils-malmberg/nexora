# NeXora — Module Actualités & Événements

Ce dépôt contient l'implémentation du **module Actualités & Événements** décrit dans
[`specs/NEWS_AND_EVENTS.md`](specs/NEWS_AND_EVENTS.md), livré comme un service autonome (pas le dashboard
d'investissement complet — voir [`specs/README.md`](specs/README.md) pour le périmètre global du produit).

**Lecture seule. Aucun ordre financier, aucune recommandation personnalisée, aucune exécution.**

## Structure

```
backend/    API FastAPI + pipeline d'ingestion (adaptateurs, normalisation, dédup, scoring, résumé)
frontend/   Interface React/TypeScript (actualités, chronologie, événements à venir)
specs/      Spécifications produit de référence (non modifiées par cette implémentation)
```

## Démarrage rapide

```bash
cp .env.example .env
docker compose up --build
```

- API : http://localhost:8000 (`/docs` pour OpenAPI, `/health`, `/metrics`)
- Frontend : http://localhost:5173
- PostgreSQL : localhost:5432

Pour voir le pipeline fonctionner de bout en bout sans aucune source réelle :

```bash
SEED_DEMO_DATA=1 docker compose --profile demo up --build
docker compose exec api python -m app.worker.cli sync-all
```

Détails de configuration, ajout d'un fournisseur, procédure de reprise : [`backend/README.md`](backend/README.md).

## Avertissement

Les informations affichées proviennent de fournisseurs configurés (flux RSS/Atom, API, calendriers
officiels) ; elles peuvent être incomplètes, différées ou temporairement indisponibles. Ce module fournit
des faits, synthèses et estimations sourcés à titre informatif — il ne constitue ni conseil financier, ni
recommandation, ni service d'exécution.
