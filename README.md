# NeXora — Analyse de marché et aide à la décision

Une seule application, sans compte à créer, pour qu'une personne qui débute puisse analyser un
titre comme sur un site de courtage — et comprendre ce qu'elle regarde. Actions, ETF, indices,
crypto-actifs.

- **« Acheter ou vendre ? » en un bouton** : une vingtaine de méthodes reconnues appliquées au titre
  (tendance, momentum, RSI, MACD, Bollinger, fourchette 52 semaines, volatilité, Sharpe ; PER, P/B,
  dividende, croissance, ROE, marge, dette, consensus d'analystes ; prédiction statistique), chacune
  avec sa lecture, son explication en français simple et son niveau de preuve. **Orientation par
  horizon** (court terme / long terme) avec **arguments pour acheter et pour vendre**, **niveaux pour
  agir** (stop de protection, objectif, gain/risque, stop suiveur, supports/résistances, taille de
  position selon le capital et le risque accepté), lecture **« conserver ou vendre »** si vous
  déclarez détenir le titre, et **test de la méthode sur le passé du titre** (« quand ce bilan disait
  achat, le cours était plus haut 20 jours après dans X % des cas », contre acheter n'importe quand).
- **Graphique et outils** : chandeliers / barres / ligne / aire, échelle log, volume, SMA, EMA,
  Bollinger, **Ichimoku, SAR parabolique, points pivots, retracements de Fibonacci, supports et
  résistances, figures de chandeliers** (chacun avec sa lecture), droites de tendance et niveaux
  tracés à la main, RSI, MACD, stochastique, ATR, OBV paramétrables, comparaison base 100.
- **Prédiction** : un clic entraîne un métamodèle (ridge, forêt aléatoire, gradient boosting) validé
  en walk-forward sur le passé du titre ; rendement attendu avec intervalle, précision de direction
  hors échantillon, test « suivre le modèle » contre « rester investi ». Laboratoire complet pour
  configurer horizons et modèles.
- **Étude de stratégie** (backtest d'une règle SMA/RSI contre acheter-conserver), **analyse
  quantitative** (Sharpe, VaR, drawdown, MEDAF, Monte Carlo), **actualités** par société (Finnhub),
  événements, **alertes** de cours, **liste de suivi** avec « je détiens ce titre ».
- **Aide** : 31 articles — chaque chiffre renvoie à la théorie et à ses limites.

**Information et pédagogie uniquement : aucun ordre n'est passé, aucune recommandation adaptée à
votre situation n'est donnée.** Les méthodes décrivent le titre ; la décision reste la vôtre.

> La gestion de portefeuille (transactions, imports Trade Republic/Revolut, plus-values, revenus,
> bilan de portefeuille) reste dans le code mais est **désactivée par défaut**
> (`NEXORA_PORTFOLIOS_ENABLED=false`) : trop lourde à alimenter sans connecteur. Réactivable.

## Structure

```
backend/     API FastAPI + worker (marché, portefeuille, analyse, actualités, prédiction, aide)
frontend/    Interface React/TypeScript unique, servie par nginx qui proxifie /api (même origine)
specs/       Spécifications produit de référence
```

## Démarrage rapide

```bash
cp .env.example .env          # ajustez au besoin ; jamais commité
docker compose up --build
```

- Application : http://localhost:5173 — aucun compte : une session locale s'ouvre toute seule
  (`NEXORA_SINGLE_USER=true`, pour une machine personnelle ou un réseau de confiance ; passez à
  `false` pour exiger des comptes, le premier créé étant administrateur)
- API : http://localhost:8000/docs · santé `/health` · métriques `/metrics` (worker : :9100)
- PostgreSQL : localhost:5432

Démo entièrement hors ligne (instrument synthétique, cotations et actualités fictives servies
localement, aucun appel externe) :

```bash
SEED_DEMO_DATA=1 NEXORA_MARKET_EQUITY_PROVIDER=fixture NEXORA_MARKET_CRYPTO_PROVIDER=fixture \
NEXORA_MARKET_FX_PROVIDER=fixture docker compose --profile demo up --build
```

> **Migration depuis les versions précédentes** : les deux services séparés (`backend` Actualités,
> `portfolio-backend` Portefeuille) et leurs bases `nexora` / `nexora_portfolio` sont remplacés par
> ce schéma unifié, sans chemin de migration automatique. Repartez d'un volume vide
> (`docker compose down -v`) puis relancez.

## Portefeuille (désactivé par défaut)

Avec `NEXORA_PORTFOLIOS_ENABLED=true`, l'application retrouve les portefeuilles, transactions,
imports d'exports Trade Republic/Revolut (aucun connecteur avec identifiants : voir
`specs/PORTFOLIO_IMPORTS.md`), plus-values réalisées, revenus et bilan de portefeuille. Sans cela,
« Je détiens ce titre » sur la liste de suivi (prix d'entrée facultatif) suffit à l'aide à la
décision pour parler de conserver ou vendre.

## Données de marché et respect des fournisseurs

Les fournisseurs sont interchangeables et configurés par variables d'environnement (voir
`.env.example` et `specs/DATA_SOURCES.md`). L'application est conçue pour ne jamais « spammer » une
API : cache-first (une cotation rafraîchie au plus toutes les 15 minutes), budget local de
requêtes par fournisseur, disjoncteur qui met en pause puis désactive une source défaillante,
rafraîchissement en arrière-plan limité aux instruments détenus ou suivis. Les tests n'effectuent
aucun appel réseau. Chaque donnée affichée porte sa source, son horodatage, son âge et sa note de
licence ; une donnée manquante est signalée, jamais inventée.

## Développement

```bash
cd backend && python3 -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]"
alembic upgrade head && uvicorn app.api.main:app --reload --port 8000
cd ../frontend && npm ci && npm run dev      # http://localhost:5173, proxy /api → :8000
```

CI (`.github/workflows/ci.yml`) : lint + tests unitaires, intégration + couverture (≥ 85 %),
migrations depuis zéro et retour arrière sur PostgreSQL, scans (gitleaks, bandit, pip-audit),
build Docker reproductible, typecheck + build du frontend. Détails : [`backend/README.md`](backend/README.md).

## Avertissement

Les cotations proviennent de fournisseurs tiers gratuits (usage personnel, données souvent
différées, pas de garantie de disponibilité ni de redistribution) ou de saisies manuelles. Les
valorisations d'actifs privés sont des estimations. Les analyses décrivent le passé ; les
simulations et le module de prédiction illustrent des hypothèses. Cet outil fournit de
l'information et de l'organisation — il ne constitue ni conseil financier, fiscal ou juridique,
ni service d'exécution.
