# Vision produit — Wourri

**Dernière révision** : 2026-08-11 (ADR-0024, transition Convex multi-tenant)

Ce document fige la vision long-terme du projet. Il est la **source de vérité
stratégique** pour toute décision d'architecture, ADR, ou plan d'implémentation.

Toute évolution de cette vision passe par un ADR qui amende explicitement
cette page.

---

## 1. Mission

Donner aux agriculteurs d'Afrique l'information climatologique et agronomique
en temps réel, dans leur langue, pour améliorer leurs récoltes.

**Différenciation** : accessible par voix, dans la langue locale de l'utilisateur,
même en zone à faible connectivité.

---

## 2. Utilisateurs cibles

- **Agriculteurs individuels** — usage direct, cœur de la promesse
- **Coopératives agricoles** — déploiement groupé, B2B
- **ONGs de développement** — sponsors et relais terrain
- **Gouvernements / services agricoles (ANADER en CI, équivalents régionaux)** —
  utilisateurs institutionnels à moyen terme

**Profil utilisateur** : francophones et locuteurs de langues africaines,
alphabétisation variable (donc voix > texte). Accès mobile limité, zones
rurales, connectivité instable.

---

## 3. Canaux

### Canal principal actuel

- **WhatsApp voice** (Baileys, port 3001) — ASR → NLU → réponse vocale dioula

### Canal principal à moyen terme (horizon 2-3 ans)

- **IVR téléphonique** (appel classique, sans internet)
  - Nécessite : infra SIP/voice (Twilio, Africa's Talking, ou opérateur local)
  - Contraintes : audio 8 kHz (vs qualité WhatsApp), latence temps-réel stricte
  - Raison stratégique : zones rurales sans couverture data doivent rester servies

### Canaux futurs possibles (non priorisés)

- App native Android light
- Interface web pour coopératives (dashboard, gestion utilisateurs)
- SMS pour notifications climatologiques push

**Règle d'architecture** : toute décision technique doit permettre d'ajouter
l'IVR téléphonique et le Web sans réécriture du cœur. Convex est le plan de
données et d'autorisation des nouveaux domaines métier multi-tenant. FastAPI
reste le plan de calcul pour l'ASR, le TTS, le NLU, les appels LLM et l'audio.
Les canaux sont des façades et ne contournent jamais les permissions métier.

---

## 4. Modèle économique

**Payant** sur trois segments :

- **B2C** : agriculteurs individuels — abonnement micro (à calibrer)
- **B2B coopératives** — licence groupée par nombre de membres
- **B2G / ONG** — licence institutionnelle, déploiement régional

**Implications architecturales** :
- **Multi-tenant** obligatoire (isolation par organisation)
- **Billing** intégré (plans, usage metering, facturation)
- **Authentification** par numéro de téléphone + SMS OTP (pas d'email en rural)
- **Row-level security** dans la base de données
- **Audit trail** des conversations (conformité + support)

---

## 5. Scope linguistique

### Horizon long terme

**50+ langues africaines**.

### Phasage de livraison (validé 2026-04-21)

Approche **graduelle avec budget croissant proportionnel aux utilisateurs payants** :

| Phase | Scope linguistique | Statut |
|---|---|---|
| P1 (actuelle) | Dioula Côte d'Ivoire (`dyu`) | En cours |
| P2 | +Baoulé, +Bété, +Agni (3 langues CI majeures) | Planifié |
| P3 | +Langues CI restantes + langues Mali (bambara `bam`) | Planifié |
| P4 | Extension Afrique de l'Ouest (wolof, peul, hausa, moore…) | Vision |
| P5+ | 50+ langues africaines | Vision long-terme |

**Règle** : on ne passe pas à la phase N+1 tant que la phase N n'est pas
production-ready (qualité non sacrifiée, métriques WER/BLEU validées).

### Implications architecturales

- Schéma DB **language-first** (chaque entrée corpus est tagguée `language`)
- Modèle d'embedding adapté à la diversité des langues africaines
  basse-ressource (ADR-0003 dédié à venir)
- Infrastructure ASR/TTS extensible (ajout d'un modèle par langue sans
  régression sur les existants)

---

## 6. Fonctionnalités

### Actuel (P1 MVP)

- ASR vocal dioula CI (NeMo Soloni)
- NLU → cascade IVR exact → IVR concept → DeepSeek+NLLB → fallback
- TTS dioula CI (MMS-tts-dyu)
- Météo temps réel (Open-Meteo)
- Corpus IVR agricole structuré (197 entrées bambara/dioula)

### Cible (P2-P3)

- **Free-form queries** : l'utilisateur doit pouvoir poser n'importe quelle
  question agricole, même hors catalogue d'intents. Exige semantic search
  robuste + RAG sur contenus externes.
- **Personnalisation utilisateur** :
  - Profil (zone géographique, cultures déclarées, taille d'exploitation)
  - Historique conversationnel
  - Parcours utilisateur suivi dans le temps
  - Conseil ciblé par zone + saison + culture
- **RAG sur documents longs** : intégration de sources expertes
  - ANADER (CI), CGIAR, ICRISAT, Africa Rice, IITA
  - Langues : FR principalement, EN secondaire
  - Chunking + embedding + recherche sémantique
- **Alertes push** (via IVR ou WhatsApp) : événements climatiques critiques

### Cible long terme (P4+)

- Connexion avec marketplaces agricoles locaux
- Intégration paiement mobile money
- Mode offline dégradé (reconnaissance vocale embarquée simplifiée)

---

## 7. Infrastructure & hosting

### Posture choisie (validée 2026-04-21)

- **Cloud VPS** au démarrage (calibration à faire selon usage réel mesuré,
  pas estimé)
- **Hébergement Europe ou Afrique** (pas US) pour éviter Cloud Act et rester
  alignés sur les exigences potentielles des bailleurs ONG
- Migration possible vers self-hosted Afrique si souveraineté devient un
  levier commercial

### Services cloud envisagés

- **Données métier** : Convex, sous réserve de validation de la résidence, de
  la rétention et de l'effacement avant toute donnée personnelle de production
- **Corpus IVR existant** : PostgreSQL + pgvector pendant la transition, avec
  une migration décidée et vérifiée séparément
- **Stockage fichiers** (audios, modèles) : S3-compatible (MinIO self-hosted,
  Cloudflare R2, Scaleway Object Storage Paris)
- **Compute** : VPS Hetzner (FSN/HEL), Scaleway (Paris), ou OVH (Gravelines)

### Scale prévu

- P1 : quelques centaines d'utilisateurs béta
- P2 : ~1000–5000 utilisateurs pilote
- P3 : 10k+ utilisateurs, premiers contrats coopératives / ONG
- P4+ : 100k+ utilisateurs, déploiement régional

### Équipe

- **Actuellement** : Ruben seul (dev + produit)
- **À moyen terme** : équipe à constituer → toute décision technique doit
  être **documentée, standard, onboardable** par des devs tiers. Pas de
  stack exotique, pas de patterns non-documentés.

---

## 8. Contraintes réglementaires

### Posture par défaut validée (2026-04-21)

- **Conformité GDPR-like** dès P1 (chiffrement at-rest, chiffrement en transit,
  consentement utilisateur, droit à l'effacement, anonymisation des données)
- **Hébergement EU ou Afrique** (jamais US pour données utilisateurs)
- **Localisation** des données (pas de réplication hors-EU sans contrôle)

### Raison

Les ONGs bailleurs (UE, Banque Mondiale, AFD, USAID) imposent souvent des
standards data protection alignés GDPR. Partir conformes = ne pas avoir à
re-architecturer le jour où on signe avec eux.

### Non-traité (à clarifier plus tard)

- Réglementation CI/Mali spécifique données agricoles (à vérifier avec un
  conseil juridique local quand on atteint la phase contrat)
- Éventuelle certification (ISO 27001, etc.) selon demande clients B2B

---

## 9. Non-négociables (rappel, source : constraints.md)

- **Qualité > tout** — jamais sacrifiée, même temporairement
- **Pas de hardcoding** — toute donnée métier externalisée
- **SOLID + tests** — chaque brique production-ready
- **ADR avant code** pour toute décision structurante
- **Pas d'invention linguistique** — validation multi-sources obligatoire

Ces règles **dominent** toute autre considération (vitesse, coût, simplicité).

---

## 10. Signaux de dérive

Cette vision est remise en cause si :

- Un utilisateur final (agriculteur) ne peut pas utiliser le produit dans sa
  langue naturelle → le produit n'a pas de sens
- La latence de bout-en-bout (voix → réponse voix) dépasse 10s → inutilisable
- Le WER ASR dioula dépasse 30% en conditions réelles → confiance cassée
- Un bailleur clé refuse pour non-conformité GDPR → stratégie commerciale
  compromise

Si un de ces signaux apparaît, ADR de révision stratégique obligatoire.

---

## Références

- [CLAUDE.md](../CLAUDE.md) — règles de travail détaillées
- [docs/constraints.md](constraints.md) — non-négociables détaillés
- [docs/adr/](adr/) — historique des décisions d'architecture
- [MEMORY.md](../../.claude/projects/c--Users-USER-PC-Documents-propre---moi-wourri/memory/MEMORY.md) — mémoire vivante projet
