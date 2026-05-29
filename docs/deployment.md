# Runbook déploiement Wourri — Sprint I.c

> Statut : **livré 2026-05-23**. Premier déploiement effectif planifié Sprint J.
> Pré-requis : Sprints I.a (Dockerfile.prod wouri-api), I.b (Dockerfile.prod whatsapp-server), I.c (compose + CI) mergés.

## Vue d'ensemble

Déploiement registry-based : la CI GitHub Actions build les images, les push sur `ghcr.io`, puis (optionnellement) déclenche un pull + restart sur une VM Scaleway via SSH.

```
┌──────────┐  push APIPy   ┌───────────────┐  build+push   ┌─────────┐
│  GitHub  │──────────────▶│ GitHub Actions│──────────────▶│ ghcr.io │
└──────────┘               └───────────────┘               └────┬────┘
                                  │                             │ pull
                                  │ SSH                         ▼
                                  ▼                       ┌──────────┐
                            ┌─────────────┐               │   VM     │
                            │ VM Scaleway │ ◀─────────────│ Scaleway │
                            └─────────────┘  docker pull  └──────────┘
```

3 conteneurs :

| Service | Image | Port (bind 127.0.0.1) |
|---|---|---|
| `postgres` | `pgvector/pgvector:pg16` | interne uniquement |
| `wouri-api` | `ghcr.io/ouedraogoissouf2012/wourri-api:latest` | 8000 |
| `whatsapp-server` | `ghcr.io/ouedraogoissouf2012/wourri-whatsapp:latest` | 3001 |

Tous les ports sont bindés sur `127.0.0.1` — l'exposition Internet (port 443) sera ajoutée Sprint J via reverse proxy (Caddy ou Traefik avec Let's Encrypt).

---

## Provisionnement initial de la VM (premier déploiement)

Une seule fois, manuellement.

### 1. Créer une VM Scaleway

- Type recommandé : `DEV1-M` ou `PLAY2-NANO` (selon budget — DEV1-M = 8 EUR/mois, 3 vCPU, 4 GB RAM)
- Région : `fr-par-2` (Paris) ou `nl-ams-1` (Amsterdam) — latence ~80 ms vers CI/Mali
- OS : Ubuntu Server 22.04 LTS
- Stockage : 40 GB minimum (modèles ML occupent ~4 GB après cache chaud)
- Réseau : IP publique IPv4

### 2. Hardening SSH

```bash
# Sur la VM, en root
adduser wourri
usermod -aG sudo wourri
mkdir -p /home/wourri/.ssh
# Copier votre clé publique
echo "ssh-ed25519 AAAA..." > /home/wourri/.ssh/authorized_keys
chmod 700 /home/wourri/.ssh
chmod 600 /home/wourri/.ssh/authorized_keys
chown -R wourri:wourri /home/wourri/.ssh

# Désactiver l'auth par mot de passe + login root
sed -i 's/^#*PasswordAuthentication .*/PasswordAuthentication no/' /etc/ssh/sshd_config
sed -i 's/^#*PermitRootLogin .*/PermitRootLogin no/' /etc/ssh/sshd_config
systemctl restart ssh

# Firewall : Sprint I.c.1 review OPS M6 — ufw + fail2ban obligatoires
# (SSH port 22 ouvert au monde = bruteforce constant en quelques heures).
apt-get install -y ufw fail2ban
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp comment 'SSH'
# Sprint J : ouvrir 80 + 443 quand le reverse proxy est en place.
# Pour l'instant tous les services applicatifs restent bindés 127.0.0.1.
ufw --force enable
systemctl enable --now fail2ban
# Bonus : si vous avez une IP fixe (CI ou bureau), restreindre :
#   ufw allow from <IP-fixe>/32 to any port 22 proto tcp
#   ufw delete allow 22/tcp
```

### 2b. Swap + sysctl (anti-OOM)

Sprint I.c.1 review OPS M8 : sur DEV1-M (4 GB RAM), un cold-start des modèles
ML peut frôler la limite. 4 GB de swap = filet de sécurité.

```bash
fallocate -l 4G /swapfile
chmod 600 /swapfile
mkswap /swapfile
swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab
# Préférer la RAM au swap (swappiness 10 vs défaut 60)
echo 'vm.swappiness=10' > /etc/sysctl.d/99-wourri-swap.conf
sysctl -p /etc/sysctl.d/99-wourri-swap.conf
```

### 3. Installer Docker + Docker Compose

```bash
# En tant que `wourri`
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker wourri
# Re-login pour appliquer le groupe
exit
```

### 4. Préparer l'arborescence prod

```bash
sudo mkdir -p /srv/wourri
sudo chown wourri:wourri /srv/wourri
cd /srv/wourri

# Cloner ce repo en read-only (sparse-checkout pour ne récupérer que le nécessaire)
git clone --depth 1 --branch APIPy https://github.com/ouedraogoissouf2012/wourri.git tmp-clone
cp tmp-clone/docker-compose.prod.yml .
cp tmp-clone/.env.prod.template .
cp -r tmp-clone/db-init .
rm -rf tmp-clone
```

### 5. Configurer les secrets prod

#### 5a. Variables non-secrètes (.env.prod)

```bash
cp .env.prod.template .env.prod
# Sprint I.c.1 review OPS N4 : owner root + permissions strictes pour empêcher
# tout autre utilisateur du groupe `docker` (qui = root via socket) de le lire.
sudo chown root:root .env.prod
sudo chmod 600 .env.prod
sudo nano .env.prod
# Remplir les valeurs non-secrètes : POSTGRES_USER, POSTGRES_DB, ALLOWED_ORIGINS,
# LOG_LEVEL, CORPUS_STORAGE_MODE, API_IMAGE_TAG, WA_IMAGE_TAG, HEALTHCHECKS_*,
# WOURI_API_KEY (toujours utilisée par whatsapp-server side, cf. §5b note).
# Génération recommandée pour les chaînes aléatoires :
#   openssl rand -base64 32
```

#### 5b. Docker secrets (issue #213) — POSTGRES_PASSWORD + API_SECRET_KEY

Pour éviter que les secrets soient visibles dans `docker inspect`,
`/proc/<pid>/environ` ou `docker compose config`, ils sont stockés dans des
**fichiers** sur l'host (mode `0600` root:root), montés en read-only dans
`/run/secrets/<nom>` côté container.

```bash
# Préparer le dossier secrets (mode 0700, root only)
sudo mkdir -p /srv/wourri/secrets
sudo chmod 0700 /srv/wourri/secrets
sudo chown root:root /srv/wourri/secrets

# 1. POSTGRES_PASSWORD : lu nativement par l'image postgres via
#    POSTGRES_PASSWORD_FILE=/run/secrets/postgres_password
echo -n "$(openssl rand -base64 32)" | sudo tee /srv/wourri/secrets/postgres_password >/dev/null
sudo chmod 0600 /srv/wourri/secrets/postgres_password
sudo chown root:root /srv/wourri/secrets/postgres_password

# 2. API_SECRET_KEY : lu par app/config.py::_read_file_secret() via
#    API_SECRET_KEY_FILE=/run/secrets/api_secret_key
echo -n "$(openssl rand -base64 32)" | sudo tee /srv/wourri/secrets/api_secret_key >/dev/null
sudo chmod 0600 /srv/wourri/secrets/api_secret_key
sudo chown root:root /srv/wourri/secrets/api_secret_key

# Vérification
sudo ls -la /srv/wourri/secrets/
# Doit afficher :
#   drwx------ 2 root root  ...
#   -rw------- 1 root root  ... postgres_password
#   -rw------- 1 root root  ... api_secret_key
```

#### Particularité whatsapp-server

`whatsapp-server` (Node.js) lit toujours `WOURI_API_KEY` depuis env var
(env-based pattern, pas FILE). Pour cohérence :
- Le contenu de `/srv/wourri/secrets/api_secret_key` DOIT être identique à
  `WOURI_API_KEY` dans `.env.prod`
- À chaque rotation, mettre à jour les **deux** sources
- Une issue backlog est ouverte pour migrer whatsapp-server vers le même
  pattern `*_FILE` (nécessite modif `app-baileys.js` côté Node, cross-repo)

```bash
# Synchroniser .env.prod avec le fichier secret
API_KEY=$(sudo cat /srv/wourri/secrets/api_secret_key)
sudo sed -i "s|^WOURI_API_KEY=.*|WOURI_API_KEY=$API_KEY|" /srv/wourri/.env.prod
```

#### Backup hors-VM (obligatoire)

Comme `.env.prod`, les fichiers `/srv/wourri/secrets/*` sont l'UNIQUE moyen
de redéployer en cas de perte VM. Les sauvegarder dans le gestionnaire de
secrets (1Password / Bitwarden) **avant le premier démarrage**.

> Sprint I.c.1 review OPS B4 : **sauvegarder `.env.prod` HORS de la VM** dans
> un gestionnaire de secrets (1Password, Bitwarden, Scaleway Secret Manager).
> En cas de perte de la VM (disque corrompu, suppression accidentelle), ce
> fichier est l'UNIQUE moyen de redéployer (POSTGRES_PASSWORD irrécupérable
> sans dump chiffré avec l'ancien password). Audit obligatoire à chaque
> rotation de secret : mettre à jour le coffre AVANT la VM.

### 6. Login GHCR (pull privé)

Si les images sont privées sur `ghcr.io` :

```bash
# Créer un PAT GitHub (Settings → Developer settings → Personal access tokens
# (classic) → scope `read:packages` uniquement). À mettre dans `~/.gh-pat`.
chmod 600 ~/.gh-pat
cat ~/.gh-pat | docker login ghcr.io -u <github-username> --password-stdin
```

### 7. Premier démarrage

```bash
cd /srv/wourri
docker compose --env-file .env.prod -f docker-compose.prod.yml pull
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d postgres

# Attendre postgres healthy (~30s)
docker compose -f docker-compose.prod.yml ps

# Appliquer les migrations Alembic
docker compose --env-file .env.prod -f docker-compose.prod.yml run --rm wouri-api /app/scripts/run_migrations.sh

# Démarrer les services applicatifs
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d wouri-api whatsapp-server
```

### 8. Scanner le QR code WhatsApp (one-shot)

Le port 3001 est bindé sur 127.0.0.1 → invisible depuis Internet. Pour scanner le QR :

```bash
# Depuis votre poste local
ssh -L 3001:127.0.0.1:3001 wourri@<vm-ip>

# Puis dans un navigateur local
open http://localhost:3001/qr-page
# Scanner avec WhatsApp mobile (Paramètres → Appareils liés)
```

La session est ensuite persistée sur le volume nommé `wourri_wa_auth` — pas besoin de re-scanner sauf si vous supprimez le volume.

### 9. Healthchecks

```bash
# Depuis la VM
curl -fsS http://127.0.0.1:8000/health   # wouri-api : status "ok" attendu
curl -fsS http://127.0.0.1:3001/health   # whatsapp-server : status "ok" attendu
```

---

## Activer le déploiement automatique CI

Une fois le premier déploiement manuel validé :

### Préparer une clé SSH dédiée à la CI (NE PAS réutiliser la clé admin)

> Sprint I.c.1 review SEC B1 : `appleboy/ssh-action` exige une clé sans
> passphrase (script non-interactif). Si la clé admin perso est utilisée et
> que l'org GitHub est compromise (token leak, employé interne), l'attaquant
> obtient un accès `wourri@vm` équivalent. **Mitigations obligatoires** :
> (1) clé dédiée CI, (2) `command=`/`from=` restrictif côté `authorized_keys`
> de la VM, (3) rotation 90 jours documentée + calendrier.

```bash
# Sur votre poste local — clé ed25519 dédiée à la CI (jamais réutilisée)
ssh-keygen -t ed25519 -f ~/.ssh/wourri_ci -C "wourri-github-actions-$(date +%F)" -N ""

# Sur la VM Scaleway — restreindre la commande exécutable + le scope IP
# Le `command=` enferme la clé dans une seule commande (le runbook deploy).
# `restrict` désactive port-forwarding, X11, agent-forwarding (le compromis
# d'une clé CI ne donne pas un shell général). Note : `from=` n'aide pas
# avec les GH-hosted runners (IPs Azure changeantes) — la restriction de
# commande est notre rempart principal.
cat >> /home/wourri/.ssh/authorized_keys <<'EOF'
restrict,command="cd /srv/wourri && exec docker compose --env-file .env.prod -f docker-compose.prod.yml ${SSH_ORIGINAL_COMMAND#*'docker compose --env-file .env.prod -f docker-compose.prod.yml '}" ssh-ed25519 AAAA...CLEPUBLIQUE...
EOF
```

> **Calendrier rotation 90 jours** (à reporter dans un agenda partagé) :
> - Date dernière rotation : `YYYY-MM-DD` (à remplir)
> - Prochaine rotation : `YYYY-MM-DD + 90j`
> - Procédure : générer nouvelle clé → ajouter à `authorized_keys` → mettre
>   à jour `SCALEWAY_SSH_KEY` dans GitHub Secrets → tester un deploy →
>   supprimer ancienne clé d'`authorized_keys`.

### Configurer les secrets GitHub

`Settings → Secrets and variables → Actions → New repository secret` :

| Secret | Valeur |
|---|---|
| `SCALEWAY_HOST` | IP publique de la VM |
| `SCALEWAY_USER` | `wourri` |
| `SCALEWAY_PORT` | `22` (ou port custom) |
| `SCALEWAY_SSH_KEY` | contenu de `~/.ssh/wourri_ci` (clé privée CI dédiée, jamais la clé admin) |

### Activer le job deploy

`Settings → Secrets and variables → Actions → Variables → New repository variable` :

| Variable | Valeur |
|---|---|
| `DEPLOY_API_ENABLED` | `true` |
| `DEPLOY_WA_ENABLED` | `true` (créé en Sprint I.c.2) |

À partir de cet instant, chaque push sur `APIPy` ou `whatsappServeur` déclenche : build → push ghcr.io → SSH pull + migrate + restart.

---

## Opérations courantes

### Voir les logs

```bash
# Live tail
docker compose -f docker-compose.prod.yml logs -f wouri-api whatsapp-server

# Dernières 200 lignes
docker compose -f docker-compose.prod.yml logs --tail 200 wouri-api
```

### Mettre à jour manuellement (sans CI)

```bash
cd /srv/wourri
docker compose --env-file .env.prod -f docker-compose.prod.yml pull
docker compose --env-file .env.prod -f docker-compose.prod.yml run --rm wouri-api /app/scripts/run_migrations.sh
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d
docker image prune -f
```

### Rollback vers une version antérieure

Toutes les images sont taggées avec le SHA commit (`sha-<long-sha>`).

```bash
# Dans .env.prod
API_IMAGE_TAG=sha-1234567890abcdef...    # SHA du commit qui marchait

# Puis
docker compose --env-file .env.prod -f docker-compose.prod.yml pull wouri-api
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d wouri-api
```

### Rotation du `WOURI_API_KEY`

Le secret est partagé entre `wouri-api` (validation `X-API-Key`) et `whatsapp-server` (envoi `X-API-Key`).

> **Sprint I.c.1 review OPS B2 — downtime de 30 s à 2 min INÉVITABLE**
> Docker Compose recrée les containers SÉQUENTIELLEMENT (jamais simultanément).
> Pendant la fenêtre où l'un a la nouvelle clé et l'autre l'ancienne, toutes
> les requêtes WhatsApp → API renvoient 401. **Planifier la rotation hors
> heures de pic** (nuit CI = 02h00 UTC = 02h00 Abidjan).
> Issue backlog "dual-key pour rotation zero-downtime" (validation 2 clés
> simultanément côté API pendant 5 min) — non livré Sprint I.c, à prévoir
> avant prod réelle. Référence : ROADMAP #209.

```bash
# 1. Générer une nouvelle clé
NEW_KEY=$(openssl rand -base64 32)

# 2. Sauvegarder l'ancienne dans le coffre-fort (gestionnaire de secrets)
#    AVANT de l'écraser localement (filet de sécurité en cas d'oubli).

# 3. L'écrire dans .env.prod
sudo sed -i "s|^WOURI_API_KEY=.*|WOURI_API_KEY=$NEW_KEY|" /srv/wourri/.env.prod

# 4. Recharger les 2 services dans la foulée (downtime ~30 s)
#    `up -d` recrée le container si l'env a changé.
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d wouri-api whatsapp-server

# 5. Vérifier que les 2 services repartent OK (sinon rollback ancienne clé) :
curl -fsS http://127.0.0.1:8000/health
curl -fsS http://127.0.0.1:3001/health

# 6. Mettre à jour le coffre-fort avec la NOUVELLE clé (sinon perte irréversible).
```

### Rotation du `POSTGRES_PASSWORD`

```bash
# 1. Changer le mot de passe dans Postgres
docker compose -f docker-compose.prod.yml exec postgres \
  psql -U wourri -d wourri_prod -c "ALTER USER wourri PASSWORD 'NEW_PWD';"

# 2. L'écrire dans .env.prod
sed -i "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=NEW_PWD|" /srv/wourri/.env.prod

# 3. Restart wouri-api (postgres n'a pas besoin de redémarrer pour cette opération)
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d wouri-api
```

### Sauvegardes automatiques (cron daily) — OBLIGATOIRE avant Sprint J

> **Sprint I.c.1 review OPS B3** : sans backup auto + rotation + restore testé,
> le système est en zone rouge (RPO/RTO indéfinis). À mettre en place AVANT
> le premier déploiement effectif Sprint J.

#### 1. Créer le dossier de backups

```bash
sudo mkdir -p /srv/wourri/backups
sudo chown wourri:wourri /srv/wourri/backups
sudo chmod 700 /srv/wourri/backups
```

#### 2. Script de backup `/srv/wourri/backup.sh`

```bash
#!/usr/bin/env bash
# Wourri — Sauvegarde quotidienne (Postgres + sessions WhatsApp + .env.prod).
# Rétention : 30 jours. Upload off-site optionnel via rclone (Scaleway Object Storage).
set -euo pipefail

BACKUP_DIR="/srv/wourri/backups"
DATE="$(date +%F)"
RETENTION_DAYS=30
COMPOSE="docker compose --env-file /srv/wourri/.env.prod -f /srv/wourri/docker-compose.prod.yml"

cd /srv/wourri

echo "[backup] $(date -u +%FT%TZ) start"

# 1. Dump Postgres (toutes les bases — gzip → ~quelques MB)
$COMPOSE exec -T postgres pg_dumpall -U "$(grep ^POSTGRES_USER .env.prod | cut -d= -f2)" \
    | gzip > "$BACKUP_DIR/db_$DATE.sql.gz"

# 2. Session WhatsApp (perte = re-scan QR)
docker run --rm \
    -v wourri_wa_auth:/source:ro \
    -v "$BACKUP_DIR":/backup \
    alpine \
    tar czf "/backup/wa_auth_$DATE.tgz" -C /source .

# 3. user_preferences + pending_messages (volume wa_data)
docker run --rm \
    -v wourri_wa_data:/source:ro \
    -v "$BACKUP_DIR":/backup \
    alpine \
    tar czf "/backup/wa_data_$DATE.tgz" -C /source .

# 4. .env.prod (CRITIQUE — backup local en plus du gestionnaire de secrets)
#    Chmod 600 hérité du fichier source.
cp /srv/wourri/.env.prod "$BACKUP_DIR/env_prod_$DATE"

# 5. Rotation : supprimer les backups > RETENTION_DAYS jours
find "$BACKUP_DIR" -type f -mtime "+$RETENTION_DAYS" -delete

# 6. (Optionnel) Upload off-site Scaleway Object Storage via rclone
#    Pré-requis : `rclone config` avec un remote `scw-backup`.
#    Décommenter quand le remote est configuré :
# rclone sync "$BACKUP_DIR" scw-backup:wourri-backups/$(hostname)/ \
#     --include "*_$DATE.*" --include "env_prod_$DATE"

# 7. Ping de fin vers healthchecks.io (issue #220)
#    Sans ping en 26h, healthchecks.io envoie une alerte email.
#    `[ -n "..." ]` : ne ping que si la variable est définie (graceful no-op).
#    `|| echo` : un échec ping est non-fatal (le backup réussit même sans ping).
[ -n "${HEALTHCHECKS_BACKUP_URL:-}" ] && \
    curl -fsS -m 10 --retry 3 "$HEALTHCHECKS_BACKUP_URL" >/dev/null || \
    echo "[backup] WARN: ping healthchecks.io échoué (non-fatal)"

echo "[backup] $(date -u +%FT%TZ) done — $(du -sh "$BACKUP_DIR" | cut -f1)"
```

> Note : `backup.sh` doit pouvoir lire `$HEALTHCHECKS_BACKUP_URL` depuis
> `.env.prod`. Solution sourcée dans la crontab (cf. §3 ci-dessous).

```bash
sudo chmod +x /srv/wourri/backup.sh
sudo chown wourri:wourri /srv/wourri/backup.sh
```

#### 3. Cron daily (02h15 UTC)

```bash
sudo crontab -u wourri -e
# Ajouter :
# `set -a; . /srv/wourri/.env.prod; set +a` source les vars du .env.prod
# (notamment HEALTHCHECKS_BACKUP_URL) pour que backup.sh puisse les lire.
15 2 * * * set -a && . /srv/wourri/.env.prod && set +a && /srv/wourri/backup.sh >> /srv/wourri/backups/backup.log 2>&1
```

#### 4. Test de restauration (OBLIGATOIRE — un backup non testé = pas de backup)

À faire en environnement dev/staging AVANT prod réelle. Procédure dans
[Section Restauration](#restauration-postgres-après-incident) ci-dessous.

#### 5. Monitoring externe (healthchecks.io) — issue #220

Sans monitoring externe, un cron de backup qui s'arrête silencieusement n'est
découvert qu'après incident. Healthchecks.io résout ce problème en envoyant
une alerte email/Slack si un ping attendu n'arrive pas dans la fenêtre prévue.

##### a) Créer le compte + 3 checks

1. S'inscrire sur https://healthchecks.io (gratuit, 20 checks)
2. Dans **Projects → Wourri (nouveau projet)** → créer 3 checks :

| Check name | Schedule | Grace time | Usage |
|---|---|---|---|
| `wourri-backup-daily` | Cron `15 2 * * *` (02h15 UTC) | 60 min | Ping de `backup.sh` |
| `wourri-api-health` | Period `5 min` | 10 min | Ping périodique `/health` wouri-api |
| `wourri-wa-health` | Period `5 min` | 10 min | Ping périodique `/health` whatsapp-server |

3. Pour chaque check, copier l'URL `https://hc-ping.com/<uuid>` et la mettre
   dans `.env.prod` :
   ```bash
   sudo nano /srv/wourri/.env.prod
   # Remplir :
   #   HEALTHCHECKS_BACKUP_URL=https://hc-ping.com/<uuid-backup>
   #   HEALTHCHECKS_API_URL=https://hc-ping.com/<uuid-api>
   #   HEALTHCHECKS_WA_URL=https://hc-ping.com/<uuid-wa>
   ```

##### b) Configurer l'alerte email/Slack

Sur healthchecks.io : **Integrations → Email / Slack / Discord / Webhook**.
Recommandation : email vers `adcdevteam2025@gmail.com` minimum, ajouter Slack
si une instance équipe existe.

##### c) Ping de fin de `backup.sh`

Déjà intégré dans le template `backup.sh` ci-dessus (étape 7). Le ping est
graceful : si `HEALTHCHECKS_BACKUP_URL` est vide, le backup tourne quand même.

##### d) Cron de ping `/health` toutes les 5 min

Ces 2 pings remontent l'état applicatif (Postgres → wouri-api → whatsapp-server).
Si `/health` répond non-200 ou ne répond pas dans la fenêtre, alerte
healthchecks.io.

```bash
sudo crontab -u wourri -e
# Ajouter (en plus de la ligne backup déjà présente) :
*/5 * * * * set -a && . /srv/wourri/.env.prod && set +a && [ -n "$HEALTHCHECKS_API_URL" ] && curl -fsS -m 5 http://127.0.0.1:8000/health >/dev/null && curl -fsS -m 5 "$HEALTHCHECKS_API_URL" >/dev/null
*/5 * * * * set -a && . /srv/wourri/.env.prod && set +a && [ -n "$HEALTHCHECKS_WA_URL" ] && curl -fsS -m 5 http://127.0.0.1:3001/health >/dev/null && curl -fsS -m 5 "$HEALTHCHECKS_WA_URL" >/dev/null
```

Logique : on n'envoie le ping QUE si `/health` répond 200. Si `/health` est
KO, healthchecks.io détecte l'absence de ping en 10 min (grace time) et alerte.

##### e) Vérifier le setup

```bash
# Forcer un ping immédiat (utile pour valider chaque URL)
curl -fsS "$HEALTHCHECKS_BACKUP_URL"   # ⇒ "OK"

# Sur healthchecks.io dashboard, le check correspondant doit passer "up"
# en < 5 secondes.
```

##### f) Limites

- **Healthchecks.io est gratuit jusqu'à 20 checks** — largement suffisant pour
  Wourri staging. Si l'app grossit (10 services), envisager Uptime-kuma
  (self-hosted) — tracé issue #220.
- **Détecte la perte de service, pas la dégradation lente**. Pour des SLO
  type latence p95, prévoir Grafana + Prometheus dans un Sprint ultérieur.

---

### Restauration Postgres après incident

```bash
# 1. Stopper wouri-api pour libérer la base
docker compose --env-file .env.prod -f docker-compose.prod.yml stop wouri-api

# 2. Restaurer le dump (DESTRUCTIF — confirme la date)
gunzip < /srv/wourri/backups/db_YYYY-MM-DD.sql.gz | \
    docker compose --env-file .env.prod -f docker-compose.prod.yml \
    exec -T postgres psql -U $(grep ^POSTGRES_USER /srv/wourri/.env.prod | cut -d= -f2)

# 3. Redémarrer wouri-api
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d wouri-api

# 4. Healthcheck
curl -fsS http://127.0.0.1:8000/health
```

---

### Sauvegarder la session WhatsApp (volume `wourri_wa_auth`)

Critique : sa perte = re-scan QR obligatoire.

```bash
docker run --rm \
  -v wourri_wa_auth:/source:ro \
  -v /srv/wourri/backups:/backup \
  alpine \
  tar czf /backup/wa_auth_$(date +%F).tgz -C /source .
```

Restauration :

```bash
docker compose -f docker-compose.prod.yml stop whatsapp-server
docker run --rm \
  -v wourri_wa_auth:/target \
  -v /srv/wourri/backups:/backup \
  alpine \
  sh -c "cd /target && tar xzf /backup/wa_auth_YYYY-MM-DD.tgz"
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d whatsapp-server
```

### Sauvegarder la base Postgres

```bash
docker compose -f docker-compose.prod.yml exec postgres \
  pg_dump -U wourri wourri_prod | gzip > /srv/wourri/backups/db_$(date +%F).sql.gz
```

---

## Troubleshooting

| Symptôme | Diagnostic | Solution |
|---|---|---|
| `wouri-api` reste `unhealthy` >15 min | Cold-start premier deploy (download modèles ~3-4 GB) | Patienter, vérifier `docker logs wouri-api` montre progress |
| `whatsapp-server` log `WhatsApp non connecté` | Session manquante ou expirée | Re-scan QR via tunnel SSH (cf. §8) |
| `pull access denied` sur `ghcr.io` | Image privée + pas loggé | `docker login ghcr.io` (cf. §6) |
| `permission denied` sur `/app/auth_baileys` | Volume créé en root | `docker compose down && docker volume rm wourri_wa_auth && docker compose up -d` (perd session) |
| Migration Alembic timeout | 2 workers uvicorn démarrent en parallèle | TOUJOURS appliquer les migrations AVANT `up -d` (cf. `run_migrations.sh`) |
| `password authentication failed` Postgres | Clé `.env.prod` désynchronisée avec password réel | Cf. §Rotation POSTGRES_PASSWORD |
| Workflow CI échoue à `Login to GHCR` | Repo privé sans `packages: write` | Vérifier `permissions:` dans `.github/workflows/deploy-api.yml` |

---

## Coûts estimés

| Composant | Coût mensuel |
|---|---|
| VM Scaleway DEV1-M | ~8 EUR |
| Stockage block storage 40 GB | ~3 EUR |
| Bande passante sortante (premières 100 GB gratuites) | 0 EUR |
| **Total estimé staging** | **~11 EUR/mois** |

Pour passer en prod avec ~100 utilisateurs simultanés : prévoir DEV1-L (16 EUR/mois) ou GP1-XS (~35 EUR/mois).

---

## Liens

- Issue parent : [#201 Sprint I — Préparation déploiement production](https://github.com/ouedraogoissouf2012/wourri/issues/201)
- ROADMAP : [#209 ROADMAP finalisation Wourri](https://github.com/ouedraogoissouf2012/wourri/issues/209)
- Suite : Sprint J — Premier déploiement staging effectif
