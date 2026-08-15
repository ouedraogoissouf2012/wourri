# ADR-0013 — Durcissement du déploiement SSH (3 options à arbitrer)

**Statut** : accepté (addendum 2026-08-15)
**Date** : 2026-05-30 — addendum 2026-08-15
**Auteur** : Claude (sous direction Ruben)
**Valideur** : Ruben — addendum Dokploy 2026-08-15

---

## Addendum 2026-08-15 — la cible Scaleway n'existe plus

**[ADR-0024](0024-deploiement-wourri-dokploy.md) (accepté)** a changé la cible
de production : VPS Contabo + **Dokploy** (build Git sur le serveur), pas une
VM Scaleway + `appleboy/ssh-action`.

Conséquence pour #221 :

- Le risque B1 (clé SSH CI → `wourri@vm` Scaleway) **ne s'applique plus au
  chemin prod**. Dokploy clone le repo et build ; il n'y a pas de job CI qui
  SSH pour déployer.
- `deploy-api.yml` existe encore mais le job SSH est **gated**
  (`DEPLOY_API_ENABLED`). Tant que cette variable n'est pas `true`, le
  workflow ne fait que build+push GHCR. **Ne pas l'activer** : ce serait
  réintroduire le risque B1 sur une cible obsolète.
- Le risque restant est **l'accès admin humain** (`marcel@` Contabo / UI
  Dokploy), pas le pipeline CI. Tailscale reste une option *admin*, pas un
  prérequis pour déployer.

### Option D — Dokploy-native (héritée d'ADR-0024) — **retenue**

- **Description** : le déploiement prod = Dokploy. Pas de self-hosted runner
  pour déployer. Pas de Tailscale dans le chemin CI. Pas d'OIDC Scaleway.
- **Avantages** : zéro clé SSH CI sur le chemin réel ; pas de runner à
  maintenir ; aligné sur l'infra déjà en place.
- **Inconvénients assumés** : `deploy-api.yml` legacy reste dans le repo
  (inactif sans flag). Accès admin serveur = SSH/Dokploy classiques (hors
  #221).
- **Travail induit** : documenter ici + dans #221. Ne pas implémenter A/B/C.
- **Rollback** : aucun — c'est l'état déjà en prod.

Les options A/B/C ci-dessous restent la **trace 2026-05** (Scaleway). Elles
ne doivent plus être exécutées telles quelles.

---

## Contexte (historique 2026-05-30)

### Déclencheur

Sprint I.c.1 review SÉCURITÉ BLOCKER B1 (long terme) — PR #212. Documenté dans
l'issue [#221](https://github.com/ouedraogoissouf2012/wourri/issues/221).

Le pipeline de déploiement actuel (`/.github/workflows/deploy-api.yml` et
`deploy-wa.yml`) utilise `appleboy/ssh-action` pour exécuter des commandes
sur la VM Scaleway. Cette action exige une **clé SSH sans passphrase**
(les jobs CI sont non-interactifs et ne peuvent pas répondre à un prompt).

### Risque

Si l'organisation GitHub `ouedraogoissouf2012` est compromise (token PAT
leak, fuite de secret par un fork malveillant, compromission d'un workflow
réutilisé, employé interne malveillant chez Anthropic / GitHub / un
prestataire), l'attaquant obtient un accès `wourri@vm` équivalent au CI.

La clé est restreinte côté `authorized_keys` de la VM via une directive
`command="..."` qui limite ce que l'attaquant peut faire, mais cela reste
une **clé statique vivant dans GitHub Secrets**, indéfiniment, sans
rotation automatique.

### Ce qui a changé / Pourquoi décider maintenant

- **Mitigation court terme livrée** (PR #212) : clé SSH dédiée CI, rotation
  90j documentée, restrictions `authorized_keys` (`from=`, `command=`,
  `no-pty`, `no-port-forwarding`, etc.). Cf. `docs/deployment.md` §SSH CI
  hardening.
- **Mitigation long terme = cet ADR**. Pas urgent (mitigation court terme
  réduit la surface), mais à décider pour ne pas accumuler la dette
  sécurité indéfiniment.
- **Synergie avec ADR-0015 ARTCI** (à venir, issue #215) : un système
  d'authentification audité (Tailscale ou OIDC) facilitera le tracing
  PII demandé par la conformité ARTCI Côte d'Ivoire.

### Contexte projet

- **Wourri** est un bot WhatsApp agricole en pré-production. 1 développeur
  principal (Ruben). Pas d'équipe ops dédiée.
- VM cible : Scaleway DEV1-M (4 GB RAM, 1 IP publique).
- Volume CI : ~1-3 déploiements/jour en pré-prod, ~1/semaine attendu en
  prod stable.
- Budget : projet bootstrappé, contrainte coût forte. Toute option
  payante doit justifier le ROI face à la mitigation court terme.

---

## Questions à trancher

1. **Quelle option de hardening retenir parmi les 3 ?** (self-hosted
   runner / Tailscale SSH / Scaleway OIDC)
2. **Quel timing ?** (maintenant, post-présentation, ou Sprint J
   déploiement staging)
3. **Quel critère acceptable de coût opérationnel ?** (la solution doit
   rester soutenable par 1 développeur, sans ops dédié)
4. **Quel critère acceptable de coût financier ?** (free tier
   indispensable pour le projet bootstrappé actuellement)

---

## Options étudiées

### Option A — Self-hosted runner GitHub Actions

**Description courte** : héberger un **runner GitHub Actions sur la VM
Scaleway elle-même**. Le workflow `deploy-api.yml` ne SSH plus du tout —
les jobs s'exécutent en local sur la VM, donc l'accès aux fichiers /
services Docker est direct.

**Implémentation** :
1. Provisionner un user dédié `gha-runner` sur la VM (UID/GID non-root)
2. Installer le binaire runner GitHub
   (https://github.com/actions/runner/releases)
3. Enregistrer le runner via PAT GitHub avec scope minimal (`repo:status`,
   `repo_deployment`)
4. Lancer le runner comme service systemd
5. Migrer `deploy-api.yml` : `runs-on: [self-hosted, wourri-prod]` au
   lieu de `runs-on: ubuntu-latest`
6. Supprimer toute action SSH, exécuter `docker compose pull && docker compose up -d` en local

**Avantages** :
- **Zéro SSH** : pas de clé statique, pas de port 22 exposé au CI
- **Audit GitHub natif** : tous les jobs apparaissent dans l'UI GitHub
  Actions avec logs complets
- **Performance** : pas de transfert d'image Docker via SSH (la VM pull
  GHCR directement), pas de latence réseau

**Inconvénients** :
- **Maintenance runner** : applique les security updates du runner
  régulièrement (releases ~2x/mois), monitoring de l'uptime du service
  systemd
- **Isolation jobs/host compromise** : tout job qui tourne sur ce runner
  a accès à tous les secrets de la VM (Docker socket, fichiers env, etc.).
  Risque si un workflow malveillant est triggered (compromis fork, ou
  pull request d'attaquant). Mitigation possible : restreindre les
  triggers (pas de runs sur PRs externes).
- **Persistance secrets entre jobs** : un runner self-hosted n'est PAS
  jetable comme un GitHub-hosted runner. Si un job pollue
  l'environnement (variables shell, cache disque), ça persiste pour le
  prochain. Discipline `clean-up steps` obligatoire.
- **Risque single point of failure** : si la VM crash, le runner aussi
  → impossible de redéployer pour réparer la VM. Solution : un 2e runner
  d'urgence sur une autre machine (ramène la complexité ops).

**Coût** :
- **Financier** : 0 € (utilise la VM existante)
- **Temps mise en oeuvre** : ~4-6h (setup runner + migration workflow +
  test E2E)
- **Maintenance** : ~30 min/mois (updates + monitoring)
- **Verrou futur** : moyen — peut être démonté facilement, mais migration
  vers GitHub-hosted ultérieure nécessite de réintroduire un mécanisme
  SSH ou OIDC

**Compatibilité contraintes projet** :
- ❌ Compromet l'isolation jobs/host (risque si compromission GitHub)
- ✅ Pas de dépendance externe payante
- ⚠️ Ops mature requis (1 dev solo = risque oubli updates runner)

---

### Option B — Tailscale SSH

**Description courte** : remplacer SSH classique par **Tailscale SSH**
(connexion WireGuard authentifiée via OAuth GitHub). Plus de clé SSH
statique : chaque session ouvre un tunnel WireGuard éphémère, authentifié
contre l'identité GitHub de la machine appelante (le runner GitHub
Actions hébergé).

**Implémentation** :
1. Créer compte Tailscale (gratuit jusqu'à 100 devices, comptes
   GitHub/Google/Microsoft acceptés)
2. Installer Tailscale sur la VM Scaleway, autoriser SSH via
   `tailscale up --ssh`
3. Configurer une **ACL Tailscale** qui autorise les machines tagguées
   `tag:ci` à SSH vers la VM tagguée `tag:wourri-prod` pour le user
   `wourri`
4. Générer une **auth-key Tailscale réutilisable + ephemeral** (devices
   créés disparaissent automatiquement après usage)
5. Modifier `deploy-api.yml` : ajouter `tailscale/github-action@v2`
   avec l'auth-key en secret, puis `ssh wourri@wourri-vm` (résolu via
   MagicDNS Tailscale, pas d'IP publique nécessaire)
6. Optionnel : **fermer le port 22 public** sur le firewall Scaleway
   (l'accès SSH passe désormais par WireGuard sur port UDP)

**Avantages** :
- **Zéro clé SSH statique** : auth-key Tailscale rotative, ephemeral
- **Audit logs centralisés** : Tailscale logge chaque connexion SSH avec
  l'identité GitHub utilisée (auditable dans le dashboard Tailscale +
  syslog VM)
- **Fermeture port 22 public** possible → réduit la surface d'attaque de
  toute la VM (pas que CI)
- **Synergie ARTCI** (issue #215) : les logs Tailscale fournissent un
  audit trail des accès à la VM, utile pour la conformité
- **Pas de runner à maintenir** : on garde `ubuntu-latest` GitHub-hosted
  → updates automatiques, isolation jetable
- **Mise en oeuvre rapide** : ~2-3h (vs 4-6h pour self-hosted)

**Inconvénients** :
- **Dépendance Tailscale** (vendor lock léger) : si Tailscale a une panne
  ou augmente ses prix au-dessus du free tier, on doit migrer. Mitigation :
  on peut TOUJOURS garder une clé SSH backup pour accès admin manuel.
- **Tailscale est un service tiers** : auth via leur infrastructure
  d'identité (basée sur OAuth des grands providers). Si compromission
  Tailscale (peu probable mais possible), impact sur sécurité réseau.
- **Auth-key Tailscale dans GitHub Secrets** : on remplace une clé SSH
  par une auth-key Tailscale. La clé est tout de même mieux : courte
  durée de vie (auth-key configurée comme ephemeral + reusable, expire
  par défaut à 90j) + audit + révocation centralisée vs SSH bricolé.

**Coût** :
- **Financier** : 0 € jusqu'à 100 devices (Wourri = 1 VM + N runners
  ephemeral = bien en dessous). Plan payant à ~5-10$/mois si on
  dépasse, mais aucun risque court terme.
- **Temps mise en oeuvre** : ~2-3h (install + ACL + workflow update +
  test E2E)
- **Maintenance** : ~5 min/mois (Tailscale gère les updates de son agent
  via apt/systemd unattended)
- **Verrou futur** : faible — Tailscale est ouvert (basé sur WireGuard
  upstream, protocole standard), on peut self-host avec Headscale en cas
  de migration. Migration retour à SSH classique = trivial (revert
  workflow).

**Compatibilité contraintes projet** :
- ✅ Free tier compatible projet bootstrappé
- ✅ Ops minimal (1 dev solo soutenable)
- ✅ Synergie ARTCI (audit logs)
- ⚠️ Dépendance externe (mitigée par possibilité Headscale + clé SSH
  backup)

---

### Option C — Scaleway OIDC + IAM (workload identity)

**Description courte** : authentification GitHub Actions → Scaleway via
**JWT court (15 min) signé par GitHub**, sans aucune clé persistante.
GitHub Actions fournit nativement un JWT OIDC à chaque job, qu'on échange
contre un token Scaleway temporaire via leur API IAM. Le workflow utilise
ce token pour appeler l'API Scaleway (ex: `scw instance ssh`, ou bien
docker push GHCR + un trigger Scaleway pour redéployer).

**Implémentation** :
1. **Vérifier que Scaleway supporte OIDC pour GitHub Actions** (TODO :
   à confirmer dans la doc Scaleway, [IAM federated identity](https://www.scaleway.com/en/docs/identity-and-access-management/iam/))
2. Configurer une **policy IAM Scaleway** qui autorise un JWT GitHub
   (issuer `https://token.actions.githubusercontent.com`, audience =
   Scaleway, sub = `repo:ouedraogoissouf2012/wourri:ref:refs/heads/APIPy`)
   à exécuter `scw instance ssh` ou un script de déploiement
3. Modifier `deploy-api.yml` : utiliser `id-token: write` pour récupérer
   le JWT, échanger via `scw login` ou API IAM, exécuter les commandes
   de déploiement
4. Supprimer la clé SSH et les secrets GitHub correspondants

**Avantages** :
- **Zéro secret long-terme** : pas de clé SSH, pas d'auth-key Tailscale.
  Le JWT vit 15 min, signé par GitHub, vérifié par Scaleway.
- **Modèle "industrie 2026"** : c'est le pattern recommandé AWS / GCP /
  Azure (workload identity federation), Scaleway le supporte
  potentiellement aussi.
- **Audit logs IAM natifs** : Scaleway IAM logge chaque appel API avec
  l'identité GitHub vérifiée.
- **Granularité** : la policy IAM peut restreindre par repo / branche /
  workflow (ex: seul `APIPy` peut déployer en prod, pas les PRs)

**Inconvénients** :
- **À vérifier : Scaleway supporte-t-il OIDC GitHub Actions ?** Pas sûr
  en l'état actuel de leur doc (2026-05). Si non, **cette option est
  bloquée** jusqu'à ce que Scaleway le supporte.
- **Pas de SSH direct** : on ne `ssh wourri@vm` plus du tout. Le
  déploiement doit passer par l'API Scaleway (`scw instance ssh` qui
  est un wrapper API, ou un mécanisme de redéploiement Scaleway-natif
  type Serverless Functions / Kubernetes). Migration plus invasive que
  Tailscale.
- **Verrou vendor Scaleway** : la policy IAM est spécifique Scaleway.
  Migration vers OVH/AWS/Hetzner = réécriture du mécanisme d'auth.

**Coût** :
- **Financier** : 0 € (IAM Scaleway inclus dans les comptes)
- **Temps mise en oeuvre** : ~6-10h (recherche doc Scaleway + setup IAM
  + refactor workflow déploiement + tests) — **incertain** car dépend du
  support OIDC réel
- **Maintenance** : ~0 (pas de secret à roter)
- **Verrou futur** : élevé — verrou Scaleway, mais aligné sur les
  meilleures pratiques industrie

**Compatibilité contraintes projet** :
- ✅ Free, gracieux long terme
- ⚠️ Implementation complexe et incertaine (dépend support Scaleway)
- ❌ Verrou vendor Scaleway le plus fort des 3 options

---

## Comparatif

| Critère | A (Self-hosted) | B (Tailscale) | C (Scaleway OIDC) |
|---|---|---|---|
| **Sécurité (suppression clé statique)** | ✅ Aucune clé | ✅ Auth-key ephemeral 90j | ✅✅ Aucun secret long-terme |
| **Coût financier** | 0 € | 0 € (free tier) | 0 € |
| **Coût mise en oeuvre** | 4-6h | **2-3h** | 6-10h (incertain) |
| **Coût maintenance** | 30 min/mois | 5 min/mois | 0 |
| **Isolation jobs/host** | ❌ Compromise | ✅ GitHub-hosted runner jetable | ✅ GitHub-hosted runner jetable |
| **Audit logs** | GitHub Actions | **Tailscale + syslog** | Scaleway IAM |
| **Synergie ARTCI (#215)** | Faible | **Forte** (logs centralisés) | Forte (logs IAM) |
| **Verrou vendor** | Aucun | Léger (Tailscale ↔ Headscale possible) | **Fort (Scaleway IAM)** |
| **Soutenabilité 1 dev solo** | ⚠️ Updates runner manuels | ✅ Updates Tailscale auto | ✅ Pas de maintenance |
| **Incertitude faisabilité** | Aucune | Aucune | **Élevée** (support OIDC à vérifier) |
| **Réversibilité** | Moyenne | **Élevée** (revert workflow trivial) | Faible (refactor déploiement) |

---

## Décision

**2026-08-15 — Option D retenue** (Dokploy-native). Les options A/B/C visaient
Scaleway + `appleboy/ssh-action`. Ce chemin n'est plus la prod.

**2026-05-30 — recommandation historique (obsolète) : B — Tailscale SSH**

### Justification

1. **Élimine le risque B1-SEC sans introduire de nouveau risque ops**.
   La clé SSH statique disparaît, remplacée par une auth-key ephemeral
   audité.

2. **Meilleur ratio coût mise en oeuvre / bénéfice** (2-3h vs 4-6h
   self-hosted vs 6-10h OIDC incertain).

3. **Pas d'incertitude technique** (contrairement à OIDC Scaleway qui
   nécessite vérifier le support).

4. **Audit logs centralisés** = bonus pour la conformité ARTCI (#215)
   qui demande un trail des accès PII.

5. **Soutenabilité 1 dev solo** : Tailscale est conçu pour les équipes
   petites, updates automatiques, dashboard simple.

6. **Réversibilité** : on peut TOUJOURS revenir à SSH classique en
   revertant le workflow. Pas de verrou.

### Pourquoi pas A (self-hosted runner) ?

- L'isolation jobs/host est compromise. Risque si un workflow malveillant
  est mergé sur APIPy (ex: dépendance npm compromise, fork malicieux).
- Maintenance manuelle du runner = oubli probable sur projet 1 dev.
- Performance / latence ne sont pas un problème actuel sur Wourri (1-3
  déploiements/jour).

### Pourquoi pas C (Scaleway OIDC) ?

- Incertitude sur le support OIDC GitHub Actions par Scaleway. Si non
  supporté, on perd 6-10h d'investigation pour rien.
- Refactor déploiement plus invasif (suppression complète SSH).
- Verrou vendor Scaleway le plus fort. Wourri est un projet où la
  portabilité d'hébergement peut être stratégique (déplacement vers
  Hetzner / OVH / cloud africain ultérieurement).

### Conditions d'acceptation

Cette décision est valide **si** Tailscale free tier reste à ≥ 100
devices ET si Wourri reste à ≤ 10 VMs. Si Tailscale change drastiquement
sa politique de pricing, réévaluer via ADR de remplacement.

---

## Conséquences (si décision B retenue)

### Positives

- **Suppression clé SSH statique** : risque B1-SEC mitigé long terme
- **Port 22 public peut être fermé** sur firewall Scaleway (gain
  sécurité bonus)
- **Audit trail accès VM** disponible pour ARTCI
- **Pas de SPOF** : le déploiement reste sur GitHub-hosted runner
  jetable

### Négatives assumées

- **Dépendance Tailscale** (mitigée par Headscale possible + clé SSH
  backup pour accès admin manuel d'urgence)
- **Auth-key Tailscale en GitHub Secrets** : ce n'est pas zéro-secret,
  c'est juste un secret de meilleure qualité (court terme, audité,
  révocable)

### Migration / travail induit

1. Création compte Tailscale (5 min)
2. Install Tailscale sur VM (10 min, via apt + `tailscale up --ssh`)
3. Configuration ACL Tailscale (15 min)
4. Génération auth-key + ajout en GitHub Secret (5 min)
5. Modification `deploy-api.yml` + `deploy-wa.yml` (30 min)
6. Test E2E déploiement staging (30-60 min)
7. Fermeture port 22 public sur firewall (optionnel, après validation)
8. Documentation `docs/deployment.md` (20 min)
9. Update `whatsapp-server/CLAUDE.md` si nécessaire

**Estimation totale** : 2-3h de travail concentré, exécutable en 1
session.

### Verrous futurs

- **Tailscale → Headscale** : possible si Tailscale devient payant
  inacceptable. Migration = changer le control plane, garder le client.
- **Tailscale → SSH classique** : revert trivial, mais perd le bénéfice
  sécurité.
- **Tailscale → Scaleway OIDC** : si Scaleway supporte OIDC plus tard,
  ADR ultérieur de remplacement possible.

---

## Hors scope

- **Décision sur la fermeture du port 22 public** : suit la mise en
  place Tailscale, à confirmer après validation E2E que tous les accès
  admins passent par Tailscale.
- **Authentification 2FA des admins humains** sur la VM : sujet
  orthogonal (clé SSH personnelle Ruben + 2FA passphrase locale).
- **Backup d'urgence** : si Tailscale est en panne, Ruben doit pouvoir
  SSH manuellement. Garder une clé SSH backup chiffrée avec passphrase,
  documentée dans `docs/deployment.md`.
- **Tailscale Funnel** (exposition publique de services internes) : non
  utilisé ici, hors scope.

---

## Plan d'exécution (si décision B retenue)

| Étape | Description | Durée | PR |
|---|---|---:|---|
| B.1 | Création compte Tailscale + install VM | 15 min | — |
| B.2 | Configuration ACL `tag:ci` → `tag:wourri-prod` | 15 min | — |
| B.3 | Génération auth-key ephemeral 90j + GitHub Secret | 5 min | — |
| B.4 | Modification `deploy-api.yml` + `deploy-wa.yml` | 30 min | PR-A |
| B.5 | Test E2E déploiement staging (1 PR de validation) | 30-60 min | PR-A |
| B.6 | Documentation `docs/deployment.md` | 20 min | PR-A |
| B.7 | Fermeture port 22 public (firewall Scaleway) | 5 min + monitoring 24h | — |
| B.8 | Marquer cet ADR comme **complété** | 5 min | PR-A |

---

## Métriques de succès

| Métrique | Cible |
|---|---|
| Clé SSH statique CI supprimée des GitHub Secrets | ✅ |
| Port 22 public fermé sur firewall Scaleway | ✅ |
| Déploiement API + WA fonctionnel via Tailscale | ✅ |
| Logs Tailscale visibles dans dashboard | ✅ |
| Temps déploiement E2E ≤ 5 min | ≤ 5 min |
| Backup SSH manuel documenté | ✅ |

---

## Références

- Issue : [#221](https://github.com/ouedraogoissouf2012/wourri/issues/221)
- PR mitigation court terme : [#212](https://github.com/ouedraogoissouf2012/wourri/pull/212)
- ADR précédent sécurité : [ADR-0012](0012-securite-whatsapp-server.md)
- ADR lié futur : ADR-0014 ARTCI conformité (#215) — bénéficierait des
  logs Tailscale pour audit trail
- Doc Tailscale SSH : https://tailscale.com/kb/1193/tailscale-ssh/
- Doc Tailscale ACL : https://tailscale.com/kb/1018/acls/
- Doc Tailscale GitHub Action : https://github.com/tailscale/github-action
- Doc Scaleway IAM (référence Option C) : https://www.scaleway.com/en/docs/identity-and-access-management/iam/
- Doc GitHub OIDC : https://docs.github.com/en/actions/deployment/security-hardening-your-deployments/about-security-hardening-with-openid-connect

---

## Historique

- **2026-05-30 (rédaction)** : ADR brouillon. 3 options Scaleway, recommandation
  historique **Option B (Tailscale SSH)**. Statut **proposé**.
- **2026-08-15 (addendum)** : ADR-0024 a rendu A/B/C inapplicables au chemin
  prod. **Option D** (Dokploy-native) retenue. Statut **accepté**. #221
  closeable : pas d'implémentation Tailscale/runner. Accès admin Contabo =
  sujet séparé si besoin.
