# ADR-0024 — Déploiement Wourri sur l'hôte Dokploy existant (ADC)

**Statut** : accepté
**Date** : 2026-08-13
**Auteur(s)** : Claude (assistant IA)
**Valideur** : Issouf (ouedraogoissouf2012)

---

## Contexte

Le premier déploiement effectif de Wourri (prévu « Sprint J » dans
[docs/deployment.md](../deployment.md)) doit avoir lieu. Le runbook existant a
été écrit pour une **VM Scaleway vierge** avec un montage manuel
`docker compose` + nginx + certbot + ufw + systemd + secrets fichiers.

La cible réelle est différente. Reconnaissance effectuée le 2026-08-13 sur le
serveur `serveur.africandigitconsulting.com` (VPS Contabo `vmi3499821`, user
`marcel`) :

**Ressources** : Ubuntu 24.04 LTS, 8 vCPU AMD EPYC, **23 Go RAM**, 4 Go swap,
290 Go disque (13 Go utilisés). Docker 29.7 + Compose v5.4.

**Infra déjà en place (à ne pas casser)** :

- **Dokploy** `v0.29.14` — PaaS auto-hébergée (build/deploy/logs/rollback).
- **Traefik** `v3.6.7` — reverse proxy possédant les ports 80/443 + SSL
  Let's Encrypt. (Les vhosts nginx `portainer.…`/`serveur.…` sont des vestiges
  inactifs : le 404 servi sur `:80` porte la signature Traefik.)
- **Docker Swarm actif** (ports 2377/7946), overlay `dokploy-network`.
- **Portainer** (UI Docker, `127.0.0.1:9443`).
- Conteneurs : `dokploy`, `dokploy-postgres`, `dokploy-traefik`, `portainer`.

**Pourquoi décider maintenant** : la cible d'hébergement change de paradigme
(VM manuelle → PaaS Dokploy sur Swarm). Reproduire à la main le montage
nginx/certbot/systemd du runbook reviendrait à **combattre** une infra
d'orchestration déjà installée et opérationnelle. Aucun ADR existant ne couvre
le choix de plateforme d'hébergement — [ADR-0013](0013-ssh-deploy-hardening-options.md)
ne traite que du durcissement de la clé SSH CI.

**Contraintes projet pertinentes** (réf. [constraints.md](../constraints.md)) :
qualité > vitesse, pas de raccourci, coexistence avec l'existant obligatoire,
ADR avant tout code structurant.

**Spécificité repo (structurante)** : `wouri-api` et `whatsapp-server` sont
deux checkouts du **même** repo `github.com/ouedraogoissouf2012/wourri` sur
**deux branches orphelines distinctes** :

- branche `APIPy` → racine = code wouri-api (`Dockerfile.prod` à la racine)
- branche `whatsappServeur` → racine = code whatsapp-server (`Dockerfile.prod`)
- branche `wourri` = défaut

La migration monorepo ([ADR-0010](0010-migration-monorepo.md)) est encore au
statut **proposé** (non exécutée). Il n'existe donc **aucune branche unique
contenant les deux arbres de code** → pas de `docker-compose.yml` capable de
builder les deux services depuis un seul checkout Git.

## Questions posées avant la décision

Questions stratégiques posées à l'utilisateur le 2026-08-13 (transcript session) :

1. Comment déployer Wourri sur ce serveur Dokploy ?
2. Wourri a-t-il besoin d'une exposition publique Internet, ou l'interne suffit ?
3. D'où viennent les images Docker (build serveur vs ghcr.io CI) ?

Réponses obtenues :

- **Q1 → Via Dokploy** (utiliser la PaaS en place, ne pas monter un système
  d'orchestration parallèle).
- **Q2 → Interne seulement.** Aucun domaine public. Justification technique :
  Baileys est un client **sortant** (WebSocket vers WhatsApp) ; l'API est
  appelée en interne par le serveur WhatsApp. Le seul entrant est la **page QR**
  à scanner une fois — faisable via tunnel SSH, sans exposition Traefik.
- **Q3 → Build sur le serveur depuis Git.** Aucune dépendance à l'état de la CI
  ni à l'authentification ghcr.io. Ressources largement suffisantes (8 vCPU /
  23 Go). Coût : ~15-30 min au 1er build de wouri-api (préload modèles ML).

## Options étudiées

Le cadre est fixé par les réponses ci-dessus (Dokploy + interne + build serveur).
La vraie question ouverte est **comment modéliser les 3 composants dans Dokploy**
compte tenu de la contrainte des deux branches.

### Option A — 3 services natifs dans un Projet Dokploy « Wourri »

- **Description** : un Projet Dokploy contenant 3 ressources —
  (1) `postgres` (Database Dokploy `pgvector/pgvector:pg16` ou app image),
  (2) `wouri-api` (Application, source Git branche `APIPy`, build `Dockerfile.prod`),
  (3) `whatsapp-server` (Application, source Git branche `whatsappServeur`,
  build `Dockerfile.prod`). Câblage via le réseau overlay partagé + variables
  d'env pointant les hostnames de service.
- **Avantages** :
  - **Aucune restructuration du repo** : chaque service build depuis sa branche
    naturelle → cohérent avec le modèle CI existant (APIPy→api, whatsappServeur→wa).
  - Ne préempte pas [ADR-0010](0010-migration-monorepo.md) (monorepo encore proposé).
  - Rollback et logs par service, indépendants (natif Dokploy).
- **Inconvénients** :
  - **Réseau inter-services à câbler explicitement** : en Swarm/Dokploy le nom
    DNS d'un service porte un préfixe généré (pas juste `postgres`/`wouri-api`).
    Nécessite d'attacher les 3 sur un réseau commun + alias, OU d'utiliser les
    hostnames Dokploy réels dans `POSTGRES_URL` et `WOURI_API_URL`.
    *(comportement exact à vérifier sur l'instance 0.29.14 — non mesuré.)*
  - Migrations Alembic à orchestrer hors du démarrage API (commande one-shot
    Dokploy ou `docker exec` manuel).
- **Coût** : setup modéré (3 ressources + câblage réseau/env), 0 dette repo.
- **Compatibilité contraintes** : ✅ pas de raccourci, respecte ADR-0010.

### Option B — Service Dokploy « Compose » unifié via une branche de déploiement

- **Description** : créer une branche de déploiement (ex. `deploy-dokploy`)
  regroupant les deux arbres de code (`wouri-api/`, `whatsapp-server/`) + un
  `docker-compose.yml` avec sections `build:` (contextes vers les sous-dossiers)
  et le service `postgres`. Dokploy « Compose » clone cette branche et build/déploie
  le tout comme une seule stack.
- **Avantages** :
  - **DNS interne propre** : dans une stack Compose Dokploy, les services se
    résolvent par leur nom (`postgres`, `wouri-api`) sans câblage manuel.
  - Une seule unité de déploiement ; migrations modélisables en service one-shot
    (`migrate` avec `restart: "no"`, `depends_on` postgres healthy).
  - Réutilise directement `docker-compose.prod.yml` (adapté : `build:` au lieu
    de `image: ghcr.io`, secrets fichiers → env Dokploy).
- **Inconvénients** :
  - **Restructuration repo requise** : fusionner deux branches orphelines dans
    une branche unique = travail structurel qui **chevauche ADR-0010** (monorepo).
    Le faire à la va-vite préempterait/contredirait cet ADR encore en discussion.
  - Branche de déploiement à maintenir en phase avec `APIPy`/`whatsappServeur`
    (double push, ou automatisation) tant que le monorepo n'est pas fait.
- **Coût** : setup plus lourd (branche + fusion arbres + maintenance sync), dette
  repo temporaire jusqu'à ADR-0010.
- **Compatibilité contraintes** : ⚠️ risque de raccourci structurel si bâclé ;
  acceptable seulement si la branche est traitée comme 1re étape propre d'ADR-0010.

### Option C — `docker compose` classique HORS Dokploy (rejetée en amont)

- **Description** : déployer `docker-compose.prod.yml` en direct (marcel dans le
  groupe docker), bind 127.0.0.1, en parallèle de Dokploy.
- **Avantages** : runbook déjà écrit, contrôle bas niveau total, DNS interne
  propre (réseau compose dédié).
- **Inconvénients** : fait tourner **deux systèmes d'orchestration** sur le même
  hôte (Swarm/Dokploy + compose standalone) → incohérence ops, Traefik possède
  déjà 80/443, non-géré par la plateforme d'équipe. **Écartée par l'utilisateur
  en Q1.**
- **Coût** : faible au départ, dette ops croissante.
- **Compatibilité contraintes** : ❌ contredit le choix « via Dokploy ».

> Note sur les images ghcr.io : une variante « Compose avec `image: ghcr.io/...`
> pré-buildées » a été écartée par Q3 (build serveur retenu, pas de dépendance CI/GHCR).

### Comparatif

| Critère | A (3 services) | B (Compose/branche) | C (compose hors Dokploy) |
|---|---|---|---|
| Restructuration repo | Aucune | **Requise** (chevauche ADR-0010) | Aucune |
| DNS interne | À câbler (env/alias) | **Natif par nom** | Natif par nom |
| Cohérence CI existante | ✅ branche/service | ⚠️ nouvelle branche à sync | ✅ |
| Intégration infra équipe | ✅ Dokploy | ✅ Dokploy | ❌ parallèle |
| Effort setup initial | Moyen | Élevé | Faible |
| Dette induite | Faible | Repo (temporaire) | Ops (permanente) |
| Verrou Dokploy | Moyen | Moyen | Nul |

## Décision

**Option retenue** : **Option A (3 services natifs Dokploy)** — validée par
l'utilisateur le 2026-08-13.

**Justification** : c'est la seule option qui déploie via Dokploy (Q1), build sur
le serveur (Q3), reste interne (Q2) **sans toucher à la structure du repo**. Elle
respecte que la migration monorepo (ADR-0010) est une décision distincte non
tranchée : on ne préempte pas un ADR par un raccourci structurel. Le seul point
dur — le câblage réseau inter-services — est un travail de config borné et
documenté, pas une dette. L'Option B reste préférable *fonctionnellement* (DNS
propre, unité unique) et deviendra le choix naturel **une fois ADR-0010 exécuté** ;
elle pourra alors superséder cet ADR.

## Conséquences

- **Positives** :
  - Déploiement intégré à la plateforme d'équipe (Dokploy) : logs, restart,
    rollback, gestion env centralisés.
  - Aucune surface publique ajoutée (interne only) → surface d'attaque minimale.
  - Aucune modification du repo (branches, structure) → ADR-0010 reste libre.

- **Négatives assumées** :
  - Câblage réseau/env inter-services manuel (à valider sur Dokploy 0.29.14).
  - 3 ressources à gérer plutôt qu'une stack unique.
  - Le runbook `deployment.md` (montage nginx/certbot/systemd/secrets fichiers)
    devient **partiellement obsolète** pour cette cible ; ses parties réutilisables
    (backups, rotation clés, healthchecks) restent valables et seront réadaptées.

- **Migration / travail induit** (détaillé dans le plan d'exécution à venir) :
  1. **Accès Docker/opérations** : décider comment j'opère (groupe `docker` pour
     marcel, ou sudo NOPASSWD ciblé, ou commandes exécutées par l'utilisateur).
     `sudo` exige actuellement un mot de passe → bloquant pour l'automatisation.
  2. **Accès Git Dokploy** : configurer l'accès de Dokploy au repo (public, ou
     GitHub App / deploy key si privé) pour build les branches `APIPy` /
     `whatsappServeur`.
  3. **postgres** : image `pgvector/pgvector:pg16`, appliquer `db-init/init.sql`
     (extension `vector`), volume data persistant, `POSTGRES_USER/PASSWORD/DB`.
  4. **Migrations Alembic** : étape one-shot `run_migrations.sh` **avant** le
     démarrage de l'API (jamais au startup — race 2 workers uvicorn).
  5. **Secrets** : Dokploy gère les env par ressource. La clé partagée
     API↔WhatsApp (`API_SECRET_KEY`/`WOURI_API_KEY`) et `POSTGRES_PASSWORD`
     injectées en variables Dokploy (pas de Docker secrets fichiers ici — le
     mécanisme `*_FILE` du compose devient sans objet). Vérifier le nom de
     variable exact attendu par `app/config.py`.
  6. **Volumes persistants critiques** : `hf_cache` (modèles ML, évite
     re-download), `wa_auth` (session WhatsApp — **perte = re-scan QR**),
     `audio_output`, `wa_data`. À déclarer en volumes Dokploy nommés + inclure
     dans la stratégie de backup.
  7. **Scan QR WhatsApp** : one-shot via tunnel SSH
     (`ssh -L 3001:127.0.0.1:3001 …` ou accès interne Dokploy) → `/qr-page`.
  8. **Backups** : réadapter `backup.sh` (dump pg + `wa_auth`) au contexte
     Dokploy (chemins volumes différents de `/srv/wourri`).

- **Verrous futurs** :
  - Dépendance opérationnelle à Dokploy (mitigée : ce sont des conteneurs Docker
    standard, réversibles vers compose/Swarm si besoin).
  - Tant que le câblage réseau est manuel (Option A), un renommage de service
    Dokploy casse la résolution → à documenter.

- **Souveraineté / réglementaire** : le VPS Contabo est en UE (IPv6 `2a02:c207`,
  Contabo Allemagne). Les données (numéros WhatsApp, questions agricoles)
  résident donc hors Côte d'Ivoire. À garder en tête pour la conformité **ARTCI**
  (régulateur data CI) — non bloquant pour un staging, mais à tracer.

## Références

- Reconnaissance serveur 2026-08-13 (transcript session).
- [docs/deployment.md](../deployment.md) — runbook Scaleway (partiellement réutilisable).
- [ADR-0010](0010-migration-monorepo.md) — migration monorepo (proposé) : préalable
  à l'Option B.
- [ADR-0013](0013-ssh-deploy-hardening-options.md) — durcissement SSH CI.
- [ADR-0011](0011-strategie-prechargement-ml.md) — préchargement modèles ML
  (explique le build lourd de wouri-api).
- Dockerfiles : `wouri-api/Dockerfile.prod`, `whatsapp-server/Dockerfile.prod`.

## Historique

- 2026-08-13 — rédaction initiale (proposé), en attente de validation utilisateur
  (choix Option A vs B).
- 2026-08-13 — **accepté** : Option A retenue par l'utilisateur (3 services natifs
  Dokploy, aucune restructuration repo).
