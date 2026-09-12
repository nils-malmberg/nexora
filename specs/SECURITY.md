# Sécurité, confidentialité et conformité

## Menaces
Fuite de secrets, prise de compte, IDOR entre portefeuilles, CSV malveillant, injection dans logs, fournisseur compromis, exposition de données patrimoniales et abus de quotas.

## Contrôles
OIDC/session sécurisée ou équivalent, MFA optionnelle puis renforcée, hash de mots de passe si utilisés, cookies HttpOnly/Secure/SameSite, CSRF, rate limiting, validation serveur, contrôle d’accès tenant-aware, chiffrement en transit et au repos, CSP et dépendances scannées.

## Secrets
Variables d’environnement en local ; secret manager en production. Aucun token, clé, cookie, export privé ou mot de passe dans Git, JSON versionné, fixtures, image Docker ou logs. Rotation, révocation et accès minimal. Les exemples utilisent des placeholders non réalistes.

## Données personnelles
Minimisation, consentement pour connecteurs, rétention documentée, export et suppression, sauvegardes avec politique d’effacement. Masquer montants/identifiants dans observabilité et environnements de test.

## Conformité
Faire valider juridiction, RGPD/équivalents, conservation, licences de marché, attribution et obligations liées aux actifs privés par un conseil compétent. Le produit ne fournit ni conseil financier ni exécution.

## Réponse à incident
Détecter → contenir → révoquer/faire tourner → préserver les preuves minimales → notifier selon obligations → corriger → post-mortem. Tester sauvegarde, restauration et procédure au moins périodiquement.
