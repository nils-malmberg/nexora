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
- **⚠️ Constat opérationnel** : le domaine sec.gov est protégé par Akamai Bot Manager. Un test réel (User-Agent correct, en-têtes de type navigateur) a été bloqué (`403 "Your Request Originates from an Undeclared Automated Tool"`) malgré une politique écrite qui autorise l'accès automatisé. Ceci semble être une restriction technique (empreinte TLS/HTTP du client) indépendante de la conformité déclarative (User-Agent, cadence) — à tester depuis votre propre réseau avant de considérer la source pleinement opérationnelle. La légalité de la source n'est pas remise en cause, seule son accessibilité technique immédiate l'est.

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
