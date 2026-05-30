# Session du 29-30 mai 2026 — Récap accessible

> **Pour qui ?** Toi (Ruben), à tête reposée. Tout est expliqué en
> français normal, sans jargon. Schémas ASCII inclus.
> **Objectif** : que tu puisses comprendre TOUT ce qui a été fait,
> sans avoir à me redemander.

---

## Sommaire

1. [Ce qu'on a fait en 1 paragraphe](#1-ce-quon-a-fait-en-1-paragraphe)
2. [Sécurité — Docker secrets + dual-key](#2-sécurité)
3. [Refactor `bambara_validator` — 732 → mieux](#3-refactor-bambara_validator)
4. [Environnement staging — la 2e machine de test](#4-environnement-staging)
5. [ADR-0013 SSH — 3 options pour mieux sécuriser](#5-adr-0013-ssh)
6. [Compléments utiles](#6-compléments-utiles)
7. [Glossaire des termes techniques](#7-glossaire)

---

## 1. Ce qu'on a fait en 1 paragraphe

Ton projet Wourri était fonctionnel mais avait accumulé de la "dette
technique" : des choix faits rapidement il y a 6 mois qui rendaient
le code difficile à maintenir et la sécurité fragile. En 1 session,
on a livré **15 améliorations mergées + 2 propositions en attente
de ta décision**. Le bot lui-même fonctionne exactement comme avant
(0 changement utilisateur visible), mais en interne, c'est beaucoup
plus propre, sécurisé, et préparé pour la production.

---

## 2. Sécurité

### a) Docker secrets — Pourquoi c'est important

**Avant** : tes mots de passe (Postgres, clé API) étaient dans le
fichier `.env.prod` en clair.

```
.env.prod (texte brut sur disque)
POSTGRES_PASSWORD=ToutLeMondeQuiPeutVoirCeFichierVoitMonMotDePasse
```

**Problème** :
- Si quelqu'un fait `docker inspect wouri_api_prod`, il voit tes
  variables d'env (donc tes mots de passe)
- Si un attaquant accède à `/proc/<pid>/environ` sur ta VM, idem
- Si tu push accidentellement `.env.prod` sur Git (ça arrive), c'est
  game over

**Après** : tes mots de passe sont dans des fichiers protégés
`/srv/wourri/secrets/*` (mode 600 root:root), montés dans le
container à `/run/secrets/*` en lecture seule.

```
/srv/wourri/secrets/postgres_password (mode 600 root:root)
/srv/wourri/secrets/api_secret_key    (mode 600 root:root)
```

Le container lit ces fichiers via une fonction Python `_read_file_secret()`.
**Aucun mot de passe n'est jamais dans les variables d'environnement.**

### b) Rotation dual-key — Pourquoi c'est important

**Avant** : si tu voulais changer ta clé `WOURI_API_KEY` (parce qu'elle
était compromise par exemple), il fallait :
1. Restart le serveur API avec la nouvelle clé
2. Restart le serveur WhatsApp avec la nouvelle clé
3. Entre les 2, des messages WhatsApp arrivaient mais étaient rejetés (HTTP 403)

→ Downtime ~30 secondes minimum, parfois plus.

**Après** : tu peux mettre 2 clés simultanément (l'ancienne ET la
nouvelle). Le serveur API accepte les deux. Procédure :

```bash
# 1. Génère la nouvelle clé
NEW_KEY=$(openssl rand -base64 32)
OLD_KEY=$(cat /srv/wourri/secrets/api_secret_key)

# 2. Configure les 2 clés
echo $NEW_KEY > /srv/wourri/secrets/api_secret_key   # nouvelle clé devient principale
export WOURI_API_KEY_PREVIOUS=$OLD_KEY                # ancienne en fallback

# 3. Restart API SEUL — accepte les 2 clés pendant la fenêtre
docker compose restart wouri-api

# 4. Restart WhatsApp avec la nouvelle clé (zéro perte de messages)
# ... config WhatsApp avec NEW_KEY ...
docker compose restart whatsapp-server

# 5. Après 5 min, vide WOURI_API_KEY_PREVIOUS et redémarre API
unset WOURI_API_KEY_PREVIOUS
docker compose restart wouri-api
```

**Résultat** : rotation de clé = **0 message perdu**.

### c) Script `check_env_consistency.py` — Pourquoi c'est important

Tes variables d'env sont définies à 4 endroits :
- `docker-compose.dev.yml` (dev local)
- `docker-compose.prod.yml` (prod)
- `.env.prod.template` (doc + valeurs par défaut)
- `.github/workflows/ci-api.yml` (CI tests)

**Problème classique** : tu ajoutes `OPENAI_API_KEY` dans le compose
prod, tu oublies de l'ajouter dans le template. Au prochain déploiement
prod, ça crashe avec une erreur peu lisible.

**Le script vérifie** :
- Toute `${VAR:?...}` du compose est déclarée dans le template
- Toute variable du template est utilisée dans le compose (sauf
  whitelist explicite pour les outils externes)

**Intégré dans la CI** : si tu oublies, la PR ne passe pas. Tu vois
l'erreur immédiatement.

---

## 3. Refactor `bambara_validator`

### Le problème : code dupliqué

`tools/bambara_validator.py` faisait 732 lignes. Dedans :

- **3 fonctions TF-IDF quasi-identiques** (Bayelemabaga, Koumankan,
  Findora) : ~70 lignes copiées-collées 3 fois. Seuls 2 paramètres
  changent (les seuils numériques).

- **4 fonctions de scraping HTTP quasi-identiques** (Bamadaba, VOA,
  Bambara.org, Bamanankan) : ~15 lignes copiées-collées 4 fois.

- **13 variables globales éparpillées** (`_baye_fr`, `_kouman_fr`,
  `_findora_fr`, etc.)

**Conséquence** : ajouter une nouvelle source = modifier 4 endroits
différents (variables globales + fonction de chargement + fonction
TF-IDF + entrée dans le registre `SOURCES_PRINCIPALES`). On finit
par oublier un endroit et ça plante en silence.

### La solution : classes propres

```
Avant : 3 fonctions TF-IDF + 4 fonctions HTTP + 13 globals + dispatch par nom
Après : 1 classe `Source` (interface) + 2 implémentations + 7 instances + dispatch par type
```

Schéma :

```
┌──────────────────────────────────┐
│  Source (interface abstraite)    │
│  - load() : charger les données  │
│  - find(concept) : retourner     │
│       Counter{terme: score}       │
└────────────┬─────────────────────┘
             │
       ┌─────┴─────┐
       │           │
       ▼           ▼
┌──────────┐ ┌──────────────────┐
│TfidfSrc  │ │ HttpScraperSrc   │
│paire     │ │ url + fenêtre +  │
│fr/dyu +  │ │ User-Agent       │
│seuils    │ │                  │
└──────────┘ └──────────────────┘
     │              │
     ├ Bayelemabaga ├ Bamadaba
     ├ Koumankan    ├ VOA
     └ Findora      ├ Bambara.org
                    └ Bamanankan
```

**Avantage** : ajouter une nouvelle source = créer 1 instance + 1 ligne
dans le registre. **1 endroit au lieu de 4**.

### Découpage en 3 PRs (pour mieux reviewer)

- **PR #250** : on crée la classe `Source` + on migre Bayelemabaga
  comme "preuve de concept". On garde tout le reste intact. → Si bug
  dans le design, on a perdu peu de temps.

- **PR #251** : on migre Koumankan + Findora. Pas de design nouveau,
  juste extension.

- **PR #252** : on crée `HttpScraperSource` + on migre les 4 scrapers
  + on unifie le dispatcher (avant : `if nom == "bayelemabaga"` =
  hardcodé. Après : `if isinstance(result, Counter)` = par type).

**Workflow strict 4 phases** appliqué sur PR #250 (la plus risquée) :
PLAN → CODE → REVIEW par 2 agents → SYNTHÈSE. Les 2 agents reviewers
ont trouvé 4 bugs MAJEURS que j'ai corrigés avant push :

1. **Bug non-idempotence** : si on appelait `_load_all_splits()` 2
   fois, le corpus était doublé en mémoire (= TF-IDF faussé).
2. **Violation encapsulation** : accès direct aux variables privées
   `_fr`, `_dyu` depuis l'extérieur de la classe.
3. **Test contract tautologique** : le test "anti-régression" ne
   testait rien parce qu'il mockait trop large.
4. **Branche non couverte** : le cas "aucun split présent" jamais testé.

Tous fixés avant le merge.

### Résultat chiffré

| Métrique | Avant | Après |
|---|---|---|
| Globals | 13 | 2 |
| Classes | 0 | 3 |
| Instances réutilisables | 0 | 7 |
| Lignes | 732 | 925 (avec docstrings + tests) |
| Tests | 0 | 26 |
| Ajouter une source | 4 endroits | 1 endroit |

---

## 4. Environnement staging

### C'est quoi un "staging" ?

Imagine 2 maisons identiques :
- **Maison A (prod)** : où vivent tes vrais utilisateurs WhatsApp
- **Maison B (staging)** : une copie EXACTE de la maison A, mais
  inhabitée. Tu peux y casser des choses, tester des modifs, sans
  perturber les vrais utilisateurs.

C'est ESSENTIEL parce que :
- Tu ne veux pas que tes utilisateurs subissent un bug que tu n'avais
  pas vu en dev local
- Avant la "Phase E pgvector" (qui supprime ChromaDB), il FAUT mesurer
  la vraie latence en conditions production-like

### Ce qui est livré (PR #254, en attente)

J'ai écrit TOUS les fichiers de config pour que tu puisses créer
cette 2e machine :
- `docker-compose.staging.yml` — comment lancer les 5 conteneurs
- `.env.staging.template` — quelles variables à remplir
- `config/loki/loki-config.yml` — config du serveur de logs
- `config/promtail/promtail-config.yml` — agent qui collecte les logs
- `docs/staging-deployment.md` — **runbook 632 lignes** pour suivre
  étape par étape

### Ce que TU dois faire (ne nécessite pas de tiers)

Suivre le runbook. Étapes (toi seul) :
1. Créer une VM Scaleway DEV1-S (~10 €/mois) — via console web
2. Configurer le DNS `staging-api.wourri.ci` chez ton registrar
3. Installer Docker sur la VM
4. Créer les secrets sur la VM
5. Copier les fichiers du repo
6. `docker compose up -d`
7. Scanner le QR WhatsApp staging avec un téléphone dédié
8. Faire les 10 tests E2E documentés

**Temps total** : ~1-2h si tu suis le runbook.

### Pourquoi c'est crucial pour Phase E pgvector

L'issue **#203 (Sprint K)** veut basculer définitivement de ChromaDB
vers PostgreSQL + pgvector. Mais l'ADR-0008 dit : "on bascule
SEULEMENT si la latence pgvector ≤ 1.5× celle de ChromaDB,
**MESURÉE EN STAGING**".

Sans staging = pas de mesure = pas de bascule = pgvector reste
indéfiniment en mode "dual" (les 2 marchent en parallèle, gaspillage
RAM + complexité).

---

## 5. ADR-0013 SSH

### Le problème actuel

Quand tu déploies via GitHub Actions, le workflow se connecte en SSH
à ta VM avec une clé SSH **statique** (toujours la même). Cette clé
est stockée dans "GitHub Secrets" (encrypted, mais pas révocable
automatiquement).

**Si quelqu'un vole cette clé** (compromission de l'org GitHub,
employé malveillant chez Anthropic/GitHub, fork malicieux mergé,
etc.), il a accès permanent à ta VM jusqu'à ce que TU la révoques
manuellement.

### Les 3 options analysées dans l'ADR

#### Option A — Self-hosted runner GitHub Actions
Tu installes un "agent GitHub" directement sur ta VM. Quand le
workflow se déclenche, il s'exécute en local sur la VM (pas de SSH
du tout).

- ✅ Zéro clé SSH
- ❌ L'agent garde des secrets en mémoire entre les jobs (risque si
  un workflow malveillant tourne dessus)
- ❌ Tu dois mettre à jour l'agent manuellement (~30 min/mois)

#### Option B — Tailscale SSH (ma recommandation)
Tailscale = service qui crée un VPN privé entre tes machines (basé
sur WireGuard, open source). Le runner GitHub se connecte au VPN
avec une clé éphémère, accède à ta VM via le VPN.

- ✅ Clé éphémère (expire après 90j, révocable instantanément)
- ✅ Logs centralisés (qui s'est connecté, quand, depuis où)
- ✅ Tu peux fermer le port 22 publique (le SSH passe par le VPN)
- ✅ Gratuit jusqu'à 100 machines (tu en as 1-2)
- ⚠️ Dépendance Tailscale (mais migration possible vers Headscale
  self-hosted si besoin)

#### Option C — Scaleway OIDC + IAM
Authentification GitHub Actions → Scaleway via un token JWT court
(15 min de durée de vie). Pas de clé du tout.

- ✅ Aucun secret long-terme
- ❌ Pas sûr que Scaleway supporte ce mode pour GitHub Actions
  (à vérifier dans leur doc 2026)
- ❌ Verrou vendor Scaleway le plus fort des 3 options

### Pourquoi je recommande B (Tailscale)

| Critère | Option A | **Option B** | Option C |
|---|---|---|---|
| Sécurité | Bon | Bon | Excellent |
| Mise en oeuvre | 4-6h | **2-3h** | 6-10h (incertain) |
| Maintenance | 30 min/mois | **5 min/mois** | 0 |
| Verrou vendor | Aucun | Léger | Fort |
| Audit logs | GitHub | **Tailscale + GitHub** | Scaleway |
| Faisabilité | Sûre | **Sûre** | Incertaine |

### Ce qu'il faut faire

**Lire la PR #253** (442 lignes mais bien structurées), valider
ou rebattre, puis si OK je peux exécuter le plan (2-3h de prép code
+ tes décisions cloud).

---

## 6. Compléments utiles

### Comprendre les "PR" et la branche

Tu travailles sur 2 branches principales :
- `APIPy` : la branche de prod du serveur API Python (wouri-api)
- `whatsappServeur` : la branche du serveur WhatsApp Node.js

Chaque amélioration passe par une "Pull Request" (PR) :
1. Je crée une branche depuis APIPy (ex: `feat/issue-202-staging`)
2. Je commit mes changements
3. Je push la branche sur GitHub
4. Je crée une PR qui propose de merger ma branche dans APIPy
5. Le CI (tests automatiques) tourne sur la PR
6. Si vert + tu approuves → on merge (ça intègre dans APIPy)

### Comprendre les "Issues" et les "Sprints"

- **Issue** = un ticket qui décrit un problème à résoudre. Ex:
  "#222 = dual-key rotation API key"
- **Sprint** = un groupe d'issues bossées ensemble (ex: Sprint I =
  préparation déploiement, regroupe issues #213, #214, #216, etc.)

Quand une PR résout une issue, on "ferme" l'issue (`gh issue close`).

### Comprendre les "ADRs"

Architecture Decision Record = document qui grave une décision
importante.

Format : `docs/adr/00NN-titre.md`. Statuts :
- **proposé** = rédigé, attend validation
- **accepté** = validé, à implémenter
- **complété** = implémenté
- **rejeté** = étudié mais non retenu

Règle projet : **aucun code structurant sans ADR validé**.

### Comprendre `pgvector` vs `ChromaDB`

Les 2 sont des "bases de vecteurs" — elles stockent des nombres qui
représentent du texte (embeddings) et permettent de trouver les textes
les plus proches d'une recherche.

- **ChromaDB** : ce qu'on utilise aujourd'hui en prod. Léger mais
  limité (pas de jointures SQL, pas de transactions).
- **pgvector** : extension PostgreSQL. Permet de stocker les vecteurs
  dans la même base que tes données métier. Plus solide long-terme.

ADR-0001 a décidé : on migre vers pgvector. ADR-0008 décrit le plan
en 5 phases (A→E). Aujourd'hui : phases A à D livrées (l'infra est
prête, on a mesuré 0% de divergence en mode dual). Phase E (bascule
définitive + suppression ChromaDB) en attente de mesure latence en
staging.

### Comprendre Docker / docker-compose / images / volumes

- **Docker image** = un "snapshot" de ton application empaqueté
  (code + Python + tous les modèles ML). Ex: `wourri-api:latest`
- **Container** = une instance d'une image qui tourne sur ta machine
- **Volume** = du stockage persistant. Le container peut crasher, le
  volume reste. Ex: `wourri_pgdata_prod` = la base Postgres.
- **docker-compose.yml** = recette qui décrit plusieurs containers
  qui doivent tourner ensemble (postgres + api + whatsapp).

### Comment lire un log Loki

```bash
# Tunnel SSH vers ta VM
ssh -L 3100:127.0.0.1:3100 wourri@<IP_STAGING>

# Récupère tous les logs des 5 dernières min
curl -s "http://localhost:3100/loki/api/v1/query_range?query=%7Bstack%3D%22wourri-staging%22%7D&start=$(date -d '5 min ago' +%s)000000000" | jq .

# Cherche les erreurs uniquement
curl -s "http://localhost:3100/loki/api/v1/query_range?query=%7Bstack%3D%22wourri-staging%22%7D%20%7C%3D%20%22error%22" | jq .
```

Mais c'est pénible. Plus simple : installer Grafana sur ton poste
local et l'utiliser comme UI (cf. runbook section 7.2).

---

## 7. Glossaire

| Terme | Définition simple |
|---|---|
| **ADR** | Document qui grave une décision technique importante |
| **CI** | Continuous Integration. Les tests automatiques qui tournent sur chaque PR |
| **CD** | Continuous Deployment. Le déploiement automatique sur ta VM après merge |
| **PR** | Pull Request. Une proposition de changement à reviewer avant merge |
| **Issue** | Un ticket qui décrit un problème ou une amélioration |
| **Sprint** | Un groupe d'issues bossées ensemble |
| **Container** | Une appli empaquetée et isolée (Docker) |
| **Volume** | Du stockage persistant pour un container Docker |
| **GHCR** | GitHub Container Registry. Où on stocke nos images Docker |
| **Embedding** | Un vecteur de nombres qui représente un texte |
| **TF-IDF** | Algorithme qui mesure la spécificité d'un mot dans un corpus |
| **pgvector** | Extension PostgreSQL pour stocker des vecteurs |
| **ChromaDB** | Une base de vecteurs alternative (qu'on remplace par pgvector) |
| **Loki** | Serveur de logs centralisés (équivalent ELK light) |
| **Promtail** | Agent qui envoie les logs Docker à Loki |
| **Healthcheck** | Endpoint qui dit "je suis vivant" (ex: `/health`) |
| **OIDC** | Standard d'authentification basé sur JWT |
| **JWT** | JSON Web Token. Un token signé qui prouve une identité |
| **WireGuard** | Protocole VPN moderne (qu'utilise Tailscale) |
| **Single point of failure** | Un composant dont la panne arrête tout le système |
| **Rollback** | Revenir à une version précédente après un déploiement raté |
| **Workflow CI** | Le fichier `.github/workflows/*.yml` qui automatise les tests/deploy |
| **GitHub Actions** | Le système qui exécute les workflows CI sur les serveurs GitHub |

---

## Ce qui reste à faire (faisable à 2, sans tiers)

| Tâche | Effort | Faisable maintenant ? |
|---|---|---|
| **Forcer rebuild Chroma si tu as déjà une prod** | 5 min | OUI |
| **Lire + valider PR #253 (ADR-0013 SSH)** | 30 min lecture | OUI |
| **Lire + valider PR #254 (staging prep)** | 30 min lecture | OUI |
| **Migrer agri_dict → LookupSource (finir refactor #233)** | ~1h | OUI |
| **Créer les 3 followups pas créés (WOURI_API_KEY_FILE WA, url_resolver, API_SECRET_KEY_PREVIOUS_FILE)** | 15 min | OUI |
| **Augmenter couverture tests existants (objectif +10%)** | ~1-2h | OUI |
| **Nettoyer MEMORY.md (trop long, 200+ lignes)** | ~30 min | OUI |
| **Bumper corpus_ivr.json version pour forcer rebuild Chroma propre** | 5 min | OUI |

## Tâches qui nécessitent un tiers (reportées)

| Tâche | Tiers requis | Pourquoi |
|---|---|---|
| #215 ARTCI conformité | Avocat / Délégué Protection Données | Décisions juridiques RPO/RTO + rétention légale |
| Sprint J.2 provisionnement VM staging | Toi physiquement sur Scaleway | Compte cloud + carte bancaire |
| Sprint K Phase E pgvector | Débloqué par Sprint J.2 d'abord | Cycle de dépendances |
| Sprint O corpus dioula | Locuteur natif dioula CI | Validation linguistique |
| Sprint N ADRs structurants (AfroLID, etc.) | Recherche externe + benchmarks | Lourde investigation |

---

## Référence des PRs de cette session

| PR | Titre | Statut |
|---|---|---|
| #239 | TTS loudnorm normalisation | mergée |
| #240 | Tests STT helpers | mergée |
| #241 | Tests message_handler.js | mergée |
| #242 | check_env_consistency.py | mergée |
| #243 | Docs GHCR credential management | mergée |
| #244 | Postgres bind-mount | mergée |
| #245 | Dual-key rotation API key | mergée |
| #246 | import_corpus_ivr HF fallback | mergée |
| #248 | Preload ML models Docker | mergée |
| #235 | Pin SHA deploy-wa.yml | mergée |
| #249 | vdb_service HF fallback (bug embeddings) | mergée |
| #250 | Source ABC + TfidfSource (refactor #233 PR 1/3) | mergée |
| #251 | Koumankan + Findora vers TfidfSource (PR 2/3) | mergée |
| #252 | HttpScraperSource + dispatcher (PR 3/3) | mergée |
| **#253** | **ADR-0013 SSH hardening (3 options)** | **EN ATTENTE** |
| **#254** | **Sprint J.1 prep infra staging** | **EN ATTENTE** |

---

**Si tu veux plus de détail sur un point précis, ouvre la PR
correspondante sur GitHub et lis le diff. Les commits sont écrits
pour être lisibles individuellement.**
