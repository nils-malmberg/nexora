# NeXora — backend

API FastAPI unique pour l'ensemble du dashboard (`specs/*.md`) : identité et sessions, marchés
(recherche, cotations, historique OHLCV, liste de suivi), portefeuilles (transactions immuables,
positions FIFO, valorisation multi-devises avec provenance, import CSV), analyse (historique,
allocation, TWR/MWR, statistiques de rendement/risque, VaR, MEDAF, corrélations, frontière
efficiente, Monte Carlo, indicateurs techniques), actualités & événements (pipeline d'ingestion),
aide éducative et module de prédiction expérimental. **Consultation et analyse uniquement : aucun
ordre financier, aucune recommandation personnalisée** (vérifié par
`tests/integration/test_no_order_endpoints.py`).

## Démarrage local (sans Docker)

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
alembic upgrade head          # SQLite local par défaut (./nexora.db), aucune base externe requise
pytest tests -q               # 310 tests, tous hors ligne (fournisseurs "fixture", respx pour le HTTP)
uvicorn app.api.main:app --reload --port 8000
python -m app.worker.scheduler   # optionnel : rafraîchissement périodique marché + actualités
```

Le frontend (`../frontend`, `npm run dev`) proxifie `/api` vers `http://localhost:8000` : une seule
origine, cookie de session first-party, aucun CORS à configurer.

## Organisation du code

```
app/api/            routeurs HTTP (auth, me, portfolios, instruments, market, imports, analytics,
                    news, timeline, events, education, prediction, providers, admin), deps, erreurs
app/domain/         règles métier pures : positions FIFO + valorisation (positions.py), FX (fx.py),
                    analyse Phase 2 (analytics.py), boîte à outils quantitative (quant.py), import CSV
app/market/         fournisseurs de marché interchangeables : contrat (base.py), yahoo, coingecko,
                    finnhub, frankfurter, fixture/null ; budget de requêtes (ratelimit.py), HTTP
                    commun (http.py), sélection + disjoncteur (registry.py), service cache-first
app/news/           pipeline Actualités & Événements (adaptateurs RSS/JSON/ICS, dédoublonnage,
                    scoring, résumé) — inchangé fonctionnellement, rattaché aux instruments
app/prediction/     moteur expérimental (engine.py : jeu de données sans fuite, walk-forward,
                    métamodèle) et service d'exécution
app/education_content.py   contenu d'aide versionné (17 articles)
app/worker/         scheduler APScheduler (ingestion actualités + rafraîchissement marché)
alembic/            une seule histoire de migrations (schéma unifié)
```

## Sécurité (specs/SECURITY.md)

- Mot de passe `argon2id`, session opaque révocable (hash SHA-256 en base), cookie
  `HttpOnly`/`SameSite=Lax`/`Secure` (désactivable uniquement en local), CSRF double-soumission
  (`X-CSRF-Token`), limitation de débit en mémoire sur `login`/`register` et sur les endpoints qui
  sollicitent des fournisseurs externes.
- Contrôle d'accès tenant-aware : un objet d'un autre utilisateur est un 404, jamais un 403
  (IDOR) ; les instruments du catalogue partagé sont en lecture seule pour les utilisateurs.
- Rôle administrateur (premier compte inscrit ou `NEXORA_ADMIN_EMAILS`) pour la gestion des
  sources ; toute action sensible est journalisée (`audit_events`).
- En-têtes défensifs sur chaque réponse (CSP, `X-Frame-Options: DENY`, `nosniff`,
  `Referrer-Policy`, `Cache-Control: no-store`) ; `/docs` désactivé en production.
- Secrets uniquement par variables d'environnement (les adaptateurs ne stockent que le *nom* de
  la variable) ; journalisation JSON avec rédaction des clés/jetons ; CI : gitleaks, bandit,
  pip-audit.
- Suppression de compte avec réauthentification ; export complet des données ; liste des sessions
  actives et révocation.

## Données de marché (specs/DATA_SOURCES.md)

Fournisseurs configurables par famille d'actifs (`NEXORA_MARKET_EQUITY_PROVIDER`,
`..._CRYPTO_PROVIDER`, `..._FX_PROVIDER`) : Yahoo Finance (API JSON publique non officielle, usage
personnel, données différées), CoinGecko (API publique, attribution requise), Finnhub (clé
personnelle, alternative pour les actions), Frankfurter (taux de référence BCE). Chaque cotation
porte sa source, son horodatage, son âge, son statut (`fresh`/`cached`/`stale`/`unavailable`) et la
note de licence du fournisseur.

Protection des quotas — et de votre adresse IP :

- **cache-first** : une cotation est rafraîchie au plus toutes les `NEXORA_QUOTE_FRESHNESS_MINUTES`
  (15 min) ; l'historique quotidien est stocké (`ohlc_bars`) et complété seulement pour la partie
  manquante ; les taux de change sont stockés (`fx_rates`) et récupérés par série entière ;
- **budget local par fournisseur** (seau à jetons, `NEXORA_<PROVIDER>_RATE_LIMIT_PER_MINUTE`) :
  quand il est épuisé, on sert le cache au lieu d'attendre — jamais de rafale ;
- **disjoncteur persistant** (`market_providers`) : après 3 échecs le fournisseur est mis en pause
  10 min ; après `NEXORA_MARKET_AUTO_DISABLE_AFTER_FAILURES` échecs consécutifs il se désactive
  tout seul et doit être réactivé par un administrateur après enquête (leçon de l'incident SEC
  EDGAR documenté dans `specs/DATA_SOURCES.md`) ;
- le worker ne rafraîchit que les instruments **détenus ou suivis**, séquentiellement, toutes les
  `NEXORA_MARKET_REFRESH_INTERVAL_SECONDS`.

Aucun test n'appelle un fournisseur réel : la suite force les adaptateurs `fixture`/`null` et
intercepte le HTTP avec `respx` (tests de contrat sur des charges utiles enregistrées).

## Valorisation et FX

Positions rejouées en FIFO ; prix applicable = observation la plus récente (cotation, clôture
quotidienne, saisie manuelle, valorisation privée) ; conversion dans la devise du portefeuille
avec le taux de référence daté (provenance renvoyée : `fx_rates`, `fx_rate`, `fx_source`). Sans
taux connu, le montant reste non converti et listé (`unconverted_currencies`), jamais converti à un
taux inventé. Un prix manquant exclut la position du total et est signalé.

## Prédiction (specs/PREDICTION.md)

Désactivé par défaut (`NEXORA_PREDICTION_ENABLED`). Variables construites uniquement avec le passé
(retards, fenêtres glissantes, momentum, RSI), cible = log-rendement à `h` jours, validation
walk-forward chronologique avec écart de `h−1` entre entraînement et test, modèles de base (naïf,
moyenne historique, ridge, forêt aléatoire, gradient boosting) et métamodèle de stacking (poids
positifs, ajusté sur les seules prédictions hors échantillon). Métriques MAE/RMSE/direction/
couverture d'intervalle contre le benchmark naïf, empreinte du jeu de données, version du code,
graine : chaque expérience est reproductible. Tests anti-fuite avec sentinelles futures dans
`tests/unit/test_prediction_leakage.py`.

## Limites connues (V1)

- `transfert` (import CSV et API) : sémantique source+destination non couverte ; rejeté
  explicitement.
- Historique/analytique recalculés à la demande (pas de cache de calcul) : suffisant pour un
  portefeuille personnel.
- Limitation de débit et caches de recherche en mémoire (mono-instance).
- Yahoo Finance est une API non officielle : elle peut cesser de fonctionner sans préavis — passer
  alors `NEXORA_MARKET_EQUITY_PROVIDER` à `finnhub` (clé gratuite) ou `null`.
- Les candles crypto (CoinGecko, gratuit) ne fournissent que des clôtures : graphique en ligne.
- Pas de migration depuis les deux bases séparées des versions précédentes (`nexora` +
  `nexora_portfolio`) : le schéma unifié repart de zéro (voir README racine).

## Tests

```bash
ruff check . && ruff format --check .
pytest tests -q
coverage run -m pytest tests -q && coverage report --fail-under=85
bandit -q -r app && pip-audit --skip-editable
```
