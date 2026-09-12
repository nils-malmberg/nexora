# NeXora — Dashboard multi-actifs

Ce dépôt implémente progressivement le dashboard décrit dans [`specs/README.md`](specs/README.md), sous
forme de **services indépendants** (chacun avec sa base de données, son API et son frontend) plutôt
qu'une application monolithique :

- **Actualités & Événements** ([`specs/NEWS_AND_EVENTS.md`](specs/NEWS_AND_EVENTS.md)) : faits,
  synthèses et estimations sourcés par instrument.
- **Portefeuille** ([`specs/ARCHITECTURE.md`](specs/ARCHITECTURE.md), Phase 1 de
  [`specs/ROADMAP.md`](specs/ROADMAP.md)) : authentification, portefeuilles, transactions, positions
  et valorisation avec provenance.

**Consultation et analyse uniquement. Aucun ordre financier, aucune recommandation personnalisée,
aucune exécution.**

## Structure

```
backend/               API FastAPI du module Actualités & Événements (adaptateurs, pipeline, scoring)
frontend/               Interface React/TypeScript du module Actualités & Événements
portfolio-backend/      API FastAPI du module Portefeuille (auth, portefeuilles, transactions, valorisation)
portfolio-frontend/     Interface React/TypeScript du module Portefeuille
infra/postgres-init/    Script de création de la base `nexora_portfolio` au premier démarrage
specs/                  Spécifications produit de référence (non modifiées par ces implémentations)
```

Les deux frontends sont volontairement séparés pour l'instant (chaque module a été livré et testé
indépendamment) ; une intégration UI unifiée (actualités affichées dans la page d'un instrument du
dashboard) est un travail ultérieur, une fois les deux modules stables.

## Démarrage rapide

```bash
cp .env.example .env
docker compose up --build
```

- Actualités & Événements — API : http://localhost:8000 (`/docs`, `/health`, `/metrics`) · Frontend :
  http://localhost:5173
- Portefeuille — API : http://localhost:8001 (`/docs`, `/health`, `/metrics`) · Frontend :
  http://localhost:5174
- PostgreSQL : localhost:5432 (bases `nexora` et `nexora_portfolio`, voir `infra/postgres-init/`)

Pour voir le pipeline Actualités & Événements fonctionner de bout en bout sans aucune source réelle :

```bash
SEED_DEMO_DATA=1 docker compose --profile demo up --build
docker compose exec api python -m app.worker.cli sync-all
```

Détails de configuration : [`backend/README.md`](backend/README.md) (Actualités & Événements) et
[`portfolio-backend/README.md`](portfolio-backend/README.md) (Portefeuille).

## Avertissement

Les informations affichées proviennent de fournisseurs configurés ou de saisies manuelles ; elles
peuvent être incomplètes, différées, estimées ou temporairement indisponibles — toujours signalées
comme telles, jamais inventées. Cet outil fournit de l'information à titre indicatif — il ne
constitue ni conseil financier, ni recommandation, ni service d'exécution.
