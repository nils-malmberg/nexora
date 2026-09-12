# Dashboard multi-actifs

## Objet
Dashboard personnel et extensible pour suivre actions, ETF, crypto-actifs, obligations et actifs privés, avec valorisation, historique, graphiques et aide éducative. **V1 : consultation et analyse uniquement, aucun passage d’ordre.**

## Principes
- Fournisseur par défaut gratuit de type Yahoo Finance, derrière une interface `MarketDataProvider` remplaçable.
- Import CSV contrôlé et connecteurs optionnels ; chaque donnée porte sa source, son horodatage et son niveau de fraîcheur.
- Les cours temps réel dépendent des fournisseurs, de leurs licences et de leurs limites. Cible indicative : rafraîchissement de 15 minutes lorsque la source le permet.
- L’aide explique les concepts sans recommandation personnalisée ni promesse de rendement.
- Secrets uniquement via variables d’environnement, coffre de secrets ou secret manager ; jamais dans un JSON versionné.

## Démarrage de développement
1. Lire `PRODUCT_SPEC.md`, `ARCHITECTURE.md` et `SECURITY.md`.
2. Copier le fichier d’exemple de configuration prévu par l’implémentation, sans y mettre de valeur sensible.
3. Démarrer les services avec Docker en environnement local, appliquer les migrations, puis lancer les tests.
4. Importer un petit CSV de démonstration non sensible et vérifier la provenance des données.

## Documentation
| Besoin | Document |
|---|---|
| Périmètre et critères | `PRODUCT_SPEC.md` |
| Modules et déploiement | `ARCHITECTURE.md` |
| Sources et licences | `DATA_SOURCES.md` |
| CSV et connecteurs | `PORTFOLIO_IMPORTS.md` |
| Graphiques et métriques | `ANALYTICS_AND_CHARTS.md` |
| Modèles expérimentaux | `PREDICTION.md` |
| Menaces et contrôles | `SECURITY.md` |
| Contrat HTTP | `API_SPEC.md` |
| Parcours d’interface | `UX_SPEC.md` |
| Qualité et CI | `TESTING.md` |
| Phases | `ROADMAP.md` |
| Contribution | `CONTRIBUTING.md` |
| Exécution CloudCode | `CLOUDCODE_PROMPT.md` |

## Limites et avertissement
Les cotations peuvent être différées, incomplètes ou indisponibles. Les valorisations d’actifs privés et obligataires sont souvent estimées. Ce produit est un outil d’information et d’organisation, pas un service de conseil financier, fiscal ou juridique.
