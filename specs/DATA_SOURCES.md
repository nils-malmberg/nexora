# Sources de données

## Politique
Le fournisseur gratuit de type Yahoo Finance est l’adaptateur initial à évaluer, non une promesse de disponibilité, d’exactitude ou de droit de redistribution. Vérifier et documenter les conditions de licence avant chaque usage commercial ou affichage public.

## Contrat fournisseur
Chaque adaptateur implémente : recherche d’instrument, cotation, historique OHLCV, corporate actions si disponibles, devise, limites, statut et attribution. Retourner `source`, `retrieved_at`, `as_of`, `granularity`, `is_delayed`, `license_note` et un code d’erreur explicite.

## Fraîcheur et cadence
Cible : 15 minutes quand l’API et la licence l’autorisent. Sinon cadence et badge de fraîcheur propres à la source. Pas de polling agressif ; cache TTL, quotas, backoff exponentiel et journal des échecs.

## Couverture par classe
- Actions/ETF : symbole, place, devise, OHLCV, dividendes/splits selon disponibilité.
- Crypto : paire, exchange/source, fuseau et agrégation ; attention aux différences de marché.
- Obligations : prix/coupon/maturité si disponible ; sinon saisie contrôlée et valorisation datée.
- Privés : aucune cotation supposée ; valorisation manuelle ou importée avec méthode, date et confiance.

## Qualité
Contrôler monotonicité temporelle, doublons, OHLC cohérents, devise, valeurs négatives interdites et trous. Conserver données brutes utiles à l’audit selon rétention. Montrer la couverture et l’âge, pas une fausse précision.

## Ajouter une source
Créer un adaptateur derrière l’interface, documenter licence/attribution/quotas, secrets, tests contractuels, mapping d’identifiants, stratégie de repli et runbook d’incident. Ne jamais embarquer de clé dans le code ou un fichier JSON versionné.

## Fournisseurs configurés — module Actualités & Événements

Sources réelles vérifiées (URL testée, licence et quotas confirmés à la source) pour `app/adapters/rss_atom.py` et `app/adapters/json_api.py`. Aucun scraping : uniquement flux Atom/JSON officiels ou sous CGU claires.

### SEC EDGAR — dépôts réglementaires (adaptateur `rss`)

- **Type** : flux Atom officiel du régulateur boursier américain (SEC), un flux par société (CIK).
- **URL** : `https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=<CIK>&type=&dateb=&owner=include&count=40&output=atom`
- **Licence** : information publique du gouvernement fédéral américain. Page officielle sec.gov/privacy : *« Information presented on sec.gov is considered public information and may be copied or further distributed by users of the web site without the SEC's permission »*. Ne pas utiliser le sceau/logo SEC ni la marque « EDGAR » à des fins de branding ; citer « SEC EDGAR » comme source factuelle est explicitement permis.
- **Quotas** : 10 requêtes/seconde maximum (politique officielle « fair access »).
- **Attribution/identification** : en-tête `User-Agent` **obligatoire**, au format `NomSociété/App contact@domaine.com` — une requête sans identification déclarée est bloquée (« Undeclared Automated Tool »).
- **Authentification** : aucune, aucune inscription requise.
- **Catégorie recommandée** : `reglementation` (fixée via `category_hint` sur le `ProviderFeed`, car le type de dépôt brut — 8-K, 10-Q, etc. — n'est pas une catégorie reconnue par le module).
- **Confiance de base** : source primaire officielle — `base_confidence` élevé recommandé (0.9).
- **⚠️ Incident réel (2026-09-12)** : le domaine sec.gov est protégé par Akamai Bot Manager. Un premier test (User-Agent correct, en-têtes de type navigateur) a été bloqué (`403 "Your Request Originates from an Undeclared Automated Tool"`) malgré une politique écrite qui autorise l'accès automatisé — ceci semble être une restriction technique (empreinte TLS/HTTP du client), indépendante de la conformité déclarative. Le fournisseur n'a alors **pas été désactivé immédiatement** : le worker planifié a continué à re-tenter automatiquement (disjoncteur → demi-ouvert → nouvel échec, en boucle, toutes les ~15-20 min) pendant que le développement se poursuivait sur d'autres sujets, en plus de plusieurs vérifications manuelles répétées (curl direct, requêtes de recherche). Au total, plusieurs dizaines de requêtes ont atteint sec.gov en quelques heures, ce qui a très probablement transformé un blocage ponctuel en **bannissement réel de l'adresse IP** (confirmé par l'utilisateur). Le fournisseur `sec-edgar-filings` a été désactivé (`enabled=false`) en base par précaution.
  - **Correctif structurel** (voir `app/pipeline/ingest.py`) : un fournisseur qui accumule `NEXORA_AUTO_DISABLE_AFTER_FAILURES` (défaut 15) échecs consécutifs — tous cycles ouvert/demi-ouvert confondus — se désactive désormais automatiquement, au lieu de re-sonder indéfiniment sans supervision humaine.
  - **Ne pas réactiver ce fournisseur** avant confirmation que le bannissement est levé, et ne tester manuellement qu'une seule fois à la fois, jamais en boucle.
  - La légalité/licence de la source n'est pas remise en cause, seule son accessibilité technique immédiate l'est.

### Finnhub — actualités par société (adaptateur `json_api`)

- **Type** : API JSON gratuite (compte requis), endpoint `company-news`.
- **URL** : `https://finnhub.io/api/v1/company-news?symbol=<TICKER>&from=<YYYY-MM-DD>&to=<YYYY-MM-DD>&token=<clé>` — vérifié en direct (réponse JSON structurée, y compris en cas de clé invalide).
- **Licence/quotas** : offre gratuite réservée à un usage personnel/non commercial, ≈60 appels/minute. **CGU exactes à revérifier par l'utilisateur lors de l'inscription** sur finnhub.io (page de tarification dynamique, non vérifiable par récupération automatique).
- **Authentification** : clé API en paramètre de requête `token` — jamais commitée, référencée uniquement par nom de variable d'environnement dans `Provider.config.auth.env_var`.
- **Catégorie** : laissée au mapping par défaut (`autre`) sauf configuration contraire ; pas de champ catégorie fiable dans la réponse standard.
- **Confiance de base** : agrégateur tiers — `base_confidence` modéré recommandé (0.6).
- **Format de date** : `CompanyNews.datetime` est un timestamp Unix (entier), confirmé par le schéma OpenAPI officiel (`https://finnhub.io/static/swagger.json`), pas une chaîne ISO 8601. Nécessite `provider_config.timestamp_format: "unix_seconds"` (ajouté à `app/adapters/json_api.py` — voir tests dans `tests/integration/test_json_adapter.py`).
- **Fenêtre de dates glissante** : l'endpoint exige `from`/`to` ; `{{today}}` / `{{today-Nd}}` dans `query_params` sont résolus à chaque appel (`resolve_query_param_templates`) pour rester à jour sans reconfiguration périodique.
- **Authentification réelle** : paramètre de requête `token`, confirmé par `securityDefinitions` du schéma OpenAPI (`"in": "query"`, pas un en-tête). L'adaptateur supporte désormais `auth.in: "query"`.
- **⚠️ Constat opérationnel** : la clé fournie lors de la configuration initiale a été testée en direct (requête réelle, en dehors de l'application) et retourne `401 Invalid API key`, avec les deux mécanismes d'authentification. Vérifier la clé sur finnhub.io (Dashboard → API Keys) et la remplacer dans `.env`.

### Calendrier ICS — aucune source retenue pour l'instant

Aucun calendrier ICS officiel (Réserve fédérale, NYSE, Nasdaq) n'a été trouvé avec une licence de réutilisation programmatique claire ; les agrégateurs tiers identifiés affichent un copyright « tous droits réservés » sans autorisation explicite. À réévaluer si une société suivie publie son propre calendrier IR en ICS.

## Fournisseurs de données de marché — application unifiée (`backend/app/market/`)

Adaptateurs interchangeables derrière `MarketDataProvider` / `FxProvider` (`base.py`), choisis par
famille d'actifs via `NEXORA_MARKET_EQUITY_PROVIDER`, `NEXORA_MARKET_CRYPTO_PROVIDER` et
`NEXORA_MARKET_FX_PROVIDER` (`registry.py`). Chaque réponse porte `source`, `retrieved_at`,
`as_of`, `is_delayed` et `license_note` ; les erreurs sont typées (`MarketRateLimited`,
`MarketNotFound`, `MarketNotSupported`, `MarketMisconfigured`, `MarketUnavailable`).

Politique anti-abus commune (`http.py`, `service.py`) : budget local par fournisseur (seau à
jetons, `NEXORA_<PROVIDER>_RATE_LIMIT_PER_MINUTE`, refus immédiat → cache), cache-first
(`price_points`, `ohlc_bars`, `fx_rates` + caches mémoire courts), disjoncteur persistant
(`market_providers` : 3 échecs → pause 10 min ; `NEXORA_MARKET_AUTO_DISABLE_AFTER_FAILURES`
échecs → désactivation, réactivation manuelle par un administrateur), rafraîchissement en
arrière-plan limité aux instruments détenus/suivis. Les tests n'appellent jamais un fournisseur
réel (adaptateurs `fixture`/`null`, HTTP intercepté par `respx`).

### Yahoo Finance (`yahoo.py`, défaut pour actions/ETF/indices)

- **Type** : endpoints JSON publics du site (`/v1/finance/search`, `/v8/finance/chart/{symbol}`),
  sans clé ni cookie — **API non officielle**, non documentée.
- **Licence** : conditions de Yahoo : usage personnel et non commercial, pas de redistribution ;
  données souvent différées (15 min ou plus selon la place). Affiché à l'utilisateur via
  `license_note`/`attribution`. Peut cesser de fonctionner sans préavis → basculer vers
  `finnhub` ou `null`.
- **Quotas** : non publiés ; budget local de 20 requêtes/min par processus, bien en deçà des
  seuils observés ; `User-Agent` descriptif (`NEXORA_MARKET_USER_AGENT`).
- **Couverture** : recherche (EQUITY/ETF/INDEX/CURRENCY/CRYPTOCURRENCY), cotation
  (`regularMarketPrice`, `chartPreviousClose`), historique quotidien OHLCV (lignes nulles des
  jours fériés ignorées, jamais interpolées).

### CoinGecko (`coingecko.py`, défaut pour les crypto-actifs)

- **Type** : API publique v3 (`/search`, `/simple/price`, `/coins/{id}/market_chart`), sans clé ;
  clé « demo » optionnelle (`COINGECKO_API_KEY`, en-tête `x-cg-demo-api-key`).
- **Licence** : offre gratuite pour usage personnel/non commercial, attribution
  « Powered by CoinGecko » requise (affichée). Quotas partagés par IP (~10-30 appels/min,
  429 stricts) → budget local de 8 requêtes/min.
- **Couverture** : cotation et historique quotidien en USD (converti ensuite par la couche FX) ;
  le `market_chart` ne publie que des clôtures et volumes : barres sans open/high/low, tracées en
  ligne.

### Finnhub (`finnhub.py`, alternative pour les actions)

- Même clé et mêmes conditions que pour les actualités (section ci-dessus) ; `/search`, `/quote`,
  `/stock/profile2` gratuits ; `/stock/candle` restreint sur l'offre gratuite → signalé comme
  `not_supported`, jamais silencieux. Budget local 30 requêtes/min.

### Frankfurter — taux de référence BCE (`frankfurter.py`, défaut pour le change)

- **Type** : API open source sans clé (`https://api.frankfurter.dev/v1`), publiant les taux de
  référence quotidiens de la Banque centrale européenne.
- **Licence** : données BCE réutilisables avec attribution (affichée) ; un taux par jour ouvré,
  fixé vers 16:00 CET — un taux de référence, pas un cours négociable.
- **Usage** : séries entières récupérées d'un coup pour une paire et une période
  (`ensure_fx_series`), stockées dans `fx_rates` avec date et provenance ; un montant sans taux
  connu reste non converti.

### `fixture` / `null`

`fixture` (`tests/fixtures/market_data/demo_quotes.json`) : données synthétiques pour les tests et
le profil `demo` de docker-compose. `null` : aucune donnée de marché vivante (saisie manuelle
uniquement). Aucun des deux n'effectue de requête réseau.
