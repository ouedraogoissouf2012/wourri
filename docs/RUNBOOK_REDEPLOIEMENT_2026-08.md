# Runbook — Redéploiement Wourri (Dokploy / Contabo)

**Date** : 2026-08-15
**Objet** : redéployer les ~22 correctifs/features mergés depuis le 1er déploiement (14/08) et non encore en prod (auto-deploy désactivé, accès SSH à rétablir).
**Cible réelle** : VPS Contabo, **Dokploy v0.29** (Swarm + Traefik), 3 services natifs (ADR-0026). ⚠️ **PAS** `docker compose` manuel, **PAS** Scaleway/ghcr.io — Dokploy **build depuis Git**. Le `docker-compose.prod.yml` du repo est une *référence* (env/volumes/secrets), pas le mécanisme réel.

---

## 0. Répartition
- **Toi** : rétablir l'accès SSH, clics dans l'UI Dokploy (Deploy/Redeploy).
- **Moi** : vérif SSH, 2 étapes post-deploy manuelles, smoke-tests.

## 1. Pré-requis (avant de toucher à Dokploy)
- [ ] Accès SSH rétabli : `ssh -i ~/.ssh/wourri_deploy_ed25519 marcel@serveur.africandigitconsulting.com` répond.
- [ ] UI Dokploy accessible.
- [ ] Branches à jour côté GitHub — **déjà OK** : `APIPy` (HEAD #406) + `whatsappServeur` (HEAD #403).
- [ ] Build Type Dokploy des 2 services applicatifs = **Dockerfile** (Nixpacks échoue).

## 2. Bonne nouvelle : quasi AUCUNE nouvelle config requise
Les nouveaux réglages mergés ont tous des **défauts sûrs** → rien à ajouter dans Dokploy :
- **#94 filtre LM** : `ENABLE_LM_RESCORING=False` par défaut → **pass-through, zéro impact** (binaire KenLM absent = OK, dette tracée).
- **#297 A1** : `NLU_MIN_CONFIDENCE=0.2` (inchangé), `IVR_MAX_SEMANTIC_DISTANCE` **non utilisé** → rien à poser.
- **#387 rate limit** : `RATE_LIMIT=120/minute` par défaut ; whatsapp-server **exempté** (X-API-Key).
- **#215 rétention PII** : `LOG_RETENTION_DAYS=30` / `FEEDBACK_RETENTION_DAYS=365` par défaut.
- **#376 Piper FR** : `PIPER_MODEL_FR` **déjà fixé dans l'image** (voix téléchargée au build) → rien à poser.

## 3. Env / secrets à VÉRIFIER (doivent déjà exister depuis le 14/08)
**Service `wouri-api`** :
- [ ] `ENV=production` (⚠️ sans ça → mode dev ; avec ça, `API_SECRET_KEY` devient **obligatoire** sinon l'API fait `sys.exit(1)`)
- [ ] `POSTGRES_HOST` (nom du service postgres Dokploy), `POSTGRES_PORT=5432`, `POSTGRES_USER`, `POSTGRES_DB`
- [ ] `POSTGRES_PASSWORD_FILE=/run/secrets/postgres_password` (secret) — ou `POSTGRES_PASSWORD` selon la config Dokploy
- [ ] `API_SECRET_KEY` (secret ou env) — **obligatoire en prod**
- [ ] `DEEPSEEK_API_KEY`, `DEEPSEEK_BASE_URL=https://api.deepseek.com/v1` (sinon chat 500)
- [ ] `PII_SALT` (sinon warning ; générer : `python -c "import secrets; print(secrets.token_hex(32))"`)
- [ ] `TZ=UTC`

**Service `whatsapp-server`** :
- [ ] `NODE_ENV=production`, `PORT=3001`, `WOURI_API_URL=http://wouri-api:8000`
- [ ] `WOURI_API_KEY` (= la même valeur que `API_SECRET_KEY`)
- [ ] `USER_PREFS_FILE=/app/data/user_preferences.json`, `PENDING_MESSAGES_FILE=/app/data/pending_messages.json`

## 4. Procédure de déploiement

### 4.1 — TOI (Dokploy UI)
0. ⚠️ **NE PAS toucher au service `postgres`** (image `pgvector/pg16` inchangée dans ce lot) — un redeploy inutile risquerait les données. Seuls `wouri-api` et `whatsapp-server` changent.
1. Service **wouri-api** → **Deploy/Redeploy** → Dokploy pull `APIPy` à jour + rebuild `Dockerfile.prod`.
   ⏱ Build long (~5-10 min : torch CPU + préchargement des modèles ML dans l'image).
2. Attendre **healthy** (healthcheck `/health`, `start_period=120s`).
3. Service **whatsapp-server** → **Deploy/Redeploy** (branche `whatsappServeur`).

### 4.2 — MOI (SSH — post-deploy MANUEL, ⚠️ pièges du 1er déploiement)
Trouver les noms des conteneurs : `docker ps --format '{{.Names}}' | grep -iE 'wouri-api|postgres|whatsapp'`
0. **Backup DB avant migrations** (filet de sécurité) :
   `docker exec <postgres> pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" > ~/wourri-backup-predeploy-$(date +%F).sql`
1. **Migrations Alembic** (`bash` explicite car pas de bit +x) :
   `docker exec <wouri-api> bash /app/scripts/run_migrations.sh`
2. **Peuplement corpus IVR dans pgvector** (SINON recherche IVR vide → tout tombe sur DeepSeek) :
   `docker exec <wouri-api> python /app/scripts/import_corpus_ivr.py`
   (idempotent : TRUNCATE + réinsert ; embeddings via le modèle **déjà dans l'image** #374)

## 5. Smoke-tests post-deploy (⚠️ header `X-API-Key` obligatoire sauf `/health`)
> Note : formats (query params vs body, noms de champs) basés sur `CLAUDE.md` + le code des routers — **à confirmer au 1er appel réel** (non exécutés ici, serveur down). Ajuster si un 422 signale un champ.
Sur le serveur (`K=<API_SECRET_KEY>`) :
- [ ] `curl -sf http://localhost:8000/health` → 200 (api)
- [ ] `curl -sf http://localhost:3001/health` → 200 (whatsapp)
- [ ] **TTS dioula** : `curl -X POST "http://localhost:8000/api/tts/dioula?text=aw%20ni%20ce&is_french=false" -H "X-API-Key: $K"` → audio
- [ ] **TTS français (Piper #376)** : `curl -X POST "http://localhost:8000/api/tts/french?text=bonjour" -H "X-API-Key: $K"` → audio FR
- [ ] **Corpus IVR (le fix critique #374/#369)** : `curl -X POST http://localhost:8000/api/chat/ -H "X-API-Key: $K" -H "Content-Type: application/json" -d '{"message":"quand semer le maïs","language":"dioula","city":"Bouaké"}'` → réponse avec `meta.source = ivr_exact` (PAS `deepseek`)
- [ ] **Météo « demain » (#406)** : même endpoint, `"message":"sini san bɛ na wa?"` → `meta.source = meteo_prevision`
- [ ] **WhatsApp bout-en-bout** : envoyer un message réel au numéro lié → réponse audio dioula
- [ ] **Reconnexion (#308/#396)** : `docker logs <whatsapp> | grep -i reconnect` → pas de boucle/rafale

## 6. Rollback
- Dokploy garde les déploiements précédents → **Rollback** dans l'UI (build antérieur).
- Migration problématique (rare) : `docker exec <wouri-api> alembic downgrade -1`.

## 7. Points de vigilance
- **Session WhatsApp** (`wourri_wa_auth`) : NE PAS supprimer → sinon re-scan QR (tunnel SSH `-L 3001:127.0.0.1:3001` + `/qr-page`).
- **Cache modèles** (`wourri_hf_cache`) : les modèles n'ont **pas changé** dans ce lot → NE PAS purger (éviterait un re-download inutile).
- **Corpus** : pas de changement du JSON dans ce lot → l'import re-peuple à l'identique (sûr). Toujours ré-importer si le JSON change.
- **FORWARDED_ALLOW_IPS** : reste au défaut (interne only, whatsapp exempté). À revoir seulement si expo publique future (#202).

---
*Sources vérifiées le 2026-08-15 : `docker-compose.prod.yml`, `app/config.py`, `Dockerfile.prod`, `scripts/run_migrations.sh`, `scripts/import_corpus_ivr.py`, `app/routers/*`, ADR-0026, mémoire déploiement.*
