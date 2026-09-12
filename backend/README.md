# Module Actualités & Événements — backend

Implémentation du module décrit dans [`specs/NEWS_AND_EVENTS.md`](../specs/NEWS_AND_EVENTS.md) : collecte,
normalisation, déduplication, scoring explicable, résumé contrôlé, cache/fraîcheur, API de lecture,
observabilité. **Aucun ordre financier, aucune recommandation, lecture seule.**

## Démarrage local (sans Docker)

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp ../.env.example ../.env   # ajuster si besoin ; par défaut SQLite local, aucun secret requis
alembic upgrade head
pytest tests -q              # 100% des tests utilisent des fixtures locales, aucun appel réseau réel
uvicorn app.api.main:app --reload
```

Par défaut (`NEXORA_DATABASE_URL` non défini), l'application utilise un fichier SQLite local
(`nexora_news_events.db`) : aucune base externe n'est nécessaire pour développer ou lancer les tests.
PostgreSQL est la cible de production (voir `docker-compose.yml` à la racine).

## Démarrage avec Docker Compose (depuis la racine du dépôt)

```bash
cp .env.example .env
docker compose up --build              # api (8000), worker, postgres, frontend (5173)
# Optionnel : démo entièrement synthétique via fixtures locales servies en HTTP
SEED_DEMO_DATA=1 docker compose --profile demo up --build
```

Le profil `demo` démarre un serveur nginx statique (`demo-fixtures`, port 8090) qui sert les fixtures
committées (`backend/tests/fixtures`) et seed un actif + 3 fournisseurs (RSS, JSON, calendrier ICS) qui
pointent dessus — aucune clé, aucun compte, aucun appel réseau réel.

## Configuration (variables d'environnement, préfixe `NEXORA_`)

| Variable | Rôle | Défaut |
|---|---|---|
| `DATABASE_URL` | Connexion SQLAlchemy | `sqlite:///./nexora_news_events.db` |
| `ADMIN_API_KEY` | Clé statique protégeant `/admin/providers/{id}/sync`. Vide = endpoints désactivés (503). Placeholder en attendant l'intégration à l'auth réelle du dashboard. | *(vide)* |
| `NEWS_FRESHNESS_MINUTES` / `EVENT_FRESHNESS_MINUTES` | Seuils de fraîcheur (`stale` calculé à la lecture) | `60` / `1440` |
| `INGESTION_INTERVAL_SECONDS` / `INGESTION_JITTER_SECONDS` | Cadence du worker planifié | `900` / `60` |
| `HTTP_TIMEOUT_SECONDS`, `MAX_RETRIES`, `RETRY_BACKOFF_BASE_SECONDS` | Résilience des adaptateurs | `10`, `3`, `1.0` |
| `CIRCUIT_BREAKER_FAILURE_THRESHOLD` / `_RESET_SECONDS` | Disjoncteur par fournisseur | `5` / `300` |
| `AUTO_DISABLE_AFTER_FAILURES` | Désactivation automatique (`enabled=false`) après ce nombre d'échecs **consécutifs**, tous cycles ouvert/demi-ouvert confondus — évite qu'un fournisseur bloqué soit re-sondé indéfiniment sans supervision (voir incident sec.gov dans `specs/DATA_SOURCES.md`) | `15` |
| `DEDUP_TITLE_SIMILARITY_THRESHOLD` / `_TIME_WINDOW_HOURS` | Seuils de déduplication approximative | `0.88` / `72` |
| `DEFAULT_PAGE_SIZE` / `MAX_PAGE_SIZE` | Pagination API | `20` / `100` |
| `CORS_ALLOWED_ORIGINS` | Origines autorisées (CSV) pour l'API lecture seule | `*` |
| `WORKER_METRICS_PORT` | Port `/metrics` du worker — processus séparé de l'API, donc registre Prometheus séparé | `9100` |

## Observabilité : deux endpoints `/metrics`

L'API et le worker sont deux processus distincts avec chacun leur propre registre Prometheus en
mémoire : `GET http://api:8000/metrics` ne voit **pas** les métriques d'ingestion produites par le worker.
Configurer Prometheus pour scraper les deux cibles (`api:8000/metrics` et `worker:9100/metrics`).

Aucun secret n'est jamais stocké en base ou dans un JSON versionné : la configuration d'un fournisseur
(`Provider.config`) ne référence qu'un **nom de variable d'environnement** (ex. `env_var: "MON_API_KEY"`),
résolue par l'adaptateur au moment de l'appel (`ProviderAdapter.resolve_secret`). Une variable manquante
lève `AdapterMisconfigured` plutôt que d'envoyer une requête non authentifiée en silence.

## Ajouter un fournisseur

1. Choisir un adaptateur existant (`rss`, `json_api`, `calendar_ics`) — voir `app/adapters/`.
2. Créer une ligne `Provider` (`type`, `config`, `license_note`) et une ou plusieurs `ProviderFeed`
   (`url`, `extra_config` avec `asset_id` si le flux est dédié à un seul actif).
3. Documenter licence, quotas, attribution dans `license_note` et dans `specs/DATA_SOURCES.md`.
4. Déclencher un essai manuel : `python -m app.worker.cli sync <provider-name>`.
5. Vérifier `GET /api/v1/providers/status` et les métriques (`/metrics`).

Pour un nouveau **type** d'adaptateur : implémenter `ProviderAdapter` (`fetch`, `normalize`, `health`,
`capabilities`) dans `app/adapters/`, l'enregistrer dans `app/adapters/registry.py`, ajouter des fixtures
et tests d'intégration sous `tests/fixtures/` et `tests/integration/` (formats invalides, pagination,
rate limit, timeout — voir les adaptateurs existants comme modèle).

## Procédure de reprise (fournisseur en panne ou dégradé)

1. `GET /api/v1/providers/status` : `circuit_state=open` indique un fournisseur écarté après
   `CIRCUIT_BREAKER_FAILURE_THRESHOLD` échecs consécutifs ; les données déjà collectées restent servies
   (avec `stale=true` une fois le TTL dépassé), aucune donnée valide n'est écrasée.
2. Consulter les logs structurés (JSON, corrélés par `ingestion_run_id`) pour l'`error_code` de la dernière
   `IngestionRun` (`GET` via une requête directe en base, ou futurs endpoints d'administration).
3. Corriger la cause (credential manquant, quota dépassé, format changé) puis relancer manuellement :
   `python -m app.worker.cli sync <provider-name>` — un succès referme le disjoncteur (`closed`) et
   réinitialise le compteur d'échecs. Le disjoncteur repasse aussi en `half_open` automatiquement après
   `CIRCUIT_BREAKER_RESET_SECONDS`, pour un nouvel essai sans intervention.
4. En cas de changement durable de schéma source, mettre à jour `Provider.config` (mapping JSON ou feeds
   RSS/ICS) sans redéploiement de code lorsque c'est un adaptateur générique.
5. Si `consecutive_failures` atteint `AUTO_DISABLE_AFTER_FAILURES`, le fournisseur passe automatiquement
   à `enabled=false` (log `ERROR` + métrique `nexora_provider_auto_disabled_total`) : il ne sera **plus
   jamais** re-sondé automatiquement, même après le délai du disjoncteur. Investiguer la cause avant de
   remettre `enabled=true` manuellement — ne jamais réactiver puis relancer en boucle sans avoir compris
   pourquoi ça échouait (voir l'incident sec.gov documenté dans `specs/DATA_SOURCES.md` : des relances
   répétées et non supervisées contre une source qui bloquait déjà ont provoqué un bannissement d'IP réel).

## Limites connues (V1)

- Résumé extractif simple (pas de modèle de langage), volontairement pour rester explicable, gratuit et
  sans dépendance externe — voir `app/pipeline/summarize.py`.
- Scoring de pertinence déterministe et documenté (`app/pipeline/scoring.py`), pas un modèle ML.
- Timeline non paginée par curseur (contrairement à `/news`) : `limit` borné (≤ 1000), documenté comme
  simplification V1.
- `/admin/providers/{id}/sync` est protégé par une clé statique en attendant l'intégration dans le futur
  système d'authentification du dashboard complet (hors périmètre de ce module).
- Pas de cache dédié (Redis) : la fraîcheur/staleness est calculée à la lecture à partir des timestamps
  persistés — suffisant au volume V1, documenté comme choix délibéré pour limiter l'infrastructure.
- `npm audit` (frontend) signale une vulnérabilité modérée/haute dans esbuild, embarquée par Vite 5.x —
  n'affecte que le serveur de développement (`vite dev`), jamais le build statique servi en production par
  nginx. Un correctif complet nécessite un saut de version majeure de Vite (6/7/8, cassant) ; risque accepté
  pour l'instant, à réévaluer lors d'une montée de version du frontend.

## Tests

```bash
ruff check . && ruff format --check .
pytest tests/unit tests/integration -q
coverage run -m pytest tests -q && coverage report
```

Aucun test n'appelle un service externe réel (mocks `respx`/`httpx`, fixtures RSS/JSON/ICS locales sous
`tests/fixtures/`). La CI ajoute une exécution des migrations depuis zéro contre un vrai PostgreSQL
éphémère (voir `.github/workflows/ci.yml`).
