# ADR-0025 — Rétention et purge des logs contenant des PII (conformité ARTCI)

**Statut** : accepté
**Date** : 2026-08-14
**Auteur(s)** : Claude (assistant) — lot sécurité F2, issue #215
**Valideur** : Ouedraogo Issouf (mandat d'orchestration du lot sécurité F2,
2026-08-14 : « ADR validé avant tout code » ; périmètre et direction fixés par
l'issue #215 elle-même — politique documentée + purge automatique > seuil)

---

## Contexte

État factuel vérifié dans le code (`origin/APIPy`, 2026-08-14) :

- **Logs applicatifs wouri-api** : `app/core/logging_config.py:56` attache un
  `logging.FileHandler` en mode append sur `logs/wourri.log`, **sans rotation
  ni purge**. Le fichier grossit indéfiniment.
- **Contenu PII en clair** : les transcriptions des vocaux agriculteurs sont
  logguées telles quelles — `app/routers/asr.py:161`
  (`"[ASR] Transcription brute: '%s'"`) et les 4 providers ASR
  (`mms_dyu_provider.py:99`, `mms_generic_provider.py:157`,
  `nemo_provider.py:124`, `omnilingual_provider.py:137`). Les identifiants
  utilisateurs (numéros WhatsApp) sont, eux, déjà pseudonymisés via
  `app/core/pii_utils.py` (SHA-256 salé, P0-05) partout où ils sont loggés
  (grep `logger.*user_id` sans `anonymize` → 0 résultat).
- **Feedback** : `app/routers/feedback.py:38` écrit `logs/feedback.jsonl`
  (append-only, sans purge). Contenu : timestamp, hash `usr_*` pseudonymisé,
  vote, intent, cultures, source, réponse du bot tronquée à 120 caractères.
  **Aucun texte utilisateur brut, aucun numéro en clair.** Consommé par
  `rapport_c5.py` (stats produit C5).
- **Stdout Docker** : borné en taille par `json-file` `max-size: 10m` /
  `max-file: 5` (`docker-compose.prod.yml`, fix M2-OPS #212) — ~50 Mo max par
  service, mais **aucune borne en durée**.
- **Volume `wourri_wa_logs`** : monté sur `/app/logs` du whatsapp-server, mais
  **aucun écrivain identifié** — pino loggue exclusivement sur stdout
  (`lib/logger.js`, branche `whatsappServeur`) ; grep des écritures fichiers
  dans `app-baileys.js` + `lib/*.js` → 0 résultat. Volume mort.
- **Multi-process** : `Dockerfile.prod:199-205` lance uvicorn avec
  `--workers 2` → **2 processus écrivent le même fichier de log** (append).
- **Exigence** : la réglementation ivoirienne (loi n° 2013-450 relative à la
  protection des données à caractère personnel, régulateur **ARTCI**) exige une
  durée de conservation *justifiée par la finalité*. Aucune politique n'est
  définie ni appliquée aujourd'hui (issue #215, review SEC MAJOR M4, PR #212).
- **Cible de déploiement** : Dokploy sur VPS Contabo (ADR-0026, accepté) — pas
  la VM Scaleway du runbook initial. Toute solution dépendant d'un cron hôte ou
  d'un montage spécifique à la VM Scaleway est fragile sur cette cible.

## Questions posées avant la décision

Cadre imposé par l'issue #215 et le mandat du lot sécurité F2 :

1. Quelle durée de rétention justifiée pour chaque catégorie de données ?
2. Quel mécanisme de purge automatique, sachant 2 workers uvicorn et une cible
   Dokploy (pas d'accès cron hôte garanti) ?
3. Que faire du chiffrement at-rest du volume ?

## Options étudiées

### Option A — Cron hôte + `find -mtime` (suggestion de l'issue)

- **Description** : un cron sur la VM purge les fichiers > 30 j dans les
  volumes Docker.
- **Avantages** : zéro code applicatif ; pattern ops classique.
- **Inconvénients** : dépend de l'hôte (chemins des volumes différents entre
  compose Scaleway et Dokploy — cf. ADR-0026 §Backups) ; invisible au repo
  (non versionné, non testé) ; ne résout pas la rotation du fichier actif
  `wourri.log` (un `find -mtime` ne purge jamais un fichier écrit en continu).
- **Coût** : faible en code, récurrent en ops.

### Option B — `TimedRotatingFileHandler` stdlib

- **Description** : remplacer le `FileHandler` par une rotation quotidienne
  stdlib avec `backupCount = rétention`.
- **Avantages** : stdlib, purge intégrée (`backupCount`).
- **Inconvénients** : **non sûr multi-process**. La rotation fait un
  `os.rename` ; avec `--workers 2`, chaque worker rotate indépendamment →
  double rename, écrasement du backup du jour, perte de lignes (footgun
  documenté de `logging.handlers` en multi-process).
- **Coût** : faible — mais introduit une corruption silencieuse en prod.

### Option C — Dépendance `concurrent-log-handler`

- **Description** : handler tiers avec verrous fichiers inter-process.
- **Avantages** : rotation multi-process correcte, maintenu.
- **Inconvénients** : nouvelle dépendance + verrous fichiers à chaque écriture
  (coût I/O), pour un besoin que le nommage par date résout sans verrou.
- **Coût** : moyen (dépendance à tracer, comportement verrous à tester).

### Option D — Fichiers datés append-only + purge in-app quotidienne *(retenue)*

- **Description** :
  - `wourri.log` → `wourri-YYYY-MM-DD.log` : le handler écrit dans le fichier
    du jour et **réouvre simplement le fichier du nouveau jour** au changement
    de date. **Aucun rename** → les 2 workers peuvent écrire le même fichier en
    append comme aujourd'hui, sans course.
  - `feedback.jsonl` → `feedback-YYYY-MM.jsonl` (mensuel) : la purge devient
    une suppression de fichier atomique, pas une réécriture de lignes
    (réécrire un JSONL pendant qu'un worker append = perte de données).
  - Purge : fonction pure `purge_old_logs()` (testable), déclenchée par une
    tâche quotidienne dans le lifespan FastAPI + script CLI
    `scripts/purge_logs.py` pour les ops. Idempotente → son exécution par les
    2 workers est sans danger.
- **Avantages** : zéro dépendance, zéro rename, portable (compose Scaleway,
  Dokploy, dev Windows), 100 % versionné et testé unitairement.
- **Inconvénients** : purge quotidienne pilotée par l'app (si l'app est
  arrêtée longtemps, la purge attend le prochain démarrage — acceptable : sans
  app, pas de nouveaux logs) ; deux fichiers « legacy » (`wourri.log`,
  `feedback.jsonl`) à purger par mtime pendant la transition.
- **Coût** : ~1 j (handler daté + purge + tests + docs).

### Comparatif

| Critère | A (cron hôte) | B (TimedRotating) | C (dépendance) | D (fichiers datés) |
|---|---|---|---|---|
| Sûr avec 2 workers | ✅ (n'écrit pas) | ❌ course rename | ✅ verrous | ✅ append-only |
| Purge le fichier actif | ❌ | ✅ | ✅ | ✅ (fichier du jour borné à 1 j) |
| Portable Dokploy/compose/dev | ❌ dépend hôte | ✅ | ✅ | ✅ |
| Versionné + testé dans le repo | ❌ | ✅ | ✅ | ✅ |
| Nouvelle dépendance | non | non | **oui** | non |
| Coût I/O par écriture | — | faible | verrou/écriture | faible |

## Décision

**Option D — fichiers datés append-only + purge in-app quotidienne + script CLI ops.**

**Durées de rétention** (configurables via `.env`, appliquées par la purge) :

| Catégorie | Fichiers | Rétention | Justification de finalité |
|---|---|---|---|
| Logs applicatifs (PII en clair possible : transcriptions) | `logs/wourri-YYYY-MM-DD.log` (+ legacy `wourri.log`) | **30 jours** (`LOG_RETENTION_DAYS=30`) | Diagnostic incidents / support. Aligné sur le seuil de l'issue #215 (> 30 j = non justifié). |
| Feedback pseudonymisé (aucun contenu utilisateur brut) | `logs/feedback-YYYY-MM.jsonl` (+ legacy `feedback.jsonl`) | **365 jours** (`FEEDBACK_RETENTION_DAYS=365`) | Amélioration produit / reporting C5 saisonnier (cycles agricoles annuels). Pseudonymisation SHA-256 salée (P0-05). |
| Stdout Docker | `json-file` | taille : 10 Mo × 5 par service | Complément : borné en taille ; durée effective courte en pratique. Documenté dans `docs/compliance/artci-logs.md`. |
| Files de travail corpus (`data/feedback_negatif.jsonl`, `data/feedback_candidates.jsonl`) | hors périmètre purge auto | jusqu'à traitement (revue native ADR-0019) | Ce sont des files de travail métier, pas des logs ; leur contenu (réponses du bot + hash pseudonymisés) ne contient pas de PII brute. |

**Volume `wourri_wa_logs`** : aucun écrivain (infra morte) — les logs du
whatsapp-server vivent sur stdout, bornés par `json-file`. Le montage nommé est
**conservé** dans les composes tant que l'image whatsapp-server déclare
`VOLUME /app/logs` (`Dockerfile.prod:85`, branche `whatsappServeur`) : le
retirer ferait créer un volume **anonyme** orphelin à chaque redeploy.
Suppression complète tracée en travail induit (retrait de la directive VOLUME
côté `whatsappServeur`, puis retrait du montage).

**Chiffrement at-rest** : non retenu dans ce lot. Le VPS Contabo n'offre pas de
chiffrement disque par défaut et un chiffrement LUKS impose une réinstallation
(ADR-0026 accepté sans). **Dette tracée** dans `docs/compliance/artci-logs.md`
§Chiffrement, avec mitigations actuelles (accès SSH par clé, fichiers secrets
0600, pseudonymisation des identifiants dans les logs) — à réévaluer avant tout
passage en production grand public.

## Conséquences

- **Positives** : durée de conservation bornée et justifiée par catégorie
  (exigence ARTCI) ; politique versionnée, testée, portable ; volume mort
  supprimé ; le fichier de log actif n'excède jamais 1 jour de données.
- **Négatives assumées** : les outils lisant `logs/feedback.jsonl`
  (`rapport_c5.py`) doivent lire le glob mensuel ; transition avec fichiers
  legacy purgés par mtime ; purge dépendante du cycle de vie de l'app (script
  CLI en secours pour les ops).
- **Migration / travail induit** :
  1. `app/core/logging_config.py` : handler daté (réouverture au changement de
     jour, aucun rename).
  2. `app/routers/feedback.py` : chemin mensuel `feedback-YYYY-MM.jsonl`.
  3. `app/core/log_retention.py` : `purge_old_logs()` pure + testable
     (fichiers datés par nom, legacy par mtime, jamais le fichier du jour).
  4. `app/main.py` : tâche quotidienne dans le lifespan (idempotente).
  5. `scripts/purge_logs.py` : CLI ops (`--dry-run`).
  6. `rapport_c5.py` : lecture glob `feedback-*.jsonl` + legacy.
  7. `docker-compose.prod.yml` / staging : commentaires rétention (`api_logs`)
     et statut `wa_logs` (mort mais requis par la directive VOLUME de l'image) ;
     `.env.example` / `.env.prod.template` : nouvelles variables.
     Travail induit ultérieur : retirer `VOLUME /app/logs` du Dockerfile.prod
     de la branche `whatsappServeur`, puis retirer le montage `wa_logs`.
  8. `docs/compliance/artci-logs.md` : politique complète (inventaire,
     finalités, durées, mécanisme, chiffrement, RPO/RTO logs).
  9. Tests unitaires : handler daté, purge (bornes, legacy, dry-run), chemin
     feedback mensuel.
  - **Rollback** : réversible (revenir au `FileHandler` fixe) ; aucun format de
    données modifié (JSONL identique, seul le nom de fichier change).
- **Verrous futurs** : si un jour l'app passe à N workers sur plusieurs hôtes,
  le nommage par date reste valide (append multi-writer par jour) ; une
  centralisation Loki (ADR-0016) pourra remplacer les fichiers — la politique
  de rétention documentée restera la référence (retention Loki = mêmes durées).

## Références

- Issue #215 (critical) — audit conformité ARTCI logs PII rétention > 30 j
- PR #212 (rotation json-file M2-OPS), mémoire Sprint H.1b (PII asr_client)
- Loi ivoirienne n° 2013-450 (protection des données à caractère personnel) —
  régulateur ARTCI (⚠ pas APDP, qui concerne Bénin/Mali)
- ADR-0017 (dashboard sans PII), ADR-0016 (Alloy/Loki), ADR-0026 (Dokploy,
  §Souveraineté : données hébergées en UE — à tracer pour l'ARTCI)
- Code vérifié : `app/core/logging_config.py`, `app/main.py:35-38`,
  `app/routers/feedback.py`, `app/core/pii_utils.py`, `docker-compose.prod.yml`,
  `Dockerfile.prod:199-205`, `lib/logger.js` (branche `whatsappServeur`)

## Historique

- 2026-08-14 — rédaction et acceptation (lot sécurité F2, issue #215). Statut
  « accepté » porté par le mandat d'orchestration du lot (la direction — 
  politique documentée + purge automatique — est celle prescrite par l'issue).
- 2026-08-14 — revue adversariale (10 angles) : durcissements intégrés —
  interrupteur `LOG_RETENTION_ENABLED` (les tests d'intégration exécutent le
  lifespan réel → purge désactivée sous pytest), rétentions validées `ge=1`
  + refus des valeurs négatives dans `purge_old_logs` (une rétention négative
  aurait rendu le fichier du jour candidat), scan par fichier protégé OSError
  (course inter-workers), bascule de jour transactionnelle dans le handler,
  CLI sans import de Settings (effets de bord d'import inadaptés à un cron),
  horloge unifiée `date.today()` (writer/handler/purge), montage `wa_logs`
  conservé (directive VOLUME de l'image — cf. §Décision).
