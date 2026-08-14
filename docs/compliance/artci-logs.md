# Conformité ARTCI — Politique de rétention des logs (Wourri)

**Référence réglementaire** : loi ivoirienne n° 2013-450 relative à la
protection des données à caractère personnel — régulateur **ARTCI** (Autorité
de Régulation des Télécommunications/TIC de Côte d'Ivoire). ⚠ Ne pas confondre
avec l'APDP (Bénin/Mali).

**Décision d'architecture** : [ADR-0025](../adr/0025-retention-logs-pii-artci.md)
(accepté, 2026-08-14, issue #215).

**Principe appliqué** : toute donnée à caractère personnel conservée dans les
logs a une **durée de conservation bornée et justifiée par sa finalité**, avec
purge automatique au-delà du seuil.

---

## 1. Inventaire des données personnelles dans les logs

| Donnée | Où | Forme | Sensibilité |
|---|---|---|---|
| Numéro WhatsApp / user_id | logs applicatifs, feedback | **pseudonymisée** — hash SHA-256 salé `usr_*` (`app/core/pii_utils.py`, salt `PII_SALT`, P0-05) | faible (réidentification impossible sans le salt) |
| Transcriptions des vocaux agriculteurs | logs applicatifs (`[ASR] Transcription brute`, providers ASR) | **en clair** | élevée — contenu libre dicté par l'utilisateur |
| Questions / réponses de conversation | logs applicatifs (chat, DeepSeek — historique loggé en volumétrie, pas en contenu) | partielle | moyenne |
| Réponses du bot (tronquées ≤ 120 car.) | `feedback-YYYY-MM.jsonl` | en clair (contenu **généré par le bot**, pas par l'utilisateur) | faible |
| Audio brut (dumps debug STT) | `debug_audio/` | en clair | élevée — **désactivé hors dev** (flag DEBUG, cf. `.env.example`) ; interdit en production |
| Adresses IP | access log uvicorn (stdout) | en clair | moyenne |

## 2. Durées de conservation et justifications

| Catégorie | Fichiers | Rétention | Finalité justifiant la durée |
|---|---|---|---|
| Logs applicatifs API | `logs/wourri-YYYY-MM-DD.log` + legacy `wourri.log` | **30 jours** (`LOG_RETENTION_DAYS`) | Diagnostic d'incidents et support opérationnel. Au-delà de 30 j, la valeur diagnostique est nulle → conservation non justifiée. |
| Feedback produit pseudonymisé | `logs/feedback-YYYY-MM.jsonl` + legacy `feedback.jsonl` | **365 jours** (`FEEDBACK_RETENTION_DAYS`) | Amélioration du corpus et reporting C5 sur un **cycle agricole complet** (saisonnalité annuelle des cultures). Données pseudonymisées, sans contenu utilisateur brut. |
| Stdout des conteneurs (API, WhatsApp, Postgres) | Docker `json-file` | borné en **taille** : 10 Mo × 5 fichiers par service | Consultation opérationnelle immédiate (`docker logs`). La borne de taille limite de fait la durée (rotation continue). |
| Files de travail corpus | `data/feedback_negatif.jsonl`, `data/feedback_candidates.jsonl` | jusqu'à traitement humain | Files de revue native (ADR-0019) — données métier pseudonymisées, pas des logs. Purge manuelle après promotion/rejet. |
| Agrégation Loki (staging uniquement, ADR-0016) | volume `wourri_staging_loki` | **14 jours** (`retention_period: 336h`, compactor actif — `config/loki/loki-config.yml`) | Observabilité staging. Déjà conforme (< 30 j). |

## 3. Mécanisme de purge (automatique)

- **Rotation par nommage daté** (aucun rename, sûr avec 2 workers uvicorn) :
  - log applicatif : un fichier par **jour** (`wourri-YYYY-MM-DD.log`) ;
  - feedback : un fichier par **mois** (`feedback-YYYY-MM.jsonl`).
- **Purge quotidienne in-app** : tâche de fond démarrée par le lifespan FastAPI
  (`app/main.py`), exécutée au démarrage puis toutes les 24 h. Fonction pure
  `app/core/log_retention.py::purge_old_logs()` — idempotente, testée
  unitairement. Les fichiers legacy (`wourri.log`, `feedback.jsonl`) sont
  purgés sur leur mtime avec la rétention de leur catégorie.
- **Secours ops (manuel/cron)** : `python scripts/purge_logs.py [--dry-run]`
  — même logique, utilisable depuis l'hôte ou un exec conteneur, quel que soit
  l'orchestrateur (compose ou Dokploy, cf. ADR-0024).

## 4. RPO / RTO des logs

- **RPO logs** : 24 h — les logs applicatifs ne sont **pas sauvegardés**
  (données de diagnostic, pas des données métier) ; la perte maximale acceptée
  est le volume du jour. Les données métier (corpus PostgreSQL, session
  WhatsApp) ont leur propre stratégie de backup (cf. `docs/deployment.md`).
- **RTO logs** : immédiat — la perte de logs n'empêche pas le service de
  fonctionner ; le flux stdout reprend dès le redémarrage du conteneur.

## 5. Chiffrement at-rest — état et dette tracée

- **État actuel** : les volumes (VPS Contabo, ADR-0024) ne sont **pas chiffrés
  at-rest**. Contabo ne fournit pas de chiffrement disque par défaut ; LUKS
  exigerait une réinstallation de l'hôte partagé (Dokploy/Traefik en place).
- **Mitigations en vigueur** : accès serveur par clé SSH uniquement ; secrets
  en fichiers mode 0600 (pattern `*_FILE`, issue #213) ; identifiants
  utilisateurs pseudonymisés dans les logs (P0-05) ; rétention courte (30 j)
  du seul contenu PII en clair ; hébergement UE (Allemagne).
- **Dette tracée** : chiffrement at-rest à réévaluer **avant tout passage en
  production grand public** (options : hôte dédié LUKS, volume chiffré
  dm-crypt, ou suppression du logging des transcriptions en clair). Décision à
  acter par un ADR dédié le moment venu.
- **Transfert hors Côte d'Ivoire** : les données résident en UE (Contabo,
  Allemagne — ADR-0024 §Souveraineté). Point à déclarer dans toute démarche
  ARTCI formelle.

## 6. Contrôles associés (hors périmètre de ce document)

- Pseudonymisation des user_id : `app/core/pii_utils.py` (P0-05) — exiger
  `PII_SALT` non vide en production.
- Dashboard d'observabilité **sans contenu PII** : ADR-0017.
- Contenu des logs (transcriptions en clair) : la *durée* est traitée ici ; la
  *minimisation du contenu* (ne plus logger les transcriptions brutes en
  production) est une amélioration distincte à évaluer.

---

**Révision** : 2026-08-14 (création — lot sécurité F2, issue #215).
Toute modification des durées de rétention passe par une mise à jour de
l'ADR-0025 et de ce document.
