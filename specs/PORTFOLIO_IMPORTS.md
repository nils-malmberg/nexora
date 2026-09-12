# Imports de portefeuille

## CSV V1
Colonnes recommandées : `date`, `type`, `symbol`, `asset_class`, `quantity`, `unit_price`, `currency`, `fees`, `account`, `external_id`. Types autorisés : achat, vente, dividende, coupon, dépôt, retrait, transfert, split, valorisation privée.

## Parcours
1. Upload chiffré et limitation de taille/type.
2. Détection séparateur, encodage, en-têtes et aperçu borné.
3. Mapping explicite vers le schéma canonique, devise et fuseau.
4. Validation ligne par ligne : date, décimales, signe, instrument et doublon.
5. Prévisualisation des effets ; confirmation explicite.
6. Job idempotent, rapport succès/avertissements/erreurs téléchargeable, suppression du fichier brut selon rétention.

## Règles
Ne pas déduire silencieusement une transaction ambiguë. Les ventes ne peuvent pas créer une quantité négative sans correction signalée. Les imports répétés utilisent `external_id` ou empreinte canonique. Chaque import est associé à un utilisateur, un portefeuille et un journal d’audit.

## Connecteurs optionnels
Ajouter par consentement, scopes minimaux, feature flag et révocation. Un connecteur en lecture seule ne doit jamais posséder de capacité d’ordre. Les tokens sont stockés dans un secret manager, chiffrés au repos, jamais exportés ni loggés.

## Confidentialité
Masquer comptes et identifiants dans l’interface et les logs ; permettre suppression des fichiers intermédiaires et export complet des transactions normalisées.
