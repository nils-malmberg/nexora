# Analytics et graphiques

## Valorisation
Rejouer transactions et événements dans l’ordre ; calculer positions, cash, prix convertis et valeur totale à une date. Afficher devise, timestamp, prix manquant, estimation privée et âge de chaque donnée.

## Performance
V1 : rendement pondéré dans le temps (TWR) et rendement pondéré par l’argent (MWR/IRR) avec définition affichée. Inclure dépôts/retraits et frais ; ne pas comparer des séries de couverture différente sans avertissement.

## Risque descriptif
Volatilité annualisée, drawdown maximum, concentration par classe/instrument/devise, corrélation seulement si couverture suffisante. Ces métriques décrivent le passé et ne constituent pas des recommandations.

## Graphiques
Chandeliers OHLC, volume, ligne de valeur, allocation empilée, drawdown et performance. Fenêtres 1S/1M/3M/1A/Depuis début ; zoom et export CSV. Indicateurs : SMA/EMA, RSI, MACD, avec paramètres visibles et aucune alerte prescriptive.

## Exactitude
Utiliser décimal/arrondi d’affichage séparé du calcul ; tests sur splits, dividendes, fuseaux, crypto 24/7, obligations et valorisations privées. Réponses paginées, agrégation côté serveur, cache versionné et marqueur “données incomplètes”.
