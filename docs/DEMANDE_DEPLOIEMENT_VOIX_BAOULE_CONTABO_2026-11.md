# Demande de déploiement — Voix baoulé sur le serveur Contabo, sans GPU

- **Date** : 2026-11-02
- **Demandeur** : Ouedraogo Issouf (chef de projet)
- **Destinataire** : la fenêtre « déploiement » (accès SSH au serveur), qui reprend aussi la suite du chantier : le poste du chef de projet est en panne
- **Réf.** : [ADR-0048](adr/0048-voix-baoule-sur-contabo-processeur.md) (décision et mesures), ADR-0045 (serveur voix), [DEMANDE_DEPLOIEMENT_BAOULE_2026-10.md](DEMANDE_DEPLOIEMENT_BAOULE_2026-10.md) (chaîne WhatsApp → voix, interrupteur)
- **Rien n'est fait sur le serveur sans l'accord du chef de projet**, étape par étape.

## 1. But

Le serveur voix baoulé (`finetune/serveur_voix_bci.py`) ne tournait que sur un GPU loué (RunPod),
allumé à la main pour la démonstration. Il doit tourner en permanence sur le serveur Contabo, sans
GPU, comme service Dokploy séparé, sur le réseau interne seulement.

Seuil du chef de projet : **moins de 5 s de calcul pour un vocal de 10 s**.
Le baoulé n'est allumé pour de bon (`WOURI_BAOULE_SERVI=1`) qu'**après les corrections du locuteur
(Esse)** dans l'atelier.

## 2. Ce qui est fait (branche `feat/voix-bci-processeur`)

| Élément | Fichier |
|---|---|
| Image du service (Python 3.12, torch 2.8.0+cpu, fairseq2n 0.6+cpu, kenlm compilé à part) | `finetune/voix/Dockerfile`, `finetune/voix/requirements-voix-bci.txt`, `finetune/.dockerignore` |
| Démarrage : écrit la carte du modèle monté, lance uvicorn (1 worker) | `finetune/voix/demarrer.py` |
| Mode sans GPU : float32 puis int8 (`BCI_VOIX_PROCESSEUR=1`, défini dans l'image) | `finetune/serveur_voix_bci.py` (`vers_int8`, `charger_pipeline`) |
| Mesure qualité / vitesse / mémoire | `finetune/mesure_cpu_bci.py` |
| Modèle de langue réglé sur le modèle int8 (`--processeur`) | `finetune/mesure_lm_bci.py` |
| Tests (63 au total dans `finetune/`) | `finetune/test_voix_cpu.py` |

Construction (contexte = dossier `finetune/`, ~15 min, image de 3,4 Go) :

```bash
docker build -f finetune/voix/Dockerfile -t wourri-voix-bci finetune
```

Mesures sur le portable du chef de projet (4 cœurs, détail dans l'ADR-0048) :

| | Vocal de 5 s | Vocal de 10 s | Vocal de 30 s | Mémoire |
|---|---|---|---|---|
| int8, 1er passage | 2,1 s | 4,8 s | 15,8 s | 6,7 Go |
| int8 + modèle de langue, 2e passage (portable chaud) | 2,9 s | 5,5 s | 21,1 s | 6,4 Go |

Qualité avec modèle de langue : CER test 11,8 % (11,6 % sur GPU). **Le seuil est à la limite :
seule la mesure sur le serveur tranche** (étape 3).

## 3. Les trois fichiers privés (jamais sur git, jamais dans l'image)

| Fichier | Taille | Où il est | Pourquoi privé |
|---|---|---|---|
| Modèle fine-tuné, dossier `step_3000/` | 3,9 Go | dépôt Hugging Face **privé** `seven990/omniasr-ctc-1b-bci-wourri-cv27` | modèle du projet |
| `lm_bci.pkl` (modèle de langue int8) | 23 Mo | **seulement sur le poste en panne** (dossier temporaire de la session, `mesure_cpu/lm/`) | contient des textes de jw.org |
| `dictee_bci_433.zip` (réponses lues par Esse) | – | téléchargements du chef de projet, ou nouvel export de l'écran Dictée de l'atelier | voix du locuteur |

Règles :
- Le **jeton Hugging Face** n'est jamais collé dans une conversation. Le chef de projet le saisit
  lui-même (saisie masquée), en **lecture seule**, puis le révoque après usage.
- Si `lm_bci.pkl` ne peut pas être récupéré du poste en panne, il se **reconstruit** (étape 3 bis) ;
  sans lui, le service marche quand même en décodage glouton (CER test 13,5 %).
- Common Voice : ne pas republier ses phrases ni ses fichiers de détail.

## 4. Étapes proposées (chacune avec l'accord du chef de projet)

### Étape 1 — Volumes sur le serveur

```
/srv/voix-bci/modele/step_3000/...     ← modèle (lecture seule pour le service)
/srv/voix-bci/donnees/reponses_ogg/    ← réponses d'Esse en ogg
/srv/voix-bci/donnees/lm_bci.pkl       ← modèle de langue (facultatif)
```

Le conteneur tourne sous l'utilisateur `voix` (uid 1000) : `chown -R 1000:1000 /srv/voix-bci`.

Téléchargement du modèle, jeton saisi par le chef de projet lui-même (`huggingface_hub` vient
avec `datasets` dans l'image) :

```bash
docker run --rm -it -v /srv/voix-bci/modele:/modele --entrypoint python wourri-voix-bci -c \
 "import getpass; from huggingface_hub import snapshot_download; snapshot_download('seven990/omniasr-ctc-1b-bci-wourri-cv27', allow_patterns=['step_3000/*'], local_dir='/modele', token=getpass.getpass('Jeton HF : '))"
```

Réponses d'Esse, à partir de l'export Dictée déposé dans `/srv/voix-bci/donnees/` :

```bash
docker run --rm -v /srv/voix-bci/donnees:/donnees --entrypoint python wourri-voix-bci -c \
 "import serveur_voix_bci as s; print(s.convertir_reponses('/donnees/dictee_bci_433.zip', '/donnees/reponses_ogg'), 'réponses')"
```

### Étape 2 — Service Dokploy `voix-bci`

- Image : `finetune/voix/Dockerfile`, contexte `finetune/`.
- **Aucun domaine public**, réseau interne Dokploy seulement.
- Limite CPU **4**, `OMP_NUM_THREADS=4`, mémoire réservée ~8 Go.
- Volumes : `/srv/voix-bci/modele:/modele:ro`, `/srv/voix-bci/donnees:/donnees`.
- Variables :

  ```
  BCI_VOIX_CLE=<nouvelle clé aléatoire, la même que WOURI_BAOULE_ASR_KEY côté WhatsApp>
  BCI_VOIX_LM=/donnees/lm_bci.pkl
  OMP_NUM_THREADS=4
  ```

- Vérification : `curl http://<service>:8000/health` → `modele_langue: true` si le fichier est là.
  Le premier vocal charge le modèle (~3 min) ; faire un vocal d'essai après chaque redémarrage.

### Étape 3 — Mesure de vitesse SUR le serveur, à une heure creuse

Avant tout branchement. Si le seuil de 5 s n'est pas tenu sur 4 cœurs, refaire la mesure sur
5 cœurs avant toute autre décision (ADR-0048, décision 4).

`mesure_cpu_bci.py` exige aujourd'hui le dossier Common Voice (`--cv27`). **À coder** : un mode
« vitesse seule » qui met bout à bout quelques réponses d'Esse (`/donnees/reponses_ogg`) en
vocaux de 5, 10 et 30 s (`vocaux_synthetiques` existe déjà), pour ne pas copier Common Voice sur
le serveur.

### Étape 3 bis — (seulement si `lm_bci.pkl` est perdu) le reconstruire

Commande utilisée le 2026-10-27 (1 h 30 sur 6 cœurs). Elle demande Common Voice 27 baoulé,
l'archive Zenodo, la dictée et le modèle. **Hors heures de trafic**, ou sur une autre machine :

```bash
python mesure_lm_bci.py --cv27 /cv27 --dictee /dictee.zip --zenodo /sources/zenodo_bci.zip \
  --checkpoint-root /modele --step step_3000 --sources /sources --out /sortie --processus 5 --processeur
```

Résultat attendu : candidat « complet », α = 0,4, β = 1,0, CER test 13,5 % → 11,8 %.

### Étape 4 — Branchement, interrupteur ÉTEINT

- Service **whatsapp-server** : `WOURI_BAOULE_ASR_URL=http://<service voix-bci>:8000`,
  `WOURI_BAOULE_ASR_KEY=<même clé>`, `WOURI_BAOULE_SERVI=0`.
- Service **API** : `BCI_AUDIO_BASE_URL=http://<service voix-bci>:8000/audio` (le serveur WhatsApp
  télécharge lui-même l'audio : une adresse interne suffit).

### Étape 5 — Allumage

Seulement après les corrections d'Esse et l'accord du chef de projet : `WOURI_BAOULE_SERVI=1`.

**Retour arrière** : `WOURI_BAOULE_SERVI=0` (le baoulé repasse en « bientôt disponible »), puis
arrêt du service.

## 5. Ce qui reste ailleurs (hors déploiement)

- PR #601 (résumé de relecture des mots-clés) à fusionner.
- Esse : finir les ~85 éléments « À accepter », répondre aux 10 questions (sielɛ, afuɛ, juejue,
  gua, to, fien, nnolo, titi, haricot/niébé, « quel temps fera-t-il ? »), réaccepter les paires
  228 et 277, réenregistrer plus tard les 7 réponses corrigées (bci-q182 à q185, q187 à q189).
- Ensuite : mettre à jour `dictionnaires/relecture_mots_cles_bci.json`, reconstruire la NLU
  validée (`scripts/baoule_nlu_build.py`) depuis les nouveaux exports, proposer de remplacer le
  dictionnaire démo.
