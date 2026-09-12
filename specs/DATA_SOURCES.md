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
