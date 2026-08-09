# ADR-0022 — Composition de la chaîne ASR dioula (ordre des providers, NeMo, critère de bascule)

**Statut** : proposé
**Date** : 2026-08-09
**Auteur(s)** : Claude (assistant) sous direction de Ouedraogo Issouf
**Valideur** : Ouedraogo Issouf
**Lié à** : issue #358, PR #365, docs/AUDIT_DIOULA_2026-08.md §7.1

---

## Contexte

La réparation #358 (PR #365) a ressuscité l'adapter MMS-dyu fine-tuné dioula CI,
mort depuis avril (bug de chemin). Conséquence : **le transcripteur effectif de
l'audio dioula a changé** — avant : MMS-generic (adapter `bam` Meta) ; après :
MMS-dyu (fine-tuné 295 clips Common Voice dyu), le générique restant en fallback.

La revue post-merge a produit un **test A/B sur 1 échantillon** (wav du corpus,
texte source connu) : le générique a fait *mieux* (~30 % vs ~45 % WER). Mais cet
échantillon est **structurellement biaisé** : c'est un audio *synthétique* généré
par la voix TTS de la famille `bam` — il favorise mécaniquement le modèle `bam`.
Aucune évaluation sur de **vraies voix dioula** n'est possible aujourd'hui : le
split test du dataset AXE-4 est texte seul (`audio_path: null` sur 7 992 entrées),
et aucun vocal réel avec transcription de référence n'existe dans le repo.

Par ailleurs, **NeMo Soloni** (1er provider déclaré) est indisponible partout :
le package `nemo` n'a jamais été dans `requirements.txt` ni dans l'image Docker.
Il a tourné en avril (les corrections `cultures_nemo_errors` en témoignent) puis
la réinstallation Python de juillet (#313) l'a perdu. Le modèle `.nemo` (459 Mo)
est orphelin sur disque.

**Décision à prendre** : quel ordre de providers, que faire de NeMo, et sur quel
critère toute modification future de la chaîne devra s'appuyer.

## Questions posées avant la décision

1. Faut-il rétrograder MMS-dyu derrière le générique suite au test A/B ?
2. Faut-il réinstaller `nemo-toolkit` ou retirer le provider NeMo ?

Réponse obtenue (Ruben, 2026-08-09) : « choisis la meilleure option durable » —
décision déléguée, actée ici, soumise à validation.

## Options étudiées

### A — Statu quo instrumenté *(retenue — recommandation)*
- **Ordre** : `[NeMo (skip), MMS-dyu, MMS-generic]`, agri_fallback = MMS-dyu — inchangé.
- **NeMo** : le code du provider **reste** (coût runtime nul : skip silencieux,
  réversibilité maximale), mais on **ne réinstalle pas** `nemo-toolkit`
  (dépendance très lourde) sans mesure qui le justifie.
- **Critère de bascule** (verrou de cet ADR) : *toute* modification de l'ordre
  de la chaîne exige une évaluation WER comparative sur **≥ 30 vocaux réels en
  dioula avec transcriptions de référence** (harnais `finetune/evaluate_wer.py`),
  collectés lors des tests terrain/WhatsApp. Pas de re-hiérarchisation sur des
  échantillons synthétiques ou uniques.
- **Pourquoi** : l'unique donnée contraire est biaisée (audio synthétique `bam`) ;
  l'adapter est le seul modèle entraîné sur de vraies voix dioula ; l'aval
  (normalizer 4 étapes) corrige les deux ; la position est réversible en 1 ligne.

### B — Rétrograder MMS-dyu derrière le générique
- Suit le seul point de données disponible. Mais ce point est biaisé, et cela
  revient à désactiver de facto le seul modèle dioula sur une mesure invalide.
  Rejetée : précipitation, pas rigueur.

### C — Réinstaller nemo-toolkit et restaurer l'ordre d'avril
- Restaure « la meilleure qualité » alléguée par les docstrings — jamais mesurée
  comparativement. Coût : dépendances lourdes (lightning, hydra…), image Docker
  gonflée, pour un bénéfice non démontré. Rejetée en l'absence de mesure.

## Décision

**Option A.** L'ordre actuel est maintenu ; NeMo reste en code mais non installé ;
**aucune modification future de la chaîne sans éval WER ≥ 30 vraies voix dioula**.

Travail induit (fait dans la PR liée) :
1. Normalisation du résultat du second passage agricole (revue F1).
2. `MMS_DYU_ADAPTER_PATH` surchargeable par env var, aligné sur `NEMO_MODEL_PATH`
   (revue F2 — nécessaire en Docker : l'adapter est monté en volume).

Travail futur (conditions de réévaluation) :
- Dès que ≥ 30 vocaux réels annotés existent (tests terrain), lancer
  `evaluate_wer.py` sur MMS-dyu vs MMS-generic (et NeMo si réinstallé sur une
  machine de bench) → l'ordre suit le résultat, tracé en historique ici.
- La collecte des vocaux réels relève du déploiement/test terrain (Ruben +
  locuteur natif pour les références).

## Conséquences

- **Positives** : décision réversible (1 ligne), critère objectif verrouillé,
  pas de dépendance lourde ajoutée sans preuve, le seul modèle dioula reste actif.
- **Négatives assumées** : si l'adapter s'avère réellement moins bon sur vraies
  voix, la période d'attente aura servi un modèle sous-optimal — atténué par le
  post-traitement (normalizer) et détectable dès la première éval terrain.
- **Rollback** : inverser `providers=[...]` dans `asr/__init__.py:37-40`.

## Références

- PR #365 (réparation adapter), revue post-merge (A/B 1 échantillon, biais documenté)
- `finetune/evaluate_wer.py` (harnais WER — chemins in-repo à corriger, cf. audit C11)
- docs/AUDIT_DIOULA_2026-08.md §3 C1-C3, §7.1

## Historique

- 2026-08-09 — rédaction (statut proposé). Option A recommandée, en attente de
  validation Ruben.
