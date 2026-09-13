# NeXora — Dashboard multi-actifs

Une seule application (`specs/README.md`) pour suivre les marchés et un patrimoine multi-actifs :
actions, ETF, indices, crypto-actifs, obligations et actifs privés.

- **Marchés** : recherche de n'importe quel instrument coté (Yahoo Finance / Finnhub pour les
  actions et ETF, CoinGecko pour les crypto-actifs), fiche avec cotation datée et sourcée,
  chandeliers OHLCV, SMA/EMA/Bollinger/RSI/MACD/ATR/stochastique/OBV paramétrables, liste de
  suivi et **ajout au portefeuille en un clic** (enregistrement d'un achat — jamais un ordre).
- **Portefeuilles** : transactions immuables (annulation auditée), positions FIFO, coût de revient
  et plus-values latentes, valorisation dans la devise de référence avec taux de change BCE datés,
  **import des exports Trade Republic et Revolut** (format reconnu automatiquement, titres retrouvés
  par ISIN) ou de tout CSV (aperçu, mapping, erreurs par ligne, déduplication), historique,
  allocation, TWR/MWR, **plus-values réalisées (FIFO) et revenus/frais par année**, et un
  **patrimoine consolidé** de tous les portefeuilles dans la devise de référence.
- **Analyse** : statistiques de rendement et de risque (volatilité, Sharpe, Sortino, Calmar,
  asymétrie, kurtosis), drawdown, VaR/CVaR (historique, gaussienne, Cornish-Fisher), MEDAF (bêta,
  alpha, R²), matrice de corrélation, frontière efficiente de Markowitz, simulations de Monte
  Carlo, **étude de stratégie** (backtest pédagogique d'une règle SMA/RSI contre « acheter et
  conserver », signal appliqué le lendemain, frais inclus) et **comparaison base 100** — chaque
  mesure avec méthode, période et limites.
- **Actualités & événements** : actualités par société récupérées automatiquement (Finnhub, clé
  gratuite) pour chaque action ou ETF suivi, plus flux RSS/JSON/ICS configurables ; chronologie et
  calendrier, dédoublonnage et scoring.
- **Aide à la décision (un bouton)** : sur chaque fiche, une quinzaine de méthodes reconnues appliquées
  aux données disponibles — tendance (moyennes 50/200, golden cross), momentum 12 mois, RSI, MACD, Bollinger,
  fourchette 52 semaines, volatilité, pire repli, Sharpe, PER, P/B, dividende, croissance, ROE, marge, dette,
  consensus des analystes, bêta, prédiction expérimentale — chacune avec sa lecture (favorable / défavorable /
  neutre / indisponible), son explication en français simple, son seuil et son niveau de preuve ; comptées par
  horizon, jamais pondérées en verdict. **Bilan rapide** de tous les instruments suivis sur la page Marchés,
  **bilan de portefeuille** (concentration, diversification, corrélation, risque, écart à votre allocation cible).
  Fondamentaux via Finnhub (clé gratuite). Information, jamais conseil personnalisé ni exécution.
- **Alertes informatives** : seuil de cours ou variation quotidienne sur un instrument, évaluées
  sur les données en cache (jamais de requête supplémentaire), notification dans l'application —
  jamais un ordre.
- **Aide** : 27 articles sur la théorie derrière chaque chiffre (valorisation, FIFO, TWR/MWR,
  ratios, VaR, MEDAF, Markowitz, efficience des marchés, indicateurs techniques, walk-forward,
  métamodèles…), consultables depuis chaque écran.
- **Prédiction (expérimental, désactivé par défaut)** : entraînement d'un métamodèle (stacking de
  ridge, forêt aléatoire, gradient boosting, benchmark naïf) validé en walk-forward chronologique,
  avec intervalles calibrés et métriques hors échantillon — outil pédagogique, jamais un signal.

**Consultation et analyse uniquement. Aucun ordre financier, aucune recommandation personnalisée,
aucune exécution.**

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

- Application : http://localhost:5173 (le premier compte créé est administrateur)
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

## Suivre un compte Trade Republic ou Revolut

Ces courtiers n'offrent pas d'API de lecture pour un compte personnel ; les « connecteurs » non
officiels exigent vos identifiants et votre 2FA et donnent un accès complet au compte, ce que
`specs/PORTFOLIO_IMPORTS.md` et `specs/SECURITY.md` excluent. La voie retenue est l'export de
l'application (Revolut : relevé du compte titres en CSV ; Trade Republic : export des transactions
en CSV), importé dans NeXora : le format est reconnu d'après les colonnes, les types d'opération
sont convertis, les titres sont retrouvés par ISIN ou symbole, chaque ligne est vérifiée et rien
n'est écrit avant confirmation. Un nouvel export importé plus tard ne crée pas de doublons.

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
