# ADR-0024 : transition vers le backend Convex multi-tenant (#372)

**Statut** : acceptée

**Date** : 2026-08-11

**Auteur(s)** : Codex, sous direction de l'équipe WOURI

**Valideur** : Ouedraogo Issouf
**Lié à** : issue #372

---

## Contexte

WOURI est aujourd'hui un backend FastAPI/Python. Il sert les traitements lourds
ASR, TTS, NLU, DeepSeek et le corpus PostgreSQL + pgvector, pendant que le
serveur WhatsApp l'appelle avec une clé de service partagée. Il n'existe ni
organisation, ni membership, ni identité utilisateur vérifiée, ni isolation
tenant dans cette architecture.

La mission WOURI demande désormais un backend Convex multi-tenant pour l'état
métier, les conversations, les alertes, les sources, le feedback, l'audit et
les traces d'exécution. Cette décision entre en conflit avec l'ADR-0001, qui
avait choisi PostgreSQL comme magasin unique avant l'apparition de ce besoin.

## Décision

1. La cible est Convex comme magasin unique des nouveaux domaines métier
   multi-tenant, avec une séparation stricte des déploiements développement,
   staging et production.
2. FastAPI demeure le plan de calcul spécialisé. Il conserve ASR, TTS, NLU,
   appels LLM, conversion audio et les contrats historiques du serveur
   WhatsApp pendant la transition.
3. PostgreSQL + pgvector reste l'unique propriétaire du corpus IVR actuel
   jusqu'à une ADR de migration dédiée et des mesures d'équivalence. Aucun
   dual-write synchronisé n'est autorisé.
4. Chaque agrégat a un seul propriétaire et un seul writer à tout instant.
   Les migrations basculent un agrégat après backfill idempotent, réconciliation
   complète, shadow reads et rollback documenté.
5. Convex ne reçoit aucune donnée personnelle de production tant que la
   résidence, la rétention, l'export et l'effacement n'ont pas été validés.

## Frontière initiale

| Domaine | Propriétaire initial | Évolution prévue |
|---|---|---|
| ASR, TTS, NLU, LLM, audio | FastAPI | Reste service de calcul appelé par Convex ou le gateway |
| Corpus IVR et embeddings existants | PostgreSQL + pgvector | Migration séparée, jamais couplée à l'authentification |
| Organisations, memberships, entitlements | Aucun aujourd'hui | Convex après choix d'authentification et tests d'isolation |
| Conversations, alertes, sources, feedback, audit | Aucun durablement aujourd'hui ou fichiers locaux | Convex, agrégat par agrégat |
| Authentification utilisateur | Aucune | JWT OIDC, identité et membership vérifiés côté serveur |

## Contraintes obligatoires

- Une clé `X-API-Key` authentifie le service WhatsApp, pas un utilisateur ou
  une organisation. Elle ne doit jamais autoriser un accès tenant.
- Les `user_id` et `organizationId` fournis par un client ne constituent jamais
  une preuve d'identité. Les fonctions Convex obtiennent l'identité vérifiée,
  puis valident le membership et les permissions à chaque accès.
- Les fonctions publiques Convex restent minimales. Les opérations de données
  passent par des fonctions `internal*`; les appels FastAPI utilisent une
  passerelle de service dédiée et authentifiée.
- Les actions externes sont idempotentes. Les webhooks vérifient leur signature
  avant toute mutation.

## Gates avant le premier schéma Convex

- Choix et validation du fournisseur d'authentification, avec mapping stable
  entre sujet, organisation et identifiant WhatsApp.
- Matrice de propriété des données : portée tenant, classe PII, writer, durée
  de rétention, export et effacement pour chaque agrégat.
- Validation documentée de la résidence et des sous-traitants Convex.
- Threat model incluant IDOR, membership révoqué, changement d'organisation,
  replay et confused deputy.
- Tests négatifs cross-tenant définis avant toute fonction publique.

## Conséquences

- L'ADR-0001 est remplacée pour les nouveaux domaines multi-tenant après
  acceptation de cette ADR. Elle reste la référence du corpus PostgreSQL jusqu'à
  sa propre migration.
- `docs/vision.md` doit être amendée après acceptation : FastAPI n'est plus
  l'unique point d'entrée de l'état métier, mais reste le service de calcul.
- Le socle Convex et ses tests peuvent évoluer sur un déploiement anonyme sans
  donnée personnelle. Les gates restent obligatoires avant tout déploiement
  staging ou production, transfert de données ou exposition publique.

## Références

- Issue #372.
- `docs/vision.md` sections 3, 7 et 13.
- ADR-0001 et ADR-0008.
- Documentation Convex : functions, internal functions, HTTP actions, auth et
  environment variables.

## Historique

- 2026-08-11 : proposée dans la PR #373.
- 2026-08-11 : acceptée par Marcel dans l'issue #372.
