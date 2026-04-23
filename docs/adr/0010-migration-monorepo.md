# ADR-0010 — Migration vers monorepo

**Statut** : accepté
**Date** : 2026-04-23
**Auteur** : Claude (assistant)
**Valideur** : Ruben (validé le 2026-04-23)
**ADRs liés** : tous (impact structurel global)

---

## Contexte

### Architecture git actuelle

Le projet Wourri vit sur **1 repo GitHub** (`ouedraogoissouf2012/wourri`) avec **3 branches orphelines indépendantes**, chacune contenant un arbre de fichiers complètement différent :

| Branche | Contenu | Langage | État |
|---|---|---|---|
| `APIPy` | API backend Wourri (54 commits, Sprint 1 validé) | Python / FastAPI | Active |
| `whatsappServeur` | Serveur WhatsApp (Baileys) | Node.js | Active |
| `wourri` | Déploiement cPanel (5 commits de janvier 2026) | PHP / mail | Orpheline |

Les branches n'ont **aucun historique commun**. Ce n'est pas un pattern de feature branches — c'est un pattern de "branches-comme-projets-séparés" (comparable à `gh-pages`, mais utilisé pour du développement actif, ce qui n'est pas l'usage prévu).

### Problèmes identifiés

**🔴 Critiques (bloquants à terme)** :

1. **CI/CD impossible à configurer proprement**
   - GitHub Actions déclenche par branche. Avec 3 arbres différents sur 3 branches, 1 workflow `ci.yml` ne peut pas s'appliquer cohéremment partout.
   - Solution actuelle : aucune CI. Non tenable en production payante.

2. **Sécurité aveugle**
   - Dependabot, Snyk, GitHub code scanning analysent **l'arbre de la branche par défaut** (`wourri` = PHP cPanel).
   - → Aucun des outils de sécurité ne surveille le Python (`wouri-api`) ni le Node (`whatsapp-server`).
   - Toute vulnérabilité dans `requirements.txt` ou `package.json` passe inaperçue.

3. **Audit bailleurs désastreux**
   - Un bailleur (AFD, Banque Mondiale, ONG) arrivant sur GitHub voit `wourri` par défaut : 5 commits de janvier 2026, code PHP orphelin.
   - Première impression : "projet abandonné".
   - Critique vu les ambitions B2G/ONG documentées dans [vision.md](../vision.md).

**🟠 Gênants à moyen terme (3-12 mois)** :

4. **Code sharing impossible**
   - Schémas JSON partagés entre Python et Node (`user_id`, `language`, `intent`), configs communes, types : dupliqués de part et d'autre.
   - Aucune source de vérité unique pour les contrats inter-services.

5. **Changements cross-service fragmentés**
   - Sprint 1 a prouvé que les 2 services évoluent ensemble : `P0-02` (backend) dépendait de `P0-02a` (WhatsApp).
   - Avec l'architecture actuelle : 2 commits sur 2 branches séparées, coordination manuelle, risque d'incohérence en prod.

6. **Onboarding difficile**
   - Nouveau contributeur : `git clone` → tombe sur `wourri` (PHP cPanel) → confusion. Doit apprendre l'architecture inhabituelle avant de coder.
   - Impact important quand l'équipe grandira (prévu dans [vision.md](../vision.md)).

7. **Tags et releases incohérents**
   - Un tag `v1.0.0` sur `APIPy` ne correspond pas au même état fonctionnel qu'un `v1.0.0` sur `whatsappServeur`.
   - Besoin de conventions maison (`v1.0.0-apipy`, `v1.0.0-ws`) non-standard.

### Pourquoi cette architecture existe aujourd'hui

Héritage historique probable :
- Le repo original a commencé avec la branche `wourri` pour du déploiement cPanel mail
- Les projets Python et WhatsApp ont été ajoutés comme branches orphelines pour éviter de créer 2 repos distincts
- Workflow ad-hoc qui fonctionnait à l'échelle d'un seul dev

Ce n'est pas une erreur — juste un pattern qui a vieilli face à l'ambition actuelle du projet.

---

## Options étudiées

### Option A — Status quo (rejetée)

Garder les 3 branches orphelines.

**Pour** : zéro effort immédiat, pas de disruption.

**Contre** : accumule les 7 problèmes identifiés. Devient ingérable avec l'arrivée d'une équipe ou d'une demande d'audit bailleur.

### Option B — Multi-repo (rejetée)

Créer 2 repos GitHub distincts : `wouri-api` + `wouri-whatsapp`.

**Pour** :
- Séparation nette, permissions indépendantes par repo
- Release cycles isolés
- CI dédiée par projet

**Contre pour Wourri spécifiquement** :
- **Les 2 services communiquent en permanence** (X-API-Key, JSON body, audio files) — couplage fort = antipattern multi-repo
- **Changements cross-service = 2 PRs coordonnées** (Sprint 1 l'a montré : fix backend + fix WhatsApp ensemble)
- **Code sharing nécessite un 3ᵉ repo** (libs communes) — complexité inutile à notre échelle
- **Tags de release cross-service à coordonner manuellement**
- **Audit bailleur** : doit consulter 2 repos pour comprendre le produit — pas simple
- **Onboarding** : 2 clones, 2 README, 2 CI à lire

Multi-repo serait pertinent si les services étaient vraiment découplés (contrats API stables, équipes séparées, cycles asynchrones). Ce n'est pas le cas.

### Option C — Monorepo (retenue)

Un seul repo avec structure en sous-dossiers :

```
wourri/
├── wouri-api/           # API Python backend (ex-APIPy)
├── whatsapp-server/     # Serveur Node (ex-whatsappServeur)
├── shared/              # types, schémas JSON, configs communes
├── docs/                # ADRs, vision, plan d'action
├── .github/             # templates issues/PRs + CI unifiée
├── README.md            # présentation produit globale
└── CONTRIBUTING.md      # guide dev
```

**Pour** :
- Changements cross-service **atomiques** (1 PR modifie API + WhatsApp ensemble)
- Code partagé trivial (`shared/` folder)
- **Un seul historique git cohérent**
- CI unifiée avec filtres par path (`paths: wouri-api/**` pour Python, `paths: whatsapp-server/**` pour Node)
- Dependabot scanne **toutes** les dépendances (Python + Node)
- Bailleurs et futurs contributeurs voient le produit **entier d'un coup**
- Tags de release = état global cohérent du système
- Standard industriel 2026 (Google, Meta, Uber, Airbnb, Vercel tous monorepo)

**Contre** :
- Migration = 1-2 jours de travail dédié
- Repo légèrement plus gros (négligeable à notre échelle)
- CI avec filtres `paths` à configurer (standard, bien documenté)

---

## Décision

**Option C — Migration vers monorepo** (validée par Ruben, date à confirmer).

### Structure cible

```
wourri/                          # racine du repo, branche main
├── wouri-api/                   # import depuis APIPy via git subtree
│   ├── app/
│   ├── tests/
│   ├── dictionnaires/
│   ├── data/
│   ├── finetune/
│   └── requirements.txt
├── whatsapp-server/             # import depuis whatsappServeur via git subtree
│   ├── app-baileys.js
│   ├── package.json
│   └── .env.example
├── shared/                      # nouveau
│   ├── types/                   # schémas JSON partagés (messages chat, feedback)
│   ├── config/                  # constantes communes (codes langues, cultures)
│   └── README.md
├── docs/                        # docs globales (déjà partiellement présent dans APIPy)
│   ├── vision.md
│   ├── constraints.md
│   ├── PLAN_ACTION_2026-04.md
│   └── adr/
├── .github/
│   ├── ISSUE_TEMPLATE/
│   │   ├── action-plan.md
│   │   └── bug.md
│   ├── pull_request_template.md
│   └── workflows/
│       ├── ci-python.yml        # triggered on paths: wouri-api/**
│       ├── ci-node.yml          # triggered on paths: whatsapp-server/**
│       └── docs-lint.yml        # triggered on paths: docs/**
├── README.md                    # présentation produit + architecture
├── CONTRIBUTING.md              # guide dev + workflow issues/PRs
├── LICENSE                      # à déterminer (propriétaire probable)
└── .gitignore                   # consolidé (Python + Node)
```

### Branche par défaut

`main` (standard moderne, remplace `APIPy` et `wourri` comme défaut).

### Branches conservées en archive

- `APIPy`, `whatsappServeur`, `wourri` **ne sont pas supprimées** après migration
- Marquées comme archivées (dans la description GitHub) pour traçabilité
- Tags backup `backup/APIPy-pre-migration`, etc., créés avant migration

---

## Plan de migration

### Phase 0 — Préparation (1 jour, avant la migration)

1. Créer un nouveau repo GitHub `wourri-monorepo` (ou renommer l'existant après export — à décider au moment)
2. Vérifier que toutes les PRs ouvertes sont mergées ou fermées
3. Vérifier que tous les tests passent sur APIPy et whatsappServeur
4. Créer les tags backup :
   - `backup/APIPy-pre-monorepo-migration`
   - `backup/whatsappServeur-pre-monorepo-migration`
   - `backup/wourri-pre-monorepo-migration`

### Phase 1 — Import des 2 projets (1-2 heures)

```bash
# Créer nouveau repo monorepo localement
mkdir wourri-monorepo
cd wourri-monorepo
git init
git remote add origin git@github.com:ouedraogoissouf2012/wourri-monorepo.git

# README initial
echo "# Wourri — Assistant agricole voice-first WhatsApp/IVR" > README.md
git add README.md
git commit -m "chore: initial README"

# Import APIPy comme sous-dossier wouri-api/
git subtree add --prefix=wouri-api \
    git@github.com:ouedraogoissouf2012/wourri.git APIPy

# Import whatsappServeur comme sous-dossier whatsapp-server/
git subtree add --prefix=whatsapp-server \
    git@github.com:ouedraogoissouf2012/wourri.git whatsappServeur
```

Résultat : **historique des deux projets préservé**, fusionné dans un seul repo.

### Phase 2 — Structure monorepo (demi-journée)

1. Créer `shared/` avec structure minimale
2. Déplacer les docs globales de `wouri-api/docs/` vers `docs/` (racine monorepo)
3. Consolidation `.gitignore` racine (Python + Node + IDE)
4. Création `.github/ISSUE_TEMPLATE/`, `pull_request_template.md`
5. Création `CONTRIBUTING.md` documentant workflow issues/PRs
6. Consolidation `README.md` produit

### Phase 3 — CI unifiée (demi-journée)

Configuration GitHub Actions avec path filters :

```yaml
# .github/workflows/ci-python.yml
on:
  pull_request:
    paths: ['wouri-api/**']
  push:
    branches: [main]
    paths: ['wouri-api/**']

# .github/workflows/ci-node.yml
on:
  pull_request:
    paths: ['whatsapp-server/**']
  push:
    branches: [main]
    paths: ['whatsapp-server/**']
```

Chaque workflow installe ses deps + lance ses tests + linter dans son sous-dossier.

### Phase 4 — Validation + push (2-3 heures)

1. Clone frais du monorepo en local, vérifier que le pipeline complet marche :
   - `cd wouri-api && pytest`
   - `cd ../whatsapp-server && npm test` (si tests Node existants)
   - `cd .. && ls -R shared docs .github`
2. Test manuel : lancer backend + whatsapp-server depuis le monorepo, envoyer message WhatsApp
3. Push `main` sur GitHub
4. Configuration GitHub : `main` = default branch, protection rules (require review, require status checks)
5. Mise à jour des 3 anciennes branches (`APIPy`, `whatsappServeur`, `wourri`) : ajouter un commit final avec un README qui pointe vers le nouveau repo/structure

### Phase 5 — Nettoyage (1 heure)

1. Mise à jour du `.env.example` dans les 2 sous-dossiers
2. Mise à jour du [PLAN_ACTION_2026-04.md](../PLAN_ACTION_2026-04.md) pour marquer cet ADR-0010 comme exécuté
3. Mise à jour des ADRs existants qui référencent l'ancienne structure (références de paths si besoin)
4. Annonce aux éventuels utilisateurs/intégrateurs du changement de structure

### Durée totale estimée

**1-2 jours calendaires** de travail concentré.

### Réversibilité

Les tags backup + les 3 anciennes branches préservées permettent un rollback complet en < 10 minutes si problème critique détecté après migration.

---

## Critère de déclenchement

Cette migration est **exécutée quand la première de ces conditions est atteinte** :

1. **Sprint 2 (P1 corpus/ASR) stabilisé en production** — datasets African Next Voices intégrés, benchmark ASR effectué, Omnilingual décision tranchée.
2. **Arrivée imminente d'un premier contributeur externe** — onboarding mérite une structure propre.
3. **Demande d'audit d'un bailleur** — nécessite un repo présentable en l'état.

**Horizon estimé** : 3-6 semaines à partir du 2026-04-23.

**Pas avant** : tant qu'aucune de ces conditions n'est remplie, éviter la disruption — continuer sur la structure actuelle.

---

## Conséquences

### Positives

- **CI/CD enfin possible** : workflows path-filtered, tests auto sur chaque PR
- **Sécurité retrouve son utilité** : Dependabot, code scanning, Snyk surveillent vraiment Python + Node
- **Audit bailleur simplifié** : 1 repo, 1 README, 1 structure pro
- **Code partagé trivial** : schémas JSON, configs, constantes dans `shared/`
- **Changements cross-service atomiques** : 1 PR pour toucher API + WhatsApp ensemble (fin des fragmentations type Sprint 1 P0-02 + P0-02a)
- **Onboarding futur équipier** : 1 clone, 1 README, compréhension du produit en 30 min
- **Tags de release cohérents** : `v1.0.0` = état global du système
- **Alignement standards industriels** 2026

### Négatives assumées

- **1-2 jours bloqués** pour exécuter la migration
- **Besoin de retester** le pipeline end-to-end après migration
- **Les PRs ouvertes** au moment de la migration devront être replantées sur le nouveau repo (à éviter en timant la migration quand il n'y a pas de PR ouverte importante)
- **Liens externes** vers `github.com/.../wourri/blob/APIPy/...` deviennent cassés — à documenter dans la release note
- **Configuration cPanel du déploiement `wourri` branch** à adapter si elle existe encore et tourne

### Verrous futurs levés

- Déploiement CI/CD automatique possible (non-trivial actuellement)
- Passage à WhatsApp Business Cloud API ([ADR-0006](0006-migration-whatsapp-cloud-api.md) futur) facilité par code sharing
- Intégration P2 (IVR téléphonique, ADR-0009 futur) plus simple dans une structure unifiée
- Fine-tuning pipeline partagé entre langues (P2+) gagne à vivre dans `shared/finetune/`

---

## Références

- [docs/vision.md](../vision.md) — ambition produit qui justifie cet effort structurel
- [docs/PLAN_ACTION_2026-04.md](../PLAN_ACTION_2026-04.md) — action [P2-05] (doc manquante) partiellement adressée par cet ADR
- [Sprint 1 bilan](../../../../.claude/projects/c--Users-USER-PC-Documents-propre---moi-wourri/memory/project_sprint1_securite_fait.md) — preuve empirique que les changements cross-service sont fréquents
- [git subtree documentation](https://www.atlassian.com/git/tutorials/git-subtree) — technique retenue pour la migration
- Google Monorepo blog post 2016 : *Why Google stores billions of lines of code in a single repository*
- Vercel/Next.js monorepo structure exemple public

---

## Historique

- **2026-04-23 (rédaction)** — Rédaction initiale suite à discussion sur templates GitHub. Recommandation monorepo vs multi-repo argumentée. 3 options étudiées.
- **2026-04-23 (accepté)** — Ruben valide Option C (monorepo). Statut `accepté`. Exécution planifiée après stabilisation Sprint 2 P1 corpus/ASR (horizon 3-6 semaines).
