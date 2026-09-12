# Actualités et événements

## Objectif et périmètre

Ce module enrichit le dashboard d’investissement avec des informations **sourcées, datées et contextualisées** pour chaque actif suivi. Il couvre :

- les actualités récentes par actif, sans prétendre à l’exhaustivité ;
- une chronologie historique contextualisée par période ou date ;
- les événements à venir : assemblées générales, résultats, dividendes, coupons, maturités, splits, annonces d’émetteurs et échéances réglementaires lorsque la source les publie.

Le module n’exécute jamais d’ordre financier et ne constitue ni conseil ni recommandation d’investissement.

## Contrat éditorial : faits, synthèse, prédiction

Chaque élément affiché doit indiquer explicitement son type :

- **Fait** : information attribuée à une source, avec date de publication et, si distincte, date/heure de l’événement.
- **Synthèse** : résumé court produit par le système à partir d’un ou plusieurs faits ; il doit renvoyer aux sources utilisées et ne pas ajouter d’information non étayée.
- **Prédiction/estimation** : contenu optionnel, séparé visuellement, avec méthode, hypothèses, horizon, incertitude et avertissement. Une estimation de calendrier ne doit jamais être présentée comme une annonce confirmée.

Un item comporte au minimum : `asset_id`, titre, type, résumé, URL/citation, fournisseur et provenance, date de publication, date de l’événement (ou `null`), fuseau horaire, niveau de confiance, langue, date de collecte et statut de vérification. Les dates inconnues restent inconnues ; elles ne sont pas déduites silencieusement.

## Vue fonctionnelle

### Actualités récentes par actif

Pour chaque actif, afficher une liste filtrable et paginée des faits et synthèses récents, avec : titre, source, date de publication, date de l’événement, indicateur de confiance, catégorie (résultats, dividende, réglementation, opération sur titre, gouvernance, marché, macro, autre) et lien vers la source. La fenêtre de fraîcheur est configurable ; elle doit être affichée à l’utilisateur et ne doit pas masquer les corrections ou mises à jour importantes.

### Chronologie historique contextualisée

La chronologie mélange événements passés et actualités liées à l’actif, triés par date d’événement puis date de publication. Elle permet de changer la granularité (jour, mois, trimestre, année), de filtrer par catégorie et d’ouvrir les sources. Les éléments sans date d’événement sont signalés et positionnés selon leur date de publication, sans réécriture de la date d’origine.

### Événements à venir

Afficher le calendrier dans le fuseau choisi par l’utilisateur, avec statut `confirmé`, `prévisionnel`, `reporté`, `annulé` ou `inconnu`. Exemples de champs : type, date/heure ou période, zone géographique, valeur concernée, montant et devise lorsqu’ils sont publiés, source, dernière vérification et date de mise à jour. Les événements expirés restent consultables dans l’historique ; les changements doivent être traçables.

## Pipeline de collecte et traitement

1. **Collecte** : adaptateurs récupérant RSS/Atom, APIs de news ou de marchés, calendriers officiels d’émetteurs et de places, et fournisseurs configurables. Respecter authentification, pagination, cache, délais et limites de débit de chaque fournisseur.
2. **Normalisation** : convertir les formats vers un schéma interne, normaliser identifiants d’actifs, dates, fuseaux, devises, catégories, langue et URL canonique ; conserver le payload brut minimal nécessaire à l’audit et une empreinte.
3. **Déduplication** : regrouper les copies et mises à jour au moyen d’une clé fournisseur/identifiant, URL canonique, empreinte de contenu et similarité prudente. Ne pas supprimer une source indépendante : les relations `duplicate_of` et `corroborates` doivent rester consultables.
4. **Scoring de pertinence** : calcul configurable fondé notamment sur correspondance d’actif, proximité temporelle, catégorie, importance de l’événement, qualité de la provenance et corroboration. Le score est explicable et n’est pas une note d’investissement.
5. **Résumé** : générer un résumé extractif ou contrôlé, limité au contenu disponible, avec liens vers toutes les sources utilisées. En cas d’échec, conserver le titre/extrait fourni par la source plutôt que d’inventer.
6. **Affichage** : servir les données normalisées via API, avec état de fraîcheur, provenance, confiance, filtres, pagination, reprise sur erreur et indication claire des contenus absents ou dégradés.

## Architecture et résilience

- Définir une interface d’adaptateur interchangeable (`fetch`, `normalize`, `health`, capacités et limites), sans coupler le domaine à un fournisseur particulier.
- Configurer les fournisseurs par environnement et par marché ; aucun compte, clé ou fournisseur n’est codé en dur.
- Utiliser un cache avec TTL par type de donnée, persistance locale et horodatage de dernière réussite. Prévoir index par actif, date et empreinte, ainsi qu’une stratégie d’invalidation.
- En cas de source indisponible, continuer à servir le dernier cache marqué comme tel, les autres fournisseurs et les événements déjà connus ; exposer l’état de fraîcheur et l’erreur sans écraser les données valides.
- Prévoir retries bornés avec backoff, circuit breaker, idempotence, quotas par fournisseur et tâches asynchrones pour ne pas bloquer le dashboard.
- Ne pas utiliser Google AI/Search comme dépendance unique. Les flux RSS, APIs autorisées, calendriers officiels et fournisseurs configurables doivent pouvoir fonctionner indépendamment.
- Par défaut, ne pas faire de scraping fragile. Toute source doit être utilisée conformément à ses droits d’accès, robots et CGU.

## Sources et conformité

Sources légitimes possibles : flux RSS/Atom publiés par émetteurs ou médias, APIs de news/marchés sous licence ou avec quota, calendriers officiels d’émetteurs et de places, dépôts/annonces réglementaires officiels selon la juridiction, et fournisseurs configurables validés par l’administrateur. La liste réelle dépend des marchés couverts et des licences obtenues ; elle doit être documentée par fournisseur.

Ne pas copier intégralement les articles : conserver au plus les métadonnées, un extrait permis par la licence et un résumé original. Afficher le nom de la source, l’auteur si disponible, les dates, la citation/lien et les conditions applicables. Respecter droits d’auteur, attribution, robots.txt lorsqu’applicable, CGU, restrictions de redistribution et demandes de retrait. Protéger les clés API dans le gestionnaire de secrets ; ne jamais les journaliser, les exposer au navigateur ou les committer. Minimiser les données personnelles, chiffrer les secrets en transit/au repos et appliquer rétention, contrôle d’accès et audit. Respecter les rate limits et prévoir une alerte de dépassement.

## Modèle de données minimal

```text
Asset                 id, symbol, isin/ticker optionnel, marché, devise
Provider              id, nom, type, licence/conditions, enabled, capabilities
NewsItem              id, asset_ids[], provider_id, kind, category, title, excerpt,
                      summary, publication_at, event_at, timezone, url, citation,
                      provenance, confidence, relevance_score, language,
                      collected_at, updated_at, freshness, status, content_hash
Event                 id, asset_id, type, starts_at/period, timezone, status,
                      amount/currency optionnels, source_ids[], last_verified_at
IngestionRun          id, provider_id, started_at, ended_at, status, counts,
                      error_code, latency_ms
```

Les relations de correction, doublon, corroboration et historique de statut sont conservées. Les timestamps sont stockés en UTC avec le fuseau d’affichage séparé.

## API et UX

Endpoints indicatifs : `GET /assets/{id}/news`, `GET /assets/{id}/timeline`, `GET /events/upcoming`, `GET /providers/status`, et une route d’administration protégée pour les synchronisations. Supporter filtres par actif/catégorie/date/type, pagination stable, tri, `ETag` ou `If-Modified-Since`, limites explicites, erreurs structurées et indicateur `stale`.

L’interface doit :

- distinguer visuellement fait, synthèse et prédiction ;
- montrer source, lien, provenance, dates de publication/événement, confiance et dernière collecte ;
- afficher les fuseaux et dates inconnues sans ambiguïté ;
- signaler cache obsolète, fournisseur en panne, absence de données et conflits entre sources ;
- permettre recherche, filtres, expansion du détail, ouverture de la source, export des métadonnées et suppression/masquage local ;
- rester utilisable au clavier, responsive, lisible par lecteur d’écran et correcte en mode sombre si celui-ci existe.

## Tests, fixtures et observabilité

Tests unitaires : parsing RSS/Atom et API, normalisation des dates/fuseaux et identifiants, déduplication, scoring explicable, résumé sans hallucination, transitions de statut, droits de visibilité et redaction des secrets. Tests d’intégration : adaptateur simulé, pagination, rate limit, timeout, retry/circuit breaker, cache chaud/froid, perte d’un fournisseur, données contradictoires et reprise idempotente.

Utiliser des fixtures versionnées et anonymisées couvrant publication sans événement, événement futur, correction, doublon, contenu multilingue, dates avec DST, devise absente, XML invalide et réponse fournisseur incomplète. Aucun test ne dépend d’un service externe en direct par défaut.

Mesurer et alerter sur : succès/échec par fournisseur, fraîcheur par actif, latence, volume collecté/normalisé/dédupliqué, taux de champs manquants, taux de doublons, erreurs de parsing, cache hit ratio, âge maximal servi et décalage entre date de collecte et publication. Corréler les logs par `ingestion_run_id`, sans titre sensible ni clé API, et fournir des métriques et traces suffisamment agrégées pour diagnostiquer sans divulguer de données sous licence.

## Critères d’acceptation

- Un actif peut afficher actualités récentes, chronologie et événements futurs avec liens, provenance, confiance et dates distinctes.
- Les données passent par collecte, normalisation, déduplication, pertinence, résumé et affichage ; chaque étape est observable et testée.
- Au moins deux adaptateurs conceptuellement interchangeables et un cache local permettent un fonctionnement dégradé documenté lorsqu’une source disparaît.
- Aucun fournisseur exclusif, clé réelle, résultat externe ou ordre financier n’est requis pour installer ou tester le module.
- Les textes protégés ne sont pas reproduits intégralement ; licences, robots/CGU, quotas et sécurité des secrets sont documentés.
- Les fixtures et tests couvrent les erreurs de source, dates/fuseaux, doublons, corrections et absence de données.
- La documentation explique les champs, l’API, les limites UX et les procédures de reprise.
