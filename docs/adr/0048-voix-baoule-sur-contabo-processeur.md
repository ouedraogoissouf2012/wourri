# ADR-0048 — Voix baoulé hébergée sur le serveur Contabo, sans carte graphique

**Statut** : proposé
**Date** : 2026-10-27
**Auteur(s)** : Claude (assistant) sous direction de Ouedraogo Issouf
**Valideur** : Ouedraogo Issouf — chantier demandé le 2026-10-27 (« oui je suis d'accord » : seuil de 5 s pour un vocal de 10 s, baoulé allumé pour de bon après les corrections du locuteur)
**ADRs liés** : [ADR-0045](0045-nlu-baoule-methode-dioula-validation-atelier.md) (serveur voix baoulé), [ADR-0044](0044-procedure-finetune-asr-baoule.md) (modèle et modèle de langue)
**Issue** : #474

---

## Contexte

- Le serveur voix baoulé (`finetune/serveur_voix_bci.py`) transcrit les vocaux WhatsApp en baoulé et sert les réponses lues par le locuteur. Il ne tourne aujourd'hui que sur un GPU loué (RunPod), allumé à la main pour une démonstration.
- Un pod allumé en permanence coûterait environ 15 USD par jour (≈ 440 USD par mois), même sans aucun vocal. Le baoulé reste donc éteint (`WOURI_BAOULE_SERVI=0`) en dehors des démonstrations.
- Le dioula tourne déjà sur le serveur de production (VPS Contabo, Dokploy/Swarm, 8 vCPU, 23 Go) avec un modèle de même taille (MMS, ~1 milliard de paramètres), sans GPU. La différence n'est pas la taille, mais la pile logicielle : Omnilingual exige Python 3.12, PyTorch 2.8 et fairseq2 0.6, incompatibles avec l'image de l'API (Python 3.11).

## Questions posées avant la décision

1. La qualité est-elle la même sans GPU ?
2. La vitesse est-elle acceptable ? Seuil du valideur : moins de 5 s pour un vocal de 10 s.
3. Le service peut-il cohabiter avec l'API et le serveur WhatsApp sans les ralentir ?

Mesures faites le 2026-10-27 sur le poste du chef de projet (Intel i7-10750H, conteneur limité à 4 cœurs), dans l'image même du service (`finetune/voix/Dockerfile`), script `finetune/mesure_cpu_bci.py` :

| Configuration | CER (test, 623 clips) | Vocal de 5 s | **Vocal de 10 s** | Vocal de 30 s | Mémoire max |
|---|---|---|---|---|---|
| GPU, bfloat16 (fiche 0007) | 13,4 % | – | – | – | – |
| Processeur, bfloat16 (défaut du pipeline) | – | abandonné : plus de 26 min pour 20 clips, contre 6 min en float32 | | | |
| Processeur, float32 | **13,42 %** (WER 34,9 %) | 3,3 s | 6,6 s | 21,6 s | 6,6 Go |
| **Processeur, float32 + int8** | identique sur 120 clips (24,3 % contre 24,1 %) | **2,1 s** | **4,8 s** | 15,8 s | 6,7 Go |
| Processeur, float32 + int8, 2e passage (glouton) | – | 2,7 s | 5,6 s | 19,4 s | 6,4 Go |
| **Processeur, float32 + int8 + modèle de langue** (même passage) | test CER 11,8 % (voir ci-dessous) | 2,9 s | **5,5 s** | 21,1 s | 6,4 Go |

- Le 2e passage a été mesuré deux heures après le premier, juste après 1 h 30 de reconstruction du modèle de langue sur 6 cœurs : même configuration glouton, 4,8 s puis 5,6 s pour un vocal de 10 s. Sur un portable, la chaleur et la charge font varier la vitesse de ~15 % ; le seuil de 5 s est donc à la limite et seule la mesure sur le serveur tranche.
- Le modèle de langue n'ajoute presque rien sur un vocal court (5,5 s contre 5,6 s, dans le bruit de mesure) et ~1,6 s sur un vocal de 30 s.

- Les 12 transcriptions vides du test viennent toutes d'une même voix aux enregistrements quasi muets (déjà relevée en fiche 0007) ; elles sont vides sur GPU aussi.
- Les 120 premiers clips contiennent cette voix : leur CER est plus élevé que la moyenne. Seule compte la comparaison float32 / int8 sur les mêmes clips.
- Modèle de langue reconstruit sur le modèle int8 (`mesure_lm_bci.py --processeur`, même corpus et même protocole que la fiche 0007) : candidat « complet » retenu sur dev, α = 0,4, β = 1,0 ; dev CER 9,2 % → 8,0 % ; **test CER 13,5 % → 11,8 %, WER 34,9 % → 26,4 %** (GPU : 13,4 % → 11,6 %, 34,8 % → 25,3 %). Le modèle de langue du GPU n'est pas réutilisé : celui-ci est réglé sur les sorties du modèle int8.
- int8 : quantification dynamique des 290 couches linéaires (`serveur_voix_bci.vers_int8`). Les couches de fairseq2 ne sont pas des `torch.nn.Linear` : elles sont recopiées une à une avant quantification (une copie complète d'un coup dépassait 7,6 Go).

## Options étudiées

### Option A — Pod GPU loué allumé en permanence

- Avantages : déjà en place, latence la plus faible.
- Inconvénients : ≈ 440 USD par mois même sans trafic ; adresse publique du proxy RunPod.

### Option B — GPU « à la demande » (RunPod serverless)

- Avantages : on ne paie que les secondes de calcul.
- Inconvénients : démarrage à froid du modèle de 3,9 Go à chaque réveil (plusieurs dizaines de secondes), service externe de plus, données vocales hors du serveur.

### Option C — Service séparé sur le serveur Contabo, sans GPU (retenue)

- Avantages : 0 USD de plus ; qualité quasi identique (mesurée) ; vocal de 10 s en 4,8 à 5,6 s sur 4 cœurs d'un portable (mesuré) ; réseau interne seulement (le serveur WhatsApp télécharge lui-même l'audio des réponses, `lib/response_sender.js`) ; aucune donnée vocale ne quitte le serveur.
- Inconvénients : 4 cœurs et ~7 Go de mémoire pris sur le serveur partagé ; le processeur de Contabo n'est pas celui de la mesure (vérification finale sur place) ; `torch.ao.quantization` est annoncé retiré dans PyTorch 2.10 (version figée à 2.8 ici).

### Comparatif

| Critère | A | B | C |
|---|---|---|---|
| Coût mensuel | ≈ 440 USD | quelques USD | 0 USD |
| Vocal de 10 s | < 1 s | < 1 s + démarrage à froid | 4,8 à 5,6 s (mesuré, 4 cœurs, portable) |
| Qualité (CER test, avec modèle de langue) | 11,6 % | 11,6 % | 11,8 % |
| Données hors du serveur | oui | oui | non |
| Dette technique | faible | service externe | quantification à revoir avant PyTorch 2.10 |

## Décision

**Option C.** Image `finetune/voix/Dockerfile` (contexte `finetune/`), service Dokploy séparé de l'API.

1. **Calcul** : float32 puis int8 (`BCI_VOIX_PROCESSEUR=1`, défini dans l'image) ; 4 cœurs (`OMP_NUM_THREADS=4`, limite CPU du service à 4).
2. **Réseau** : interne uniquement. `WOURI_BAOULE_ASR_URL` et `BCI_AUDIO_BASE_URL` pointent vers le nom du service sur le réseau Dokploy ; aucun domaine public.
3. **Modèle et modèle de langue** : volume persistant `/modele` et `/donnees`, jamais dans l'image (dépôt Hugging Face privé ; le modèle de langue contient des textes de jw.org).
4. **Mise en service** : seulement après une mesure de vitesse sur le serveur lui-même, à une heure creuse, et le seuil de 5 s tenu (avec le modèle de langue). S'il ne l'est pas sur 4 cœurs, la mesure est refaite sur 5 cœurs avant toute autre décision ; le baoulé n'est allumé pour de bon (`WOURI_BAOULE_SERVI=1`) qu'après les corrections du locuteur.

## Conséquences

- **Positives** : baoulé disponible en permanence sans coût ; plus de RunPod pour les démonstrations.
- **Négatives assumées** : réponse plus lente que sur GPU (le serveur WhatsApp attend jusqu'à 180 s) ; 4 cœurs réservés sur un serveur partagé.
- **Retour arrière** : `WOURI_BAOULE_SERVI=0` dans le serveur WhatsApp (le baoulé repasse en « bientôt disponible »), puis arrêt du service.

## Historique

- 2026-10-27 — proposé, avec les mesures ci-dessus (modèle de langue int8 et 2e passage ajoutés le soir).
