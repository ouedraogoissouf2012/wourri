# Wourri — Déploiement STAGING

> **Issue parent** : [#202](https://github.com/ouedraogoissouf2012/wourri/issues/202) (Sprint J)
> **Statut** : préparation infra livrée (cette PR). Provisionnement VM
> à exécuter par l'opérateur (Ruben).
> **Objectif** : un environnement staging isolé de la prod permettant de
> valider les changements avant bascule prod, prérequis du Sprint K
> ([#203](https://github.com/ouedraogoissouf2012/wourri/issues/203))
> Phase E ADR-0008 (mesurer latence pgvector en conditions réelles).

---

## Sommaire

1. [Vue d'ensemble](#1-vue-densemble)
2. [Provisionnement VM Scaleway](#2-provisionnement-vm-scaleway)
3. [Configuration DNS](#3-configuration-dns)
4. [Installation Docker + dépendances](#4-installation-docker--dépendances)
5. [Préparation arborescence + secrets](#5-préparation-arborescence--secrets)
6. [Premier déploiement](#6-premier-déploiement)
7. [Accès Loki (logs centralisés)](#7-accès-loki-logs-centralisés)
8. [Tests E2E staging](#8-tests-e2e-staging)
9. [Workflow CI déploiement automatisé](#9-workflow-ci-déploiement-automatisé)
10. [Procédure rollback](#10-procédure-rollback)
11. [Coûts mensuels estimés](#11-coûts-mensuels-estimés)
12. [Checklist Sprint J complet](#12-checklist-sprint-j-complet)

---

## 1. Vue d'ensemble

### Architecture cible staging

```
┌─────────────────────────────────────────────────────────────────────┐
│  VM staging Scaleway DEV1-S (1 vCPU, 2 GB RAM, 40 GB disk)         │
│  Domaine : staging-api.wourri.ci                                    │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌──────────────────┐    ┌──────────────────┐    ┌──────────────┐ │
│  │  wouri-api       │───►│  postgres        │    │  whatsapp-   │ │
│  │  :8001 → :8000   │    │  pgvector/pg16   │◄───│  server      │ │
│  │  mem 3GB         │    │  :5432 (interne) │    │  :3002→:3001 │ │
│  └──────┬───────────┘    └──────────────────┘    └──────────────┘ │
│         │ stdout                                                    │
│         ▼                                                           │
│  ┌──────────────────┐    ┌──────────────────┐                     │
│  │  promtail        │───►│  loki            │                     │
│  │  scrape Docker   │    │  :3100 (interne) │                     │
│  │  logs            │    │  retention 14j   │                     │
│  └──────────────────┘    └──────────────────┘                     │
│                                                                     │
│  Réseau Docker : wourri_staging_net (isolé de prod)               │
│  Bind-mounts   : /srv/wourri-staging/data/{postgres,loki}/        │
│  Secrets       : /srv/wourri-staging/secrets/                     │
└─────────────────────────────────────────────────────────────────────┘
```

### Différences clés vs prod

| Aspect | Prod | Staging |
|---|---|---|
| **Domaine** | `api.wourri.ci` | `staging-api.wourri.ci` |
| **VM** | DEV1-M (4 GB RAM) | DEV1-S (2 GB RAM) |
| **CORPUS_STORAGE_MODE** | `dual` ou `pgvector` | **`dual`** (mesure Phase E) |
| **LOG_LEVEL** | `info` | **`debug`** (plus de signal) |
| **Monitoring** | healthchecks.io seul | healthchecks.io + Loki + Promtail |
| **Ports host** | 8000 / 3001 | 8001 / 3002 |
| **Tag image** | `:latest` | `:staging` |
| **Container names** | `wourri_*_prod` | `wourri_*_staging` |
| **Réseau Docker** | `wourri_net` | `wourri_staging_net` |
| **Volumes** | `wourri_*` | `wourri_staging_*` |

### Pourquoi VM dédiée plutôt que sous-domaine sur VM prod

- **Isolation incidents** : un bug staging qui consomme 100% CPU ne tue
  pas la prod
- **Liberté de tests destructifs** : on peut casser staging volontairement
  (chaos test, simulation panne Postgres) sans risquer prod
- **Mesure latence Phase E #203 fiable** : ressources non partagées →
  mesures pgvector reproductibles
- **Sécurité** : compromission staging ne donne pas accès à prod (secrets
  différents, réseau distinct)
- **Coût marginal** : ~10-15 €/mois pour une DEV1-S Scaleway, négligeable
  vs valeur infra

---

## 2. Provisionnement VM Scaleway

### Étape 2.1 — Création VM

Via console Scaleway (https://console.scaleway.com) :

1. **Instance** → "Create an Instance"
2. **Image** : Ubuntu 24.04 LTS
3. **Type** : DEV1-S (Development, 1 vCPU, 2 GB RAM, 20 GB disk = ~10 €/mois)
4. **Storage** : Local SSD (suffit pour staging, faible volume écriture)
5. **Volume additional** : optionnel, ajouter 40 GB Block Storage si
   besoin de plus pour Loki long-terme (~3 €/mois)
6. **Région** : `fr-par-1` (Paris) — latence Côte d'Ivoire ~120ms,
   acceptable pour staging non-critique
7. **Network** :
   - Cochez "Routed IP" (1 IPv4 publique nécessaire pour SSH + Let's Encrypt)
   - Pas de Private Network (staging isolé)
8. **SSH Keys** : importer ta clé SSH publique (`~/.ssh/id_ed25519.pub`)
9. **Name** : `wourri-staging`
10. **Tags** : `wourri`, `staging`
11. **Create** → noter l'IP publique attribuée

### Étape 2.2 — Configuration firewall Scaleway

Console → Security Groups → créer `wourri-staging-sg` :

| Direction | Protocol | Port | Source | Action |
|---|---|---|---|---|
| Inbound | TCP | 22 (SSH) | Ton IP perso /32 OU ranges Scaleway si CI deploy | Allow |
| Inbound | TCP | 80 (HTTP) | 0.0.0.0/0 | Allow (Let's Encrypt only) |
| Inbound | TCP | 443 (HTTPS) | 0.0.0.0/0 | Allow |
| Inbound | * | * | 0.0.0.0/0 | Deny |
| Outbound | * | * | 0.0.0.0/0 | Allow |

**Pas d'exposition** des ports 8001, 3002, 3100, 5432 : ils sont bind sur
`127.0.0.1` côté Docker, donc inaccessibles depuis Internet. Accès via
tunnel SSH.

### Étape 2.3 — Connexion initiale

```bash
# Depuis ton poste local
ssh -i ~/.ssh/id_ed25519 root@<IP_STAGING>

# Créer un user non-root (best practice sécu)
adduser wourri --gecos "" --disabled-password
usermod -aG sudo wourri
mkdir -p /home/wourri/.ssh
cp ~/.ssh/authorized_keys /home/wourri/.ssh/
chown -R wourri:wourri /home/wourri/.ssh
chmod 700 /home/wourri/.ssh
chmod 600 /home/wourri/.ssh/authorized_keys

# Désactiver login root SSH (sécurité)
sed -i 's/^#*PermitRootLogin.*/PermitRootLogin no/' /etc/ssh/sshd_config
systemctl restart sshd

# Tester depuis nouveau terminal AVANT de fermer celui-ci
ssh wourri@<IP_STAGING>
```

---

## 3. Configuration DNS

### Si tu utilises un registrar standard (Gandi, OVH, Cloudflare)

Ajouter un enregistrement DNS :

```
Type:   A
Name:   staging-api
TTL:    300
Value:  <IP_STAGING_SCALEWAY>
```

Résultat attendu : `staging-api.wourri.ci` → IP staging.

Vérification :
```bash
dig staging-api.wourri.ci +short
# Doit retourner l'IP staging dans les 5-10 min après création
```

### Optionnel : sous-domaine WhatsApp

Si tu veux exposer le serveur whatsapp-server staging via webhook
(non recommandé en staging — préfère le mode polling Baileys) :

```
Type:   A
Name:   staging-wa
TTL:    300
Value:  <IP_STAGING_SCALEWAY>
```

---

## 4. Installation Docker + dépendances

```bash
# Connexion staging
ssh wourri@<IP_STAGING>

# Mise à jour système
sudo apt update && sudo apt upgrade -y

# Docker (procédure officielle Docker pour Ubuntu)
sudo apt install -y ca-certificates curl gnupg
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | \
    sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
    https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | \
    sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# Ajouter wourri au groupe docker (sinon `sudo docker` partout)
sudo usermod -aG docker wourri
# Reconnecter pour appliquer
exit
ssh wourri@<IP_STAGING>

# Vérif
docker --version          # Docker 27.x ou plus
docker compose version    # Docker Compose v2.30+ ou plus

# Outils utiles
sudo apt install -y vim git rsync htop ncdu
```

---

## 5. Préparation arborescence + secrets

### 5.1 — Arborescence

```bash
sudo mkdir -p /srv/wourri-staging/{data,secrets}
sudo mkdir -p /srv/wourri-staging/data/{postgres,loki}
sudo chown -R wourri:wourri /srv/wourri-staging

# Postgres a besoin UID 999 (image pgvector/pgvector officielle)
sudo chown 999:999 /srv/wourri-staging/data/postgres
sudo chmod 700 /srv/wourri-staging/data/postgres

# Loki a besoin UID 10001 (image grafana/loki officielle)
sudo chown 10001:10001 /srv/wourri-staging/data/loki

# Secrets : root 0600 (Docker daemon lit en root, lui-même restreint)
sudo chmod 700 /srv/wourri-staging/secrets
```

### 5.2 — Génération des secrets

```bash
cd /srv/wourri-staging/secrets

# Postgres password — 32 chars base64
openssl rand -base64 32 | tr -d '\n' | sudo tee postgres_password > /dev/null
sudo chmod 600 postgres_password
sudo chown root:root postgres_password

# API secret key — partagée wouri-api ↔ whatsapp-server
openssl rand -base64 32 | tr -d '\n' | sudo tee api_secret_key > /dev/null
sudo chmod 600 api_secret_key
sudo chown root:root api_secret_key

# Vérif (les commandes ne doivent montrer QUE les permissions et l'owner)
ls -la /srv/wourri-staging/secrets/
# -rw------- 1 root root 44 ... postgres_password
# -rw------- 1 root root 44 ... api_secret_key
```

### 5.3 — `.env.staging`

```bash
cd /srv/wourri-staging
# Copier le template depuis le repo (voir étape 6)
cp .env.staging.template .env.staging
chmod 600 .env.staging
vim .env.staging
# Remplir :
#   POSTGRES_PASSWORD = le contenu de /srv/wourri-staging/secrets/postgres_password
#                      (ouverture rapide : `cat /srv/wourri-staging/secrets/postgres_password`)
#                      ⚠️ Limitation actuelle : duplication entre Docker secret
#                      (lu par postgres image) ET env var (lu par url_resolver.py
#                      Python). Sera fixée par issue de followup (cf. PR #247).
#   WOURI_API_KEY = `openssl rand -base64 32` (DIFFÉRENT de prod)
#   HEALTHCHECKS_* = optionnel, créer un compte healthchecks.io distinct
```

### 5.4 — Copie des fichiers projet

Depuis ton poste local (pas la VM) :

```bash
# Cloner le repo si pas encore fait
git clone https://github.com/ouedraogoissouf2012/wourri.git
cd wourri/wouri-api
git checkout APIPy
git pull origin APIPy

# Copier les fichiers requis vers /srv/wourri-staging/
scp docker-compose.staging.yml wourri@<IP_STAGING>:/srv/wourri-staging/
scp .env.staging.template wourri@<IP_STAGING>:/srv/wourri-staging/
scp -r db-init wourri@<IP_STAGING>:/srv/wourri-staging/
scp -r config wourri@<IP_STAGING>:/srv/wourri-staging/
```

### 5.5 — Login GHCR

Pour que Docker puisse pull les images privées depuis GitHub Container
Registry :

```bash
# Depuis la VM staging
# Créer un Personal Access Token GitHub : Settings → Developer settings →
#   Personal access tokens → Tokens (classic) → Generate new token (classic)
#   Scopes nécessaires : read:packages
#   Cf. issue #214 (PR #243 mergée : 3 options GHCR credential management)

# Authentification
echo "<TON_PAT_GITHUB>" | docker login ghcr.io -u ouedraogoissouf2012 --password-stdin
# Login Succeeded
```

---

## 6. Premier déploiement

### 6.1 — Pull des images

```bash
cd /srv/wourri-staging
docker compose --env-file .env.staging -f docker-compose.staging.yml pull
```

Les 5 images sont téléchargées :
- `pgvector/pgvector:pg16` (~250 MB)
- `ghcr.io/ouedraogoissouf2012/wourri-api:staging` (~3-4 GB avec modèles ML)
- `ghcr.io/ouedraogoissouf2012/wourri-whatsapp:staging` (~200 MB)
- `grafana/loki:3.3.2` (~80 MB)
- `grafana/promtail:3.3.2` (~120 MB)

**Premier pull lent** (~5-10 min selon bande passante VM). Suivants
incrémentaux (~30s).

### 6.2 — Migration Alembic (Postgres)

```bash
# Démarrer juste postgres en premier pour les migrations
docker compose --env-file .env.staging -f docker-compose.staging.yml up -d postgres

# Attendre que postgres soit healthy (~30s)
docker compose -f docker-compose.staging.yml ps
# postgres doit être "healthy"

# Run migrations
docker compose --env-file .env.staging -f docker-compose.staging.yml \
    run --rm wouri-api /app/scripts/run_migrations.sh
```

Output attendu :
```
INFO [alembic.runtime.migration] Running upgrade  -> 0001_pgvector_corpus_ivr
... (autres migrations selon l'historique)
```

### 6.3 — Démarrage de tous les services

```bash
docker compose --env-file .env.staging -f docker-compose.staging.yml up -d

# Suivre les logs pendant ~5 min (start_period wouri-api = 120s pour
# préchargement modèles ML)
docker compose -f docker-compose.staging.yml logs -f
```

### 6.4 — Vérifications

```bash
# Status de tous les services
docker compose -f docker-compose.staging.yml ps
# Tous doivent être "Up" et idéalement "(healthy)"

# Healthchecks individuels
curl http://127.0.0.1:8001/health    # wouri-api
curl http://127.0.0.1:3002/health    # whatsapp-server
curl http://127.0.0.1:3100/ready     # loki

# Test Postgres
docker compose exec postgres psql -U wourri -d wourri_staging -c "SELECT version();"
docker compose exec postgres psql -U wourri -d wourri_staging -c "SELECT * FROM pg_extension WHERE extname='vector';"
# Doit retourner 1 ligne avec 'vector | 0.7.x' ou plus

# Test endpoint corpus (vérifie ChromaDB + pgvector en mode dual)
curl http://127.0.0.1:8001/admin/corpus-divergence-report
```

### 6.5 — Scan QR WhatsApp

Le whatsapp-server au premier démarrage nécessite un scan QR pour
s'authentifier auprès de WhatsApp.

```bash
# Depuis ton poste local, tunnel SSH
ssh -L 3002:127.0.0.1:3002 wourri@<IP_STAGING>

# Dans navigateur local
# http://localhost:3002/qr-page
```

Scanner le QR avec WhatsApp d'un téléphone DÉDIÉ staging (pas ton WhatsApp
perso ni le compte WhatsApp prod).

Une fois scanné : `auth_baileys/` est persisté dans le volume nommé
`wourri_staging_wa_auth` → pas besoin de rescanner aux prochains
redémarrages.

---

## 7. Accès Loki (logs centralisés)

### 7.1 — Via API LogQL (sans UI)

```bash
# Depuis ton poste local, tunnel SSH
ssh -L 3100:127.0.0.1:3100 wourri@<IP_STAGING>

# Query : tous les logs wouri-api de la dernière heure
curl -s "http://localhost:3100/loki/api/v1/query_range?query=%7Bjob%3D%22api%22%7D&start=$(date -d '1 hour ago' +%s)000000000&end=$(date +%s)000000000" | jq .

# Query : erreurs récentes tous services
curl -s "http://localhost:3100/loki/api/v1/query_range?query=%7Bstack%3D%22wourri-staging%22%7D%20%7C%3D%20%22error%22" | jq .
```

### 7.2 — Via Grafana local (recommandé, plus pratique)

Sur ton poste local :

```bash
# Docker Grafana minimal (option : reuse un Grafana existant)
docker run -d -p 3000:3000 --name grafana-wourri \
    -e GF_AUTH_ANONYMOUS_ENABLED=true \
    -e GF_AUTH_ANONYMOUS_ORG_ROLE=Admin \
    grafana/grafana:11.3.0

# Tunnel SSH vers Loki staging
ssh -L 3100:127.0.0.1:3100 wourri@<IP_STAGING>

# Dans Grafana http://localhost:3000 :
#   Configuration → Data Sources → Add → Loki
#   URL = http://host.docker.internal:3100  (si Docker Desktop)
#   OU = http://172.17.0.1:3100             (si Linux pure)
#   Save & Test → doit retourner "Data source connected"

# Explore → Loki → query examples :
#   {job="api"}                    → tous logs wouri-api
#   {job="whatsapp"} |= "error"    → erreurs whatsapp-server
#   {stack="wourri-staging"} != "health"  → exclure les pings healthcheck
```

---

## 8. Tests E2E staging

### 8.1 — Scénarios à valider avant bascule prod

Documenter chaque test dans un fichier `staging-test-results.md` (à créer
sur ta VM ou ton poste, hors-git).

| Scénario | Étapes | Critère succès |
|---|---|---|
| **1. Audio bambara → réponse audio** | Envoyer un vocal bambara via WhatsApp staging | Réponse audio dioula reçue dans < 30s |
| **2. Texte français → réponse FR** | Envoyer "Quand semer le riz ?" | Réponse texte FR + audio dioula |
| **3. Concept inconnu → fallback** | Envoyer "Comment cuisiner du foutou ?" | Réponse fallback gracieuse |
| **4. NLU intent** | Envoyer "ki kalo malo bena dun" (concept agricole) | Match IVR / cascade NLU |
| **5. Onboarding nouvel utilisateur** | Premier message d'un nouveau numéro | Demande ville + langue |
| **6. Changement de ville** | "changer ville" depuis état COMPLETE | Demande nouvelle ville |
| **7. Latence pgvector (#188)** | 1000 queries via script load | `latency_ratio` ≤ 1.5 → débloque Phase E |
| **8. Restart graceful** | `docker compose restart wouri-api` | Service back en < 2 min, état conservé |
| **9. Crash postgres → recovery** | `docker compose kill postgres && docker compose start postgres` | wouri-api reconnecte automatiquement |
| **10. Backup/restore** | `pg_dump` puis `pg_restore` en local | Restore complet sans erreur |

### 8.2 — Mesure latence pgvector (critère ADR-0008 §Phase E)

Script de bench à créer en `tools/benchmark_pgvector_latency.py` (hors
scope cette PR). En attendant, méthode manuelle :

```bash
# Endpoint divergence-report contient déjà les métriques en mode dual
curl http://127.0.0.1:8001/admin/corpus-divergence-report | jq .

# Champs à surveiller :
#   - chroma_latency_p50_ms
#   - pgvector_latency_p50_ms
#   - latency_ratio = pgvector / chroma
#   - divergence_pct (doit rester 0%)

# Cible Phase E ADR-0008 : latency_ratio ≤ 1.5 sur 1000+ queries réelles
```

---

## 9. Workflow CI déploiement automatisé

> ⚠️ Non livré dans cette PR — Sprint J.2 (suivante).
>
> En attendant la livraison du workflow `deploy-api-staging.yml`, le
> redéploiement staging est **manuel** via SSH :
>
> ```bash
> ssh wourri@<IP_STAGING>
> cd /srv/wourri-staging
> docker compose --env-file .env.staging -f docker-compose.staging.yml pull
> docker compose --env-file .env.staging -f docker-compose.staging.yml \
>     run --rm wouri-api /app/scripts/run_migrations.sh
> docker compose --env-file .env.staging -f docker-compose.staging.yml up -d
> ```
>
> Sprint J.2 livrera un workflow GitHub Actions qui :
> - Trigger sur push branch APIPy (auto-deploy)
> - Build & push image GHCR `:staging`
> - SSH staging et exécute les commandes ci-dessus
> - Émet ping `HEALTHCHECKS_API_URL` après succès

---

## 10. Procédure rollback

### Rollback rapide (rollback de version)

Si une release casse staging :

```bash
ssh wourri@<IP_STAGING>
cd /srv/wourri-staging

# 1. Identifier le sha du dernier build connu OK
docker images ghcr.io/ouedraogoissouf2012/wourri-api --format "{{.Tag}} {{.CreatedAt}}"

# 2. Modifier .env.staging
vim .env.staging
# Changer API_IMAGE_TAG=sha-<ancien_commit>

# 3. Redéployer
docker compose --env-file .env.staging -f docker-compose.staging.yml up -d wouri-api

# 4. Vérifier
curl http://127.0.0.1:8001/health
```

### Restore Postgres depuis backup

```bash
# Stopper wouri-api d'abord (pas postgres)
docker compose -f docker-compose.staging.yml stop wouri-api

# Restore (exemple avec un dump local)
docker compose exec -T postgres psql -U wourri -d wourri_staging < backup_YYYY-MM-DD.sql

# Restart wouri-api
docker compose -f docker-compose.staging.yml start wouri-api
```

---

## 11. Coûts mensuels estimés

| Poste | Détail | €/mois |
|---|---|---:|
| VM Scaleway DEV1-S | 1 vCPU + 2 GB + 20 GB | ~10 |
| Block Storage additionnel | 40 GB SSD pour Loki long-terme | ~3 |
| IPv4 publique | Routed IP Scaleway | inclus |
| DNS | Si registrar séparé (Gandi, etc.) | déjà payé |
| healthchecks.io | Free tier 20 checks | 0 |
| GHCR | Free pour repo public, 500 MB pour privé | 0 |
| **Total estimé** | | **~13 €/mois** |

Comparé à un staging managed (Render, Railway, Fly.io) à ~25-50 €/mois,
self-host Scaleway = économie 50-75 % avec contrôle total.

---

## 12. Checklist Sprint J complet

### Phase J.1 — Préparation infra (cette PR ✅)
- [x] `docker-compose.staging.yml` créé
- [x] `.env.staging.template` créé
- [x] `config/loki/loki-config.yml` créé
- [x] `config/promtail/promtail-config.yml` créé
- [x] `docs/staging-deployment.md` (ce fichier) créé
- [ ] PR mergée

### Phase J.2 — Provisionnement (à faire par Ruben)
- [ ] VM Scaleway DEV1-S provisionnée
- [ ] Firewall Scaleway configuré (SSH + 80/443 only)
- [ ] User non-root `wourri` créé, root SSH désactivé
- [ ] Docker + dépendances installés
- [ ] Arborescence `/srv/wourri-staging/` créée avec bonnes permissions
- [ ] Secrets `postgres_password` + `api_secret_key` générés (différents prod)
- [ ] `.env.staging` rempli
- [ ] DNS `staging-api.wourri.ci` configuré

### Phase J.3 — Premier déploiement (à faire par Ruben)
- [ ] Fichiers projet copiés sur VM
- [ ] Login GHCR effectué
- [ ] Migrations Alembic passées sans erreur
- [ ] 5 services Up + healthy (`docker compose ps`)
- [ ] QR WhatsApp scanné avec téléphone dédié staging
- [ ] Healthchecks externes (healthchecks.io) configurés

### Phase J.4 — Validation E2E (à faire par Ruben)
- [ ] 10 scénarios E2E exécutés (cf. section 8)
- [ ] Latence pgvector mesurée ≥ 1000 queries (débloque #203)
- [ ] Logs Loki accessibles via tunnel SSH
- [ ] Backup pg_dump testé + restore testé

### Phase J.5 — Workflow CI auto-deploy (PR séparée future)
- [ ] `.github/workflows/deploy-api-staging.yml` créé
- [ ] Secret GitHub `STAGING_SSH_KEY` + `STAGING_HOST` configurés
- [ ] Deploy automatique sur push APIPy testé

### Critère de sortie Sprint J (#202)
- [ ] Bot WhatsApp staging répond à message vocal bambara avec audio dioula
- [ ] 3 endpoints `/health` répondent OK
- [ ] Logs consultables à distance (via Loki + tunnel SSH)
- [ ] Un dev distant peut redéployer en < 30 min via runbook

---

## Références

- Issue parent : [#202](https://github.com/ouedraogoissouf2012/wourri/issues/202)
- Sprint suivant (débloqué) : [#203](https://github.com/ouedraogoissouf2012/wourri/issues/203) Sprint K Phase E ADR-0008
- Sprint précédent (closed) : [#201](https://github.com/ouedraogoissouf2012/wourri/issues/201) Sprint I préparation
- Issue latence pgvector : [#188](https://github.com/ouedraogoissouf2012/wourri/issues/188) — résolu par mesure staging
- Documentation production : [`docs/deployment.md`](deployment.md)
- ADR-0008 : [migration ChromaDB → pgvector](adr/0008-plan-migration-chromadb-pgvector.md)
- Docs Scaleway : https://www.scaleway.com/en/docs/compute/instances/
- Docs Loki : https://grafana.com/docs/loki/latest/
- Docs Promtail : https://grafana.com/docs/loki/latest/send-data/promtail/
