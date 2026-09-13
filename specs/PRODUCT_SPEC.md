# Spécification produit

## Vision
Offrir une vue fiable, explicable et privée d’un patrimoine multi-actifs, sans automatiser de décision ni d’exécution financière.

## Utilisateurs et objectifs
- **Particulier** : connaître positions, coût de revient, valeur et allocation.
- **Investisseur long terme** : comparer historique, contributions, performance et risque.
- **Administrateur** : gérer fournisseurs, rétention, santé et conformité.

## Périmètre V1
- Portefeuilles multiples et devise de référence configurable.
- Instruments : actions, ETF, crypto, obligations ; actifs privés saisis/importés manuellement avec valorisation datée et méthode explicite.
- Transactions achat, vente, frais, dividendes/coupons, dépôts/retraits, splits et mouvements internes.
- Prix historiques et dernier prix connu ; provenance, timestamp, devise, statut frais de change.
- Graphiques chandeliers et lignes, volume si disponible, SMA/EMA, RSI, MACD, volatilité et drawdown.
- Import CSV prévisualisé, mapping, validation, déduplication et rapport d’erreurs.
- Aide éducative contextuelle avec sources éditoriales versionnées.
- **Aide à la décision** : lectures génériques, sourcées et expliquées de méthodes reconnues (tendance, momentum,
  surachat/survente, ratios de valorisation et de qualité, consensus d’analystes, mesures de risque) pour un
  instrument, et bilan de structure (concentration, diversification, écart à une allocation cible définie par
  l’utilisateur) pour un portefeuille. Chaque lecture indique la méthode, le seuil, le niveau de preuve et ses
  limites ; les lectures sont comptées, jamais pondérées en verdict, et ne dépendent jamais de la situation de
  l’utilisateur. Alertes informatives (seuil de cours) dans l’application uniquement.
- Export des données utilisateur et suppression de compte.

## Hors périmètre V1
Passage d’ordres, recommandations personnalisées (« vous devriez acheter X »), signaux d’ordre automatisés,
levier, conservation de clés privées, scraping non autorisé, garantie de temps réel. La frontière : l’application
décrit un instrument ou un portefeuille avec des méthodes publiques et explique comment les lire ; elle ne
transforme jamais ces lectures en instruction adressée à une personne, et n’exécute rien.

## Règles métier
- Une transaction validée est immuable ; correction par événement compensatoire ou workflow d’annulation audité.
- Valeur = quantité × prix applicable + cash ; un prix absent est signalé, jamais inventé.
- Les actifs privés exigent `valuation_date`, `valuation_amount`, `valuation_method` et `confidence`.
- Toute performance indique méthode, période, devise et couverture des données.

## Critères d’acceptation
Un utilisateur peut créer un portefeuille, importer un CSV valide avec erreurs explicites, voir une valeur historisée et sa provenance, filtrer un graphique, consulter une explication non prescriptive, exporter ses données et supprimer son compte. Les tests doivent démontrer l’absence d’exécution d’ordres et de fuite temporelle du module prédictif.
