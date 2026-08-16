# Socle Convex WOURI

**Statut** : développement uniquement, sans donnée métier ni donnée personnelle.

Ce document rend le socle Convex reproductible et fixe ses frontières avec les
services existants. Il complète l'ADR-0024.

## Environnements

| Environnement | Projet Convex | Usage autorisé |
| --- | --- | --- |
| Développement | `wouri`, déploiement de développement personnel | Schéma, tests anonymes et authentification locale |
| Staging | `wouri-staging` | Réservé, aucun déploiement applicatif ni donnée personnelle avant les gates |
| Production | `wouri`, déploiement production | Réservé, aucune donnée ni exposition publique avant les gates |

Les valeurs `BETTER_AUTH_SECRET` et `SITE_URL` sont configurées sur le seul
environnement de développement. Elles ne doivent jamais être mises dans Git,
un ticket, une issue ou une documentation.

## Démarrage local

```powershell
pnpm install --frozen-lockfile
pnpm exec convex dev
```

Convex crée ou met à jour `.env.local`. Ce fichier est local et ignoré. Pour
vérifier un changement sans processus long :

```powershell
pnpm exec convex dev --once --tail-logs disable
pnpm exec tsc --noEmit -p convex/tsconfig.json
pnpm test:convex
```

Après une modification des plugins ou des champs Better Auth, régénérer le
schéma local puis redéployer le développement :

```powershell
pnpm dlx @better-auth/cli@latest generate --config ./convex/betterAuth/auth.ts --output ./convex/betterAuth/schema.ts --yes
pnpm exec convex dev --once --tail-logs disable
```

## Frontières de propriété

Better Auth local est propriétaire des utilisateurs, sessions, organisations,
membres et invitations. Les tables WOURI complètent cette base avec les
politiques de rôles, grants de périmètre, entitlements, agriculteurs,
conversations, alertes, provenance et actifs linguistiques.

La création d'organisation par un utilisateur est désactivée. Lorsqu'un
workflow d'opérateur crée une organisation Better Auth, le trigger Convex crée
son profil WOURI dans l'état `provisioning`, sans politique ni permission. Une
organisation n'est activée qu'après configuration explicite de son profil, de
ses politiques et des assignments de rôles. Ce séquencement empêche qu'une
organisation ou un membre nouvellement créé reçoive des droits implicites.

L'email/password est disponible uniquement pour le développement local et sans
vérification d'email. Staging et production gardent ce mécanisme désactivé tant
qu'un fournisseur d'envoi, son callback de vérification et les origins de
confiance n'ont pas été validés.

FastAPI reste propriétaire du calcul, notamment ASR, TTS, NLU, LLM et audio.
PostgreSQL et pgvector restent propriétaires du corpus IVR existant jusqu'à une
décision de migration séparée. Aucune écriture double n'est admise entre ces
magasins.

## Règles d'autorisation

`authorize(ctx, requirement)` est l'unique garde métier. Il vérifie la session
Better Auth, l'appartenance active, la politique WOURI, le périmètre
zone/culture/groupe et, si demandé, l'entitlement encore valide.

Une organisation choisie dans une session n'est qu'un repère de routage. Les
fonctions dérivent toujours l'organisation depuis le document stocké ou la
session validée côté serveur. Une fonction publique ne doit jamais autoriser à
partir d'un `userId`, `organizationId`, `farmerId` ou `threadId` fourni par le
client.

Les refus restent volontairement non divulguants : un identifiant d'une autre
organisation ne confirme jamais son existence.

## Gates avant staging ou production

1. Validation documentée de la résidence, sous-traitance, rétention, export et
   effacement.
2. Choix du fournisseur de facturation, contrat de webhooks signés et replay
   idempotent.
3. Mapping canonique WhatsApp vers agriculteur, avec règles de réattribution.
4. Politique de rétention des messages, mémoires et médias.
5. Tests négatifs inter-organisations verts, y compris révocation de membre,
   périmètre vide, entitlement expiré et rejeu de callback.
6. Runbook de migration par agrégat : writer unique, shadow read,
   réconciliation et rollback vérifié.
