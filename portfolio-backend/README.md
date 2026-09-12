# Module Portefeuille — backend

Dashboard NeXora (`specs/ROADMAP.md`, Phases 1 et 2) : authentification, portefeuilles,
transactions, positions et valorisation avec provenance (Phase 1), import CSV, historique,
allocation, risque descriptif, performance TWR/MWR, indicateurs techniques et aide éducative
(Phase 2). **Consultation et analyse uniquement : aucun ordre financier, aucune recommandation
personnalisée.**

Service indépendant du module [Actualités & Événements](../backend/README.md) (base de données,
API et frontend séparés) — voir `specs/README.md` pour le périmètre global du produit.

## Démarrage local (sans Docker)

```bash
cd portfolio-backend
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
alembic upgrade head        # par défaut : SQLite local, aucune base externe requise
pytest tests -q              # 100% des tests utilisent SQLite en mémoire, aucun appel réseau réel
uvicorn app.api.main:app --reload --port 8001
```

## Démarrage avec Docker Compose (depuis la racine du dépôt)

```bash
cp .env.example .env
docker compose up --build portfolio-api portfolio-frontend postgres
```

- API : http://localhost:8001 (`/docs` pour OpenAPI, `/health`, `/metrics`)
- Frontend : http://localhost:5174
- Base de données : `nexora_portfolio` sur le même serveur Postgres que le module
  Actualités & Événements (créée automatiquement au premier démarrage, voir
  `infra/postgres-init/`).

> Le script de `infra/postgres-init/` ne s'exécute qu'à la toute première initialisation du volume
> `postgres_data` (comportement standard de l'image officielle Postgres). Si ce volume existe déjà
> (déploiement News & Events antérieur à cette PR), créez la base une seule fois manuellement :
> `docker compose exec postgres psql -U nexora -d nexora -c "CREATE DATABASE nexora_portfolio;"`.

## Authentification

Email + mot de passe (hash `argon2id`), session opaque révocable côté serveur (cookie
`HttpOnly`/`SameSite=Lax`, `Secure` en production) et jeton CSRF renvoyé dans le corps de
`register`/`login`/`me` (à réémettre en en-tête `X-CSRF-Token` sur toute requête mutante). Limitation
de débit en mémoire sur `login`/`register` (mono-instance, même choix assumé que l'absence de Redis
dans le module Actualités & Événements). MFA explicitement hors périmètre de cette première version
(`specs/SECURITY.md` la place en renforcement ultérieur).

## Modèle de transaction et calcul de position

Une transaction validée est **immuable** (`specs/PRODUCT_SPEC.md`) : une correction passe par
`POST /portfolios/{id}/transactions/{tx_id}/reverse`, qui exclut la transaction de tous les calculs
(`reversed_at`/`reversal_reason`) sans jamais l'éditer ni la supprimer. Les positions sont
recalculées par rejeu FIFO (`app/domain/positions.py`) à chaque écriture affectant l'instrument
concerné. Convention pour les mouvements de trésorerie purs (`depot`, `retrait`, `dividende`,
`coupon`) : `quantity` vaut toujours `1` et `unit_price` porte le montant — mêmes colonnes que les
autres types, pour rester compatible avec l'import CSV (`specs/PORTFOLIO_IMPORTS.md`, voir plus bas).

Aucune conversion de change n'est appliquée : une position ou un solde de trésorerie dans une devise
différente de celle du portefeuille est listé séparément (`unconverted_currencies`) et exclu du total
plutôt que converti avec un taux inventé.

## Import CSV

`specs/PORTFOLIO_IMPORTS.md`, en trois requêtes (`POST /portfolios/{id}/imports`, puis
`.../{job_id}/preview`, puis `.../{job_id}/commit`) : upload + détection séparateur/encodage/en-têtes,
mapping des colonnes + validation ligne par ligne (rien n'est écrit), puis confirmation explicite.
Une ligne en erreur n'annule pas les autres — le rapport (`row_results`) reste consultable même après
confirmation, y compris ré-téléchargeable via `GET /portfolios/{id}/imports/{job_id}`.

Le fichier brut n'est jamais écrit sur disque ni conservé tel quel : il est parsé immédiatement en
lignes structurées (`app/domain/csv_import.py`), qui sont elles-mêmes purgées (`raw_rows`) une fois le
job confirmé — seul le rapport (déjà structuré) reste disponible.

Déduplication par `external_id` (contrainte unique existante) ou, à défaut, par empreinte canonique
(hash des champs, comparé aux transactions déjà en base et aux autres lignes du même fichier) : un
import répété est un no-op silencieux sur les lignes déjà présentes (statut `duplicate`), jamais une
erreur ni une entrée en double. Un instrument inconnu référencé par une ligne est créé automatiquement
si `asset_class`/`currency` sont renseignés — toujours signalé dans le rapport, jamais silencieux.

`transfert` reste un type rejeté explicitement (même limitation que pour l'API manuelle ci-dessous) ;
`valorisation_privee` est supporté (crée la transaction, une `PrivateValuation` et un `PricePoint`,
avec `method="Import CSV"` puisque le CSV V1 n'a pas de colonne dédiée).

## Analyse (Phase 2 — specs/ANALYTICS_AND_CHARTS.md)

`app/domain/analytics.py` expose, par portefeuille, un historique de valorisation
(`GET /portfolios/{id}/analytics/history`), une répartition par classe d'actif/instrument/devise
(`.../allocation`, **trésorerie exclue** — déjà sa propre carte dans `specs/UX_SPEC.md`), un risque
descriptif — volatilité annualisée et repli maximum (`.../risk`) — et une performance TWR/MWR
(`.../performance`). Par instrument, `GET /instruments/{id}/indicators` calcule SMA/EMA/RSI/MACD
sur les prix connus.

Tout est **strictement descriptif du passé, jamais une recommandation**, et la couverture
insuffisante est explicitement signalée (`has_sufficient_data=false`) plutôt que de produire un
chiffre trompeur — moins de 3 points de valorisation, par exemple, ne permet pas de calculer une
volatilité. L'historique est calculé aux dates réelles où une transaction ou un prix existe (pas une
série quotidienne interpolée) ; TWR/MWR ne considèrent `depot`/`retrait` comme flux externes que
`dividende`/`coupon` restent en trésorerie interne. Aucune dépendance de graphique n'a été ajoutée :
les courbes sont du SVG fait main (`portfolio-frontend/src/charts/`) — pas de vrais chandeliers
OHLC tant qu'aucune source ne fournit open/high/low/volume (voir "Fournisseur de marché" plus bas).

## Aide éducative (Phase 2 — specs/UX_SPEC.md)

`GET /education` et `GET /education/{slug}` servent un contenu éditorial statique et versionné
(`app/education_content.py`, pas une table — ce n'est pas une donnée utilisateur) : ce que chaque
métrique mesure, sa méthode et ses limites, ton neutre, jamais de recommandation. Public (aucune
authentification requise).

## Fournisseur de marché

`app/adapters/market_data.py` définit l'interface `MarketDataProvider`, mais **aucun fournisseur réel
n'est branché dans cette version** : seul un prix saisi manuellement (`POST
/instruments/{id}/prices`) alimente une position. Le choix d'un fournisseur réel (Finnhub est le
candidat naturel, une clé fonctionnelle étant déjà configurée pour le module Actualités &
Événements) suivra le même processus de vérification licence/quotas et de confirmation explicite
que pour les sources de ce dernier — voir `specs/DATA_SOURCES.md`.

## Limites connues (V1)

- `transfert` (import CSV et API manuelle) : sémantique source+destination non couverte par le
  schéma actuel (un seul champ `account`) ; rejeté explicitement plutôt que mal interprété.
- Pas de vrais chandeliers OHLC (voir section Analyse) : graphiques en ligne uniquement tant
  qu'aucune source ne fournit open/high/low/volume.
- Historique/risque/performance recalculés à la demande en rejouant les transactions (pas de cache) :
  suffisant au volume V1 (portefeuille personnel), documenté comme choix délibéré.
- Catalogue d'instruments propre à chaque utilisateur (pas de référentiel partagé/externe tant
  qu'aucun fournisseur réel n'est branché).
- Import CSV : l'empreinte canonique d'une ligne sans `external_id` utilise le symbole (pas un id
  réel) tant que l'instrument qu'elle référence n'existe pas encore — une ligne qui crée à chaque
  fois un nouvel instrument ne serait donc pas détectée comme doublon sur une ré-importation (cas
  marginal ; `external_id` reste la méthode de déduplication recommandée).
- Rate limiting en mémoire (mono-instance) : suffisant au volume V1, documenté comme choix délibéré.
- `npm audit` (portfolio-frontend) signale la même vulnérabilité modérée/haute dans esbuild (embarquée
  par Vite 5.x) déjà documentée pour le frontend Actualités & Événements — n'affecte que le serveur de
  développement (`vite dev`), jamais le build statique servi en production par nginx. Correctif complet
  nécessitant un saut de version majeure de Vite (6/7/8, cassant) ; risque accepté pour l'instant.

## Tests

```bash
ruff check . && ruff format --check .
pytest tests -q
coverage run -m pytest tests -q && coverage report
```

Aucun test n'appelle un service externe réel. La CI (`.github/workflows/ci-portfolio.yml`) ajoute une
exécution des migrations depuis zéro contre un vrai PostgreSQL éphémère.
