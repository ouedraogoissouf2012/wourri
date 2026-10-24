# Registre des sources baoulé (bci)

**Ce que contient ce registre** : chaque source de données baoulé examinée par le projet, avec ce qu'elle contient réellement (mesuré, pas déduit de son nom), sa licence et l'usage qu'on en fait.
**Mis à jour** : 2026-10-24.
**Liens** : [ADR-0046](adr/0046-validation-multisources-mots-baoule.md) (validation des mots), [ADR-0044](adr/0044-procedure-finetune-asr-baoule.md) (entraînement voix), [ADR-0045](adr/0045-nlu-baoule-methode-dioula-validation-atelier.md) (NLU).

Aucun texte ni audio de ces sources n'est versionné. Tout est téléchargé dans un dossier local par `python scripts/baoule_validation_mots.py --telecharger <dossier>`. Common Voice et les exports de l'atelier se déposent à la main.

## 1. Audio avec transcription (entraînement de la reconnaissance vocale)

| Source | Mesuré | Licence | Décision |
|---|---|---|---|
| **Common Voice 27.0** (Mozilla Data Collective) | 5 623 clips validés, 11,1 h, 16 voix, 876 phrases. Les splits officiels (319 / 267 / 290) sont **identiques** au miroir Klayt. | CC0. **Re-hébergement interdit**, compte Mozilla requis | ✅ 2e fine-tune : train 5,93 h (9 voix), dev 738 clips (2 voix), test 623 clips (7 voix) ; aucune voix ni phrase du test à l'entraînement (`finetune/cv27_split.py`, ADR-0044 révision 2026-10-24) |
| **Klayt/baoule-common-voice** (HF) | Les mêmes 876 clips que les splits Common Voice (vérifié chemin par chemin) | CC0 | Doublon de Common Voice : sert de référence au test 0003 |
| **Zenodo 6705861** (data354, 2022) | 565 clips, 4 voix, versets bibliques, 0 phrase commune avec le test. 223 commencent par un numéro de verset. | CC BY 4.0 | ✅ Entraînement, les 565 clips. Numéros de verset **non prononcés** (mesuré : +0,02 s ± 0,29 s à longueur égale), retirés de la transcription |
| Dictée d'esse (atelier) | 433 phrases, 1,3 h, locuteur natif | Projet (consentement QUA-3) | ✅ Entraînement + validation des mots |
| `abdouaziiz/bci-bible` (HF) | 1 709 clips, 3,9 h. **C'est du bambara**, pas du baoulé (« Filisiw ye kɛlɛ kɛ… ») | non précisée | ❌ Mauvaise langue |
| `abdouaziz/baoule2` (HF) | 8 144 clips, 18,7 h = Common Voice (**test compris**) + la Bible bambara ci-dessus | non précisée | ❌ Contaminerait le test et mélangerait les langues |
| `abdouaziz/baoule_waxal_concat` (HF) | 12 197 clips. WAXAL (Google) ne couvre officiellement pas le baoulé | accès restreint | 🔍 Accès demandé le 2026-10-24, à ouvrir pour vérifier |
| `African-Languages-Lab/baoule-asr` (HF) | 5 fichiers, publié le 2026-10-17 | CC BY 4.0, accès restreint | 🔍 Accès demandé le 2026-10-24 |
| `Tree-AI-lab/baoule-asr-dataset-mixture` (HF) | ~1 220 clips | accès restreint | 🔍 Accès demandé le 2026-10-24 |
| Nouveau Testament baoulé lu (YouVersion BLNT74, Words of Life) | Probablement 15 à 20 h | © Société biblique / PRM | ❌ Décision du valideur : la Bible ne sert que mot à mot (texte), pas en audio |
| Global Recordings Network | Récits bibliques, audio sans texte | usage d'évangélisation | ❌ Sans transcription, inutilisable pour apprendre |

## 2. Lexiques (sens des mots)

| Source | Mesuré | Licence | Décision (poids ADR-0046) |
|---|---|---|---|
| **Wiktionnaire français** (kaikki.org) | 826 entrées baoulé, gloses françaises, exemples | CC BY-SA 4.0 | ✅ Source forte, ×3 |
| **GATITOS** (Google SMOL) | 3 998 entrées ; la même entrée anglaise traduite en français **et** en baoulé → 3 996 paires français ↔ baoulé. Pivot parfois ambigu (« plant » → « usine ») | CC BY 4.0 | ✅ ×2 |
| **PanLex** (via ChiKhaPo, `ec5ug/chikhapo`) | 3 564 mots baoulé → anglais. **ChiKhaPo est un extrait de PanLex** : une seule source | CC0 / MIT | ✅ ×2 (ramené au français par GATITOS) |
| Wiktionary anglais | 25 entrées | CC BY-SA | Trop peu |
| baoule.ci | Dictionnaire sérieux | « Tous droits réservés » | ⚠️ Référence pour esse seulement ; demande d'autorisation possible |
| Dictionnaire baoulé-français (Timyan, Kouadio, Loukou, NEI 2003, 610 p.) | Ouvrage de référence, papier | © éditeur | ⚠️ Référence ; pas de version numérique libre |
| Glosbe | Traductions communautaires, surtout textes religieux | conditions interdisant l'extraction | ❌ |
| kasahorow | Aucun contenu baoulé visible | « All rights reserved » | ❌ |
| `Adjoumani/translations_french_baoule_V1` | 1 500 paires extraites de Glosbe (articles jw.org) | « MIT » apposé sur un contenu protégé | ❌ |
| `Tree-AI-lab/fr_bci_4d_instruct`, tokenizer Adjoumani | Texte produit par machine / Bible + Google Traduction | — | ❌ Apprendrait des erreurs |

## 3. Textes baoulé (graphies, mots-outils, futur modèle de langue)

| Source | Mesuré | Licence | Décision |
|---|---|---|---|
| **MADLAD** (`AfriSpeech/madlad-91-african`) | 7 392 documents, ~5 millions de mots (surtout jw.org) | ODC-BY (compilation) | ✅ Attestation « web » |
| **FineWeb-2** (`bci_Latn`) | 1 503 documents, 1,37 million de mots (97 % jw.org) | ODC-BY (compilation) | ✅ Attestation « web » |
| **FinePDFs** (`bci_Latn`) | 14 documents PDF, 37 000 mots | ODC-BY | ✅ Attestation « web » |
| **GlotCC** (`bci-Latn`) | 18 documents, 41 000 mots | CC0 | ✅ Attestation « web » |
| **SMOL** SmolSent + SmolDoc | 863 phrases + 130 documents traduits par des professionnels | CC BY 4.0 | ✅ Attestation (×1) |
| Bible baoulé 1998 (Beblia) + Louis Segond 1910 | 30 806 versets alignés par référence | baoulé © Alliance Biblique CI ; LSG domaine public | ✅ **Mot à mot uniquement** (×1), texte jamais versionné |
| Bible baoulé 1974 | Ancienne orthographe (ô, é) | © ABU 1974 | ❌ Graphies incompatibles |
| Lingua Libre | 94 mots enregistrés | CC BY-SA | Petit ; à reprendre pour la prononciation |
| Incubateur Wikipédia baoulé | Wiki de test peu actif | CC BY-SA | Négligeable |
| LGIDF (CNRS) | Site injoignable ; grammaires, pas de baoulé dans son miroir public | — | Rien à en tirer |

**Réserve sur les collections web** : la compilation est sous licence ouverte, mais le contenu vient surtout de jw.org. Il est utilisé en interne pour l'attestation et les statistiques, sans republication. C'est la pratique courante des modèles de langue ; le valideur en est informé.
