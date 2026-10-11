# 05 — Feuille de route 12 semaines

**Période** : semaines S1 à S12 à compter du 2026-10-13 · **Ressource : 1 développeur**.

## 1. Hypothèse de capacité — à valider par le manager

| Poste | Jours / semaine |
|---|---|
| Chantiers de la feuille de route | **4,0** |
| Incidents, maintenance, support, documentation, revue | **1,0** |

**Capacité sur 12 semaines : 48 jours.** Je planifie **42 jours** de chantiers et laisse
**6 jours de marge explicite** (12,5 %). Cette marge n'est pas du confort : sur un projet en
production avec des agriculteurs réels, un incident arrive.

🔴 **Point d'honnêteté** : le backlog complet (43 issues + 17 chantiers identifiés) représente
nettement plus que 48 jours. **Ce plan fait des choix et en assume les reports** — notamment
le TTS baoulé (BAO-4), reporté au trimestre suivant. Prétendre tout tenir serait un mensonge
de planification.

## 2. Vue d'ensemble

| Semaine | Axe dominant | Chantiers |
|---|---|---|
| S1 | Risques bloquants | LIC-1, INF-2 |
| S2 | Mesure dioula | DIO-1 |
| S3 | Produit | FR-1, QUA-3 |
| S4 | Baoulé | BAO-1 |
| S5–S6 | Qualité / MLOps | QUA-1, INF-1 |
| S7–S8 | Baoulé | BAO-2 |
| S9 | Dioula / agriculteur | DIO-2, AGR-1 |
| S10 | Baoulé | BAO-3 |
| S11 | Qualité des données | QUA-2 |
| S12 | Consolidation | DOC-1, AGR-2, INF-3 |

---

## AXE 1 — Fiabilité et maintenance du dioula

### DIO-1 — Exécuter le benchmark ASR dioula

- **Problème** : la langue principale du produit n'a **aucune mesure de qualité**. Impossible
  de prouver une amélioration, de détecter une régression ou de justifier un changement de
  modèle.
- **État actuel (preuve)** : `docs/benchmarks/0001-asr-dioula-evaluation.md` — **« Statut :
  proposé, en attente de validation Ruben avant exécution »**. Aucun fichier de résultats.
- **Livrable** : `docs/benchmarks/0001-asr-dioula-evaluation-results.md` avec WER et CER par
  fournisseur (MMS-dyu, MMS générique, Omnilingual), sur au moins 20 audios, plus le delta
  8 kHz / 16 kHz.
- **Dépendances** : disponibilité de Ruben pour la validation du protocole et l'évaluation
  humaine ; jeu de test audio dioula constitué.
- **Priorité** : **P0** · **Charge : 4 j (incertitude moyenne** — dépend de la disponibilité
  d'un locuteur).
- **Critères d'acceptation** : (1) WER et CER publiés pour les 3 fournisseurs ; (2) protocole
  rejouable par une commande documentée ; (3) jeu de test versionné ou sa référence épinglée.
- **Risques** : indisponibilité de Ruben → **plan B** : publier les métriques automatiques
  seules, en marquant l'évaluation humaine « à venir », plutôt que de tout bloquer.
- **Ressource** : GPU ponctuel (inférence) — Colab ou budget GPU.
- **Semaine** : S2.

### FR-1 — Servir le corpus validé en mode français

- **Problème** : le mode français **ne consulte pas le corpus**. La connaissance validée par
  des locuteurs natifs n'atteint jamais ces utilisateurs, et la boucle de retour (ADR-0040) ne
  peut pas s'y refermer.
- **État actuel (preuve)** : `app/services/chat/handlers/french_handler.py` — aucune cascade
  IVR ; le LLM est le chemin par défaut.
- **Livrable** : le `FrenchHandler` consulte le corpus avant le LLM, dans le respect de
  l'architecture existante (ADR-0015, extension sans réécriture).
- **Dépendances** : aucune.
- **Priorité** : **P0** · **Charge : 3 j (incertitude faible)**.
- **Critères d'acceptation** : (1) une question couverte par le corpus reçoit la réponse
  validée en mode français ; (2) une question escaladée puis validée est **remise** à
  l'agriculteur en mode français ; (3) aucune régression sur les modes dioula et both,
  prouvée par la suite de tests.
- **Risques** : le corpus est majoritairement dioula ; vérifier que la réponse française
  existe pour chaque entrée, sinon prévoir un repli explicite.
- **Ressource** : aucune.
- **Semaine** : S3.

### DIO-2 — Automatiser l'import du corpus vers pgvector

- **Problème** : le peuplement pgvector est **manuel** après chaque modification du corpus
  JSON. Un oubli produit un écart silencieux entre ce qui est validé et ce qui est servi.
- **État actuel (preuve)** : `CLAUDE.md` — « peuplement **MANUEL** : `scripts/import_corpus_ivr.py`
  après toute modif du corpus JSON ».
- **Livrable** : import déclenché automatiquement (CI ou démarrage applicatif), avec
  vérification de cohérence entre le JSON et la base.
- **Dépendances** : aucune.
- **Priorité** : **P1** · **Charge : 2 j (incertitude faible)**.
- **Critères d'acceptation** : (1) une modification du corpus fusionnée se retrouve servie sans
  geste manuel ; (2) un écart JSON / base est **détecté et signalé**.
- **Risques** : import au démarrage = ralentissement ; préférer un déclenchement en CI.
- **Ressource** : aucune.
- **Semaine** : S9.

---

## AXE 2 — Corpus, entraînement et intégration du baoulé

### BAO-1 — Déclaration de langue baoulé

- **Problème** : aucun agriculteur ne peut se déclarer baoulophone. **Tant que ce point n'est
  pas levé, l'intégralité du travail baoulé reste inaccessible aux utilisateurs.**
- **État actuel (preuve)** : issue **#477** ouverte ; le moteur ne détecte pas la langue
  (constat tracé dans le chantier baoulé).
- **Livrable** : l'accueil WhatsApp propose le baoulé ; la préférence est persistée comme pour
  les autres langues.
- **Dépendances** : aucune. **C'est elle qui débloque BAO-2, BAO-3, BAO-4.**
- **Priorité** : **P0** · **Charge : 3 j (incertitude faible)**.
- **Critères d'acceptation** : (1) un utilisateur choisit le baoulé et la préférence survit au
  redémarrage ; (2) un repli explicite est servi tant que le contenu baoulé est absent —
  **jamais une réponse inventée**.
- **Risques** : promettre une langue sans contenu déçoit. **Mitigation** : message d'attente
  honnête (« le baoulé arrive, voici ce que je sais faire aujourd'hui »).
- **Ressource** : aucune.
- **Semaine** : S4.

### BAO-2 — Fine-tune ASR baoulé : run complet et mesure

- **Problème** : la base mesurée plafonne à **CER 22,1 %**. Le fine-tune est décidé mais seul
  un test mécanique a tourné.
- **État actuel (preuve)** : ADR-0036 **accepté** (1B retenu) ;
  `docs/benchmarks/0005-omnilingual-finetune-smoke-test.md` — test de 100 étapes qui
  **ne conclut pas** ; commit `c8975dd` (#474).
- **Livrable** : run complet, **CER post-fine-tune mesuré** sur le même jeu (n=290) et comparé
  à la base, publié en `docs/benchmarks/`.
- **Dépendances** : budget GPU ; révision de dataset épinglée (déjà en place).
- **Priorité** : **P1** · **Charge : 5 j (incertitude ÉLEVÉE** — un entraînement échoue
  souvent pour des raisons d'environnement, cf. l'historique Kaggle du projet).
- **Critères d'acceptation** : (1) CER mesuré sur **le même jeu de test** que le benchmark
  0003 ; (2) comparaison explicite avec 22,1 % ; (3) **si le CER ne s'améliore pas, le
  résultat est publié quand même** — un résultat négatif documenté a de la valeur ;
  (4) recette rejouable.
- **Risques** : surcoût GPU ; fuite train/test si le découpage n'est pas contrôlé →
  **QUA-2 doit idéalement précéder**, sinon vérifier manuellement la séparation avant le run.
- **Ressource** : **GPU requis** (T4 ou équivalent, plusieurs heures).
- **Semaine** : S7–S8.

### BAO-3 — NLU baoulé (texte vers concept)

- **Problème** : même transcrit, un message baoulé n'est pas compris par le moteur.
- **État actuel (preuve)** : issue **#475** ouverte ; `app/services/nlu/` ne couvre que le
  français et le dioula.
- **Livrable** : extraction de concepts baoulé branchée sur l'architecture NLU existante.
- **Dépendances** : **BAO-1** (sinon inutilisable) ; corpus baoulé validé.
- **Priorité** : **P1** · **Charge : 4 j (incertitude moyenne)**.
- **Critères d'acceptation** : (1) un jeu de phrases baoulé validées par un locuteur est
  classé correctement ; (2) **aucun contenu baoulé inventé** — règle ADR-0031 respectée.
- **Risques** : volume de données validées insuffisant. **Mitigation** : commencer par les
  intentions les plus fréquentes du dioula, pas par une couverture exhaustive.
- **Ressource** : temps de locuteur baoulé.
- **Semaine** : S10.

### BAO-4 — TTS baoulé — ⏸️ REPORTÉ hors des 12 semaines

- **Problème** : pas de voix baoulé.
- **État actuel** : issue **#476** ouverte.
- **Charge estimée** : 5 j · **incertitude élevée** (tons).
- **Justification du report** : sans BAO-1 et BAO-3, une voix ne sert à personne. La capacité
  disponible ne permet pas les quatre chantiers baoulé. **Report assumé au trimestre suivant.**

---

## AXE 3 — Qualité des données et de l'évaluation linguistique

### QUA-3 — Consentement des enregistrements vocaux

- **Problème** : des voix sont collectées sans document de consentement identifié. Risque
  **juridique** et éthique, sur des locuteurs réels.
- **État actuel (preuve)** : `docs/compliance/` ne contient qu'`artci-logs.md` (journaux).
  Aucun document de consentement trouvé. ADR-0035 (collecte par dictée) est **accepté** et
  organise la collecte, sans traiter les droits.
- **Livrable** : document de consentement (français + oral traduit), procédure de recueil,
  registre des consentements, conditions de réutilisation des corpus.
- **Dépendances** : arbitrage sur la réutilisation (interne seule ? publication ?).
- **Priorité** : **P0** · **Charge : 2 j (incertitude moyenne** — peut nécessiter un avis
  externe).
- **Critères d'acceptation** : (1) tout nouvel enregistrement est lié à un consentement
  traçable ; (2) les conditions de réutilisation sont écrites ; (3) un locuteur peut demander
  le retrait de ses enregistrements.
- **Risques** : les enregistrements **déjà collectés** peuvent être dépourvus de consentement
  → prévoir une régularisation, ne pas l'ignorer.
- **Ressource** : aucune technique.
- **Semaine** : S3.

### QUA-1 — Mesure de qualité linguistique automatisée

- **Problème** : aucune régression de qualité ASR ou TTS n'est détectable automatiquement.
- **État actuel (preuve)** : `app/services/asr_quality/` **ne contient aucune source** ; 0
  mention de couverture dans `ci-api.yml` ; les mesures vivent uniquement dans des notebooks.
- **Livrable** : tâche planifiée (hebdomadaire ou déclenchée manuellement, **pas à chaque
  PR** — trop lourde) qui calcule WER/CER sur un jeu figé et publie l'évolution.
- **Dépendances** : **DIO-1** (il faut une référence avant de surveiller une dérive).
- **Priorité** : **P1** · **Charge : 4 j (incertitude moyenne)**.
- **Critères d'acceptation** : (1) la mesure tourne sans intervention ; (2) une dégradation
  au-delà d'un seuil déclenche une alerte ; (3) l'historique des mesures est conservé.
- **Risques** : coût de calcul si branchée sur chaque PR → **imposer le mode planifié**.
- **Ressource** : GPU ponctuel ou CPU selon le modèle évalué.
- **Semaine** : S5–S6.

### QUA-2 — Séparation par locuteur et découpage versionné

- **Problème** : sans séparation stricte des locuteurs entre entraînement et évaluation, **les
  chiffres mesurés sont optimistes et trompeurs**.
- **État actuel (preuve)** : 🔍 aucun découpage versionné trouvé ; aucune graine aléatoire
  identifiée.
- **Livrable** : découpage train/validation/test versionné, **séparé par locuteur**, avec
  graine fixée et contrôle automatique d'absence de recouvrement.
- **Dépendances** : aucune. **Devrait idéalement précéder BAO-2.**
- **Priorité** : **P2** (P1 si BAO-2 est avancé) · **Charge : 3 j (incertitude moyenne)**.
- **Critères d'acceptation** : (1) un contrôle automatique échoue si un locuteur apparaît des
  deux côtés ; (2) le découpage est reproductible à l'identique.
- **Risques** : les métadonnées de locuteur peuvent être absentes de certains jeux → le
  documenter honnêtement plutôt que de supposer.
- **Ressource** : aucune.
- **Semaine** : S11.

---

## AXE 4 — Infrastructure, tests et MLOps

### LIC-1 — Trancher la licence des poids ML

- **Problème** : la voix dioula en production et la traduction reposent sur des poids que le
  projet lui-même qualifie de **non commerciaux**. Le sujet est ouvert depuis ADR-0002.
- **État actuel (preuve)** : ADR-0034:18 « poids **MMS = CC-BY-NC** (non commercial) » ;
  ADR-0034:74 « **dettes tracées** : (1) licence MMS non-commerciale » ; ADR-0002:126
  « question licence MMS-dyu **non tranchée** ».
- **Livrable** : un **ADR de décision** qui (a) établit les termes applicables à partir de
  sources à jour, (b) confronte au modèle économique visé, (c) choisit : rester non
  commercial, basculer vers des poids à licence permissive, ou obtenir une autorisation.
- **Dépendances** : **décision du manager** et, probablement, un avis juridique externe.
- **Priorité** : **P0** · **Charge : 2 j côté développeur** (instruction et rédaction ;
  l'arbitrage n'est pas technique).
- **Critères d'acceptation** : ADR **accepté**, avec une position écrite sur chaque poids
  servi en production.
- **Risques** : si la réponse impose un changement de modèle TTS, l'impact est **majeur** —
  d'où l'urgence de l'instruire **maintenant**, pas à la commercialisation.
- **Ressource** : avis juridique (coût inconnu, cf. [06](06-budget-ressources.md)).
- **Semaine** : S1.

### INF-2 — Sauvegarde automatisée et restauration testée

- **Problème** : **aucune sauvegarde automatisée**. Le corpus validé, la file d'amélioration et
  les préférences des agriculteurs sont exposés à une perte définitive.
- **État actuel (preuve)** : `pg_dump` n'apparaît que dans des **procédures écrites**
  (`docs/RUNBOOK_REDEPLOIEMENT_2026-08.md:55`, `docs/deployment.md:753,939`). Aucun script
  planifié dans `scripts/`. `docs/guide-projet-wourri.md:354` reconnaît l'absence d'équivalent
  backup/restore.
- **Livrable** : sauvegarde planifiée (base + volume de l'atelier), rétention définie, et
  **une restauration réellement testée**.
- **Dépendances** : accès au serveur.
- **Priorité** : **P0** · **Charge : 2 j (incertitude faible)**.
- **Critères d'acceptation** : (1) une sauvegarde se déclenche sans intervention ; (2) **une
  restauration est effectuée et vérifiée au moins une fois** — une sauvegarde jamais restaurée
  n'est pas une sauvegarde ; (3) la procédure est documentée.
- **Risques** : espace disque — le projet a déjà connu une saturation. Prévoir la rétention.
- **Ressource** : stockage (coût marginal).
- **Semaine** : S1.

### INF-1 — Couverture de tests mesurée

- **Problème** : 98 fichiers de test existent, mais on ignore **quelle part** des 16 821
  lignes est réellement exercée.
- **État actuel (preuve)** : `ci-api.yml` ne contient **aucune** mention de couverture.
- **Livrable** : mesure de couverture en CI, valeur publiée, seuil **non bloquant au départ**
  puis durci.
- **Dépendances** : aucune.
- **Priorité** : **P1** · **Charge : 2 j (incertitude faible)**.
- **Critères d'acceptation** : (1) la couverture est affichée à chaque exécution ; (2) les
  modules critiques (cascade, garde LLM, PII) sont identifiés et leur couverture connue.
- **Risques** : un seuil trop strict d'emblée bloquerait la livraison → **commencer en
  observation**.
- **Ressource** : aucune.
- **Semaine** : S5–S6.

### INF-3 — Nettoyage des artefacts hors dépôt

- **Problème** : une **copie obsolète** du pipeline ML (`finetune/` racine, mars 2026) peut
  être exécutée par erreur à la place de la version de référence.
- **État actuel (preuve)** : `finetune/` racine hors dépôt ; version de référence sous
  `finetune/colab/` sur `APIPy`.
- **Livrable** : archivage ou suppression des copies obsolètes, et une note indiquant où vit
  la version de référence.
- **Priorité** : **P2** · **Charge : 1 j (incertitude faible)**.
- **Critères d'acceptation** : un nouvel arrivant ne peut pas confondre les deux.
- **Risques** : supprimer un fichier non sauvegardé → **archiver avant de supprimer**.
- **Semaine** : S12.

---

## AXE 5 — Expérience agriculteur et intégrations agronomiques

### AGR-1 — Mesurer le délai de traitement de l'atelier

- **Problème** : le bot promet « reviens me voir, je te donnerai la réponse ». **La valeur de
  cette promesse dépend entièrement du délai de validation** — un mois, et la promesse est
  vide.
- **État actuel (preuve)** : ADR-0040 §Conséquences identifie ce délai comme « indicateur
  produit à suivre ». Aucune mesure en place.
- **Livrable** : indicateur du délai entre escalade et validation, et du **taux de questions
  effectivement remises**.
- **Dépendances** : **FR-1** (sinon la moitié des utilisateurs ne reçoivent jamais rien).
- **Priorité** : **P1** · **Charge : 2 j (incertitude faible)**.
- **Critères d'acceptation** : (1) délai médian connu ; (2) nombre de questions **en attente
  depuis plus de N jours** visible ; (3) aucune PII dans l'indicateur (ADR-0017).
- **Risques** : découvrir que le délai est très long. **Ce n'est pas un risque, c'est le but** —
  mieux vaut le savoir.
- **Semaine** : S9.

### AGR-2 — Formulation dioula de l'accusé et du rappel

- **Problème** : les messages d'escalade et de rappel sont **en français**, y compris pour les
  utilisateurs en mode dioula.
- **État actuel (preuve)** : `app/services/chat/llm_guard.py` — `ESCALATION_MESSAGE_FR` ;
  `pending_answers.py` — `PREFIXE_RAPPEL_FR`, avec la dette explicitement commentée.
- **Livrable** : formulations **validées par un locuteur natif**, intégrées via le circuit
  ADR-0031.
- **Dépendances** : disponibilité d'un locuteur. **Aucune invention linguistique.**
- **Priorité** : **P2** · **Charge : 2 j (incertitude moyenne** — dépend du locuteur).
- **Critères d'acceptation** : (1) formulations validées et datées ; (2) prononciation TTS
  vérifiée à l'écoute.
- **Risques** : sans locuteur, **ne pas livrer** plutôt qu'inventer.
- **Semaine** : S12.

### DOC-1 — Resynchroniser la documentation d'amorçage

- **Problème** : `CLAUDE.md` annonce 163 entrées et 54 concepts ; la réalité est **197** et
  **60**. La cascade y est décrite sans les répondeurs déterministes ni le garde LLM.
- **Livrable** : `CLAUDE.md` à jour ; note sur les numéros d'ADR manquants (0006, 0007, 0009).
- **Priorité** : **P2** · **Charge : 1 j (incertitude faible)**.
- **Critères d'acceptation** : les chiffres du document correspondent aux fichiers réels.
- **Semaine** : S12.

---

## 3. Charge totale planifiée

| Priorité | Jours |
|---|---|
| P0 (LIC-1, INF-2, DIO-1, FR-1, QUA-3, BAO-1) | **16** |
| P1 (QUA-1, BAO-2, INF-1, DIO-2, AGR-1, BAO-3) | **19** |
| P2 retenus (QUA-2, DOC-1, AGR-2, INF-3) | **7** |
| **Total planifié** | **42** |
| Capacité (12 × 4 j) | 48 |
| **Marge explicite** | **6 j (12,5 %)** |

**Reporté hors période** : BAO-4 (TTS baoulé, 5 j) et les 26 issues `audit` / `P3`.
