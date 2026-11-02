# Demande de déploiement — Voix baoulé sur le serveur Contabo, sans GPU

- **Date** : 2026-11-02 — **à faire aujourd'hui**
- **Demandeur** : Ouedraogo Issouf (chef de projet)
- **Destinataire** : la fenêtre « déploiement » (accès SSH au serveur). Elle reprend aussi la suite
  du chantier : le poste du chef de projet est en panne.
- **Réf.** : [ADR-0048](adr/0048-voix-baoule-sur-contabo-processeur.md) (décision et mesures),
  ADR-0045 (serveur voix), [DEMANDE_DEPLOIEMENT_BAOULE_2026-10.md](DEMANDE_DEPLOIEMENT_BAOULE_2026-10.md)
  (chaîne WhatsApp → voix, interrupteur), PR #608.
- **Règle** : rien n'est fait sur le serveur sans l'accord du chef de projet, étape par étape.
  Chaque étape se termine par sa vérification ; on ne passe à la suivante que si elle est verte.

## 1. But

Un paysan envoie un vocal en baoulé sur WhatsApp. Il reçoit la réponse **lue par le locuteur
natif (Esse)**, puis le texte. Jusqu'ici, la transcription tournait sur un GPU loué (RunPod),
allumé à la main pour la démonstration. Elle doit tourner **en permanence sur le serveur
Contabo, sans GPU**, comme service Dokploy séparé, sur le réseau interne seulement.

Seuil du chef de projet : **moins de 5 s de calcul pour un vocal de 10 s**.

## 2. Ce qui est prêt (branche `feat/voix-bci-processeur`, PR #608)

| Élément | Fichier |
|---|---|
| Image du service (Python 3.12, torch 2.8.0+cpu, fairseq2n 0.6+cpu, kenlm compilé à part) | `finetune/voix/Dockerfile`, `finetune/voix/requirements-voix-bci.txt`, `finetune/.dockerignore` |
| Démarrage : carte du modèle monté, uvicorn (1 worker) | `finetune/voix/demarrer.py` |
| Sans GPU : float32 puis int8 (`BCI_VOIX_PROCESSEUR=1`, dans l'image) | `finetune/serveur_voix_bci.py` |
| Modèle chargé **dès le démarrage** (`BCI_VOIX_PRECHARGER=1`, dans l'image) : ~3 min ; sinon le 1er vocal après chaque redémarrage dépasserait les 180 s du serveur WhatsApp | `finetune/serveur_voix_bci.py` |
| Mesure de vitesse sur le serveur sans Common Voice (`--audios`) | `finetune/mesure_cpu_bci.py` |
| Tests (65 dans `finetune/`) | `finetune/test_voix_cpu.py`, `finetune/test_serveur_voix_bci.py` |

Mesures sur le portable du chef de projet (4 cœurs) :

| | Vocal de 5 s | **Vocal de 10 s** | Vocal de 30 s | Mémoire |
|---|---|---|---|---|
| int8, 1er passage | 2,1 s | 4,8 s | 15,8 s | 6,7 Go |
| int8 + modèle de langue, 2e passage (portable chaud) | 2,9 s | 5,5 s | 21,1 s | 6,4 Go |

Qualité avec modèle de langue : CER test 11,8 % (11,6 % sur GPU). Le seuil est à la limite :
**la mesure sur le serveur (étape 4) tranche**.

## 3. Ce que le chef de projet apporte (jamais sur git, jamais dans l'image, jamais dans une conversation)

| Quoi | Taille | Où le trouver | Comment il arrive sur le serveur |
|---|---|---|---|
| **Jeton Hugging Face en lecture seule** | – | huggingface.co → Settings → Access Tokens | le chef de projet le **tape lui-même** dans la saisie masquée de l'étape 2, puis le révoque |
| **`dictee_bci_433.zip`** (réponses lues par Esse) | 76 Mo | clé USB, ou nouvel export de l'écran Dictée de l'atelier | copie par `scp` vers `/srv/voix-bci/donnees/` |
| **`lm_bci.pkl`** (modèle de langue int8 ; privé : textes de jw.org) | 23 Mo | clé USB (copié depuis `C:\Users\PC\.venvs\sources_bci\` du poste en panne) | copie par `scp` vers `/srv/voix-bci/donnees/` |

Le modèle (3,9 Go) est dans le dépôt Hugging Face **privé**
`seven990/omniasr-ctc-1b-bci-wourri-cv27` : il se télécharge directement sur le serveur.

Sans `lm_bci.pkl`, le service marche quand même en décodage glouton (CER test 13,5 % au lieu de
11,8 %). Le reconstruire demande 1 h 30 de calcul et Common Voice (annexe A) : **pas aujourd'hui
sur le serveur**.

## 4. Le plan d'aujourd'hui

### Étape 0 — État de départ (lecture seule)

```bash
docker service ls | grep -i -E 'whatsapp|api'
W=$(docker ps -q -f name=whatsappserver | head -1); A=$(docker ps -q -f name=wouriapi | head -1)
docker exec "$W" printenv WOURI_BAOULE_SERVI WOURI_BAOULE_ASR_URL   # attendu : 0 (ou vide), ancienne adresse RunPod
docker exec "$A" printenv BCI_AUDIO_BASE_URL
free -g; nproc; uptime                                              # mémoire libre ≥ 8 Go, charge
```

**Vérification** : `WOURI_BAOULE_SERVI` vaut 0 ou est absent. Mémoire libre ≥ 8 Go. Si ce n'est
pas le cas, on s'arrête et on en parle au chef de projet.

### Étape 1 — Construire l'image sur le serveur (~15 min, à une heure calme)

```bash
git fetch origin && git checkout feat/voix-bci-processeur      # dans un clone de travail, pas celui de Dokploy
docker build -f finetune/voix/Dockerfile -t wourri-voix-bci finetune
docker run --rm --entrypoint python wourri-voix-bci -c "import torch; print(torch.__version__)"
```

**Vérification** : affiche `2.8.0+cpu`. La construction se vérifie elle-même (import de torch,
fairseq2n, kenlm, omnilingual_asr, et pas de CUDA).

### Étape 2 — Dossiers, modèle, réponses d'Esse, modèle de langue

```bash
sudo mkdir -p /srv/voix-bci/modele /srv/voix-bci/donnees
sudo chown -R 1000:1000 /srv/voix-bci                           # le conteneur tourne en uid 1000
```

Modèle — **c'est le chef de projet qui tape le jeton** (saisie masquée, rien n'est affiché) :

```bash
docker run --rm -it -v /srv/voix-bci/modele:/modele --entrypoint python wourri-voix-bci -c \
 "import getpass; from huggingface_hub import snapshot_download; snapshot_download('seven990/omniasr-ctc-1b-bci-wourri-cv27', allow_patterns=['step_3000/*'], local_dir='/modele', token=getpass.getpass('Jeton HF : '))"
```

Réponses d'Esse et modèle de langue : copier `dictee_bci_433.zip` et `lm_bci.pkl` dans
`/srv/voix-bci/donnees/` (`scp`), puis :

```bash
sudo chown 1000:1000 /srv/voix-bci/donnees/*
docker run --rm -v /srv/voix-bci/donnees:/donnees --entrypoint python wourri-voix-bci -c \
 "import serveur_voix_bci as s; print(s.convertir_reponses('/donnees/dictee_bci_433.zip', '/donnees/reponses_ogg'), 'réponses')"
```

**Vérification** : `du -sh /srv/voix-bci/modele` ≈ 3,9 Go ; `ls /srv/voix-bci/donnees/reponses_ogg | wc -l`
≈ le nombre affiché ; `ls -l /srv/voix-bci/donnees/lm_bci.pkl` ≈ 23 Mo. Le chef de projet révoque
ensuite le jeton Hugging Face.

### Étape 3 — Essai du service hors Dokploy (conteneur jetable, réseau local seulement)

```bash
CLE=$(openssl rand -hex 24)        # la garder pour l'étape 5 ; ne pas l'afficher dans une conversation
docker run -d --name voix-essai --cpus 4 -e OMP_NUM_THREADS=4 -e BCI_VOIX_CLE="$CLE" \
  -e BCI_VOIX_LM=/donnees/lm_bci.pkl -p 127.0.0.1:8099:8000 \
  -v /srv/voix-bci/modele:/modele:ro -v /srv/voix-bci/donnees:/donnees wourri-voix-bci
curl -s 127.0.0.1:8099/health      # répéter : modele_charge passe à true en ~3 min
F=$(ls /srv/voix-bci/donnees/reponses_ogg | head -1)
curl -s -H "X-Api-Key: $CLE" -F "audio=@/srv/voix-bci/donnees/reponses_ogg/$F" 127.0.0.1:8099/transcribe
curl -s -o /dev/null -w '%{http_code}\n' "127.0.0.1:8099/audio/$F"
docker stats --no-stream voix-essai
```

**Vérification** : `/health` montre `modele_charge: true`, `modele_langue: true` et
`reponses_audio` > 0 ; `/transcribe` renvoie un texte en baoulé ; `/audio` renvoie 200 ;
mémoire < 8 Go.

### Étape 4 — Mesure de vitesse SUR le serveur (le conteneur d'essai est arrêté d'abord)

```bash
docker rm -f voix-essai
mkdir -p /tmp/mesure-voix && chmod 777 /tmp/mesure-voix
docker run --rm --cpus 4 -e OMP_NUM_THREADS=4 -v /srv/voix-bci/modele:/modele:ro \
  -v /srv/voix-bci/donnees:/donnees:ro -v /tmp/mesure-voix:/sortie --entrypoint python wourri-voix-bci \
  mesure_cpu_bci.py --audios /donnees/reponses_ogg --limit 20 --checkpoint-root /modele --threads 4 \
  --int8 --lm /donnees/lm_bci.pkl --out /sortie/mesure.json
```

**Vérification** : dans `latence_s_par_duree_de_vocal.modele_langue`, la valeur pour `"10"` est
**< 5 s**. Sinon, refaire avec `--cpus 5 -e OMP_NUM_THREADS=5 --threads 5`, puis **montrer les
chiffres au chef de projet avant toute décision** (ADR-0048, décision 4). Envoyer le JSON au
chef de projet pour l'ADR (il ne contient ni phrase ni voix).

### Étape 5 — Service Dokploy `voix-bci` (interrupteur toujours ÉTEINT)

- Source : ce dépôt, branche `feat/voix-bci-processeur` (puis `APIPy` après fusion de la PR #608),
  Dockerfile `finetune/voix/Dockerfile`, contexte `finetune/`.
- **Aucun domaine public**, réseau interne Dokploy (le même que l'API et le serveur WhatsApp).
- Limite CPU **4** (ou 5 si l'étape 4 l'a exigé), mémoire réservée ~8 Go.
- Volumes : `/srv/voix-bci/modele` → `/modele` (lecture seule), `/srv/voix-bci/donnees` → `/donnees`.
- Variables (onglet *Environment*) :

  ```
  BCI_VOIX_CLE=<la clé de l'étape 3>
  BCI_VOIX_LM=/donnees/lm_bci.pkl
  OMP_NUM_THREADS=4
  ```

**Vérification**, depuis le conteneur WhatsApp (même réseau) :

```bash
docker exec "$W" sh -c 'wget -qO- http://<nom-du-service-voix-bci>:8000/health'
```

→ `modele_charge: true` après ~3 min.

### Étape 6 — Brancher WhatsApp et l'API (interrupteur ÉTEINT)

- Service **whatsapp-server** : `WOURI_BAOULE_ASR_URL=http://<nom-du-service-voix-bci>:8000`,
  `WOURI_BAOULE_ASR_KEY=<la même clé>`, `WOURI_BAOULE_SERVI=0`. **Deploy**.
- Service **API** : `BCI_AUDIO_BASE_URL=http://<nom-du-service-voix-bci>:8000/audio`. **Deploy**.
  (Le serveur WhatsApp télécharge lui-même l'audio des réponses : une adresse interne suffit.)

**Vérification** : `printenv` des deux conteneurs ; la clé vérifiée par sa longueur seulement
(`printf %s "$WOURI_BAOULE_ASR_KEY" | wc -c`).

### Étape 7 — Allumage : décision du chef de projet

Règle posée le 2026-10-27 : le baoulé n'est allumé pour de bon qu'après les corrections d'Esse
dans l'atelier. Le chef de projet décide aujourd'hui s'il allume avec le contenu actuel
(dictionnaire de la démonstration) ou s'il attend. S'il allume :

1. whatsapp-server : `WOURI_BAOULE_SERVI=1`, **Deploy**.
2. Le chef de projet envoie un vocal baoulé depuis son téléphone.
3. **Vérification** : il reçoit l'audio d'Esse puis le texte ; journaux du service voix sans erreur
   (`docker service logs <service voix-bci> --since 10m`).

### Retour arrière (à tout moment)

`WOURI_BAOULE_SERVI=0` dans whatsapp-server, **Deploy** (le baoulé repasse en « bientôt
disponible »). Puis arrêt du service `voix-bci` si besoin. Rien d'autre à défaire : l'API et le
dioula ne dépendent pas de ce service.

## 5. Ce qui reste ensuite (hors déploiement)

- Fusionner PR #608 (ce chantier) et PR #601 (résumé de relecture des mots-clés).
- Compléter l'ADR-0048 avec la mesure de l'étape 4 et passer son statut à « accepté ».
- Esse : finir les ~85 éléments « À accepter », répondre aux 10 questions (sielɛ, afuɛ, juejue,
  gua, to, fien, nnolo, titi, haricot/niébé, « quel temps fera-t-il ? »), réaccepter les paires
  228 et 277, réenregistrer plus tard les 7 réponses corrigées (bci-q182 à q185, q187 à q189).
- Ensuite : mettre à jour `dictionnaires/relecture_mots_cles_bci.json`, reconstruire la NLU
  validée (`scripts/baoule_nlu_build.py`) depuis les nouveaux exports, proposer de remplacer le
  dictionnaire démo, refaire l'export Dictée et l'étape 2 (réponses) quand Esse aura réenregistré.

## Annexe A — Reconstruire `lm_bci.pkl` (seulement s'il est perdu)

Hors heures de trafic, ou sur une autre machine. Demande Common Voice 27 baoulé (ne pas
republier), l'archive Zenodo, la dictée et le modèle. Commande du 2026-10-27 (1 h 30 sur 6 cœurs) :

```bash
python mesure_lm_bci.py --cv27 /cv27 --dictee /dictee.zip --zenodo /sources/zenodo_bci.zip \
  --checkpoint-root /modele --step step_3000 --sources /sources --out /sortie --processus 5 --processeur
```

Résultat attendu : candidat « complet », α = 0,4, β = 1,0, CER test 13,5 % → 11,8 %.
