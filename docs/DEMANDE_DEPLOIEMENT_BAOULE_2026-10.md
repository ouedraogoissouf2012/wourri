# Demande de déploiement — Baoulé (version démo terrain)

- **Date** : 2026-10-22
- **Demandeur** : Ouedraogo Issouf (chef de projet)
- **Échéance** : vendredi 2026-10-24 (présentation aux paysans)
- **Destinataire** : la fenêtre « déploiement » (machine qui a accès à la VM Scaleway et aux réglages GitHub)
- **Réf.** : ADR-0045, issue #475

## 1. Ce qu'on veut obtenir

Un paysan envoie un **message vocal en baoulé** sur WhatsApp. Il reçoit en retour **l'enregistrement
audio de la réponse** dicté par un locuteur natif, puis le texte.

Si la question n'est pas dans le corpus, il reçoit un message de repli honnête et la question
est remontée à l'équipe.

Tout est derrière un interrupteur **éteint par défaut** : `WOURI_BAOULE_SERVI=0`. Tant qu'il est
à 0, rien ne change pour les utilisateurs.

## 2. Ce qui est déjà fusionné (rien à coder)

| Brique | Où | État |
|---|---|---|
| API : NLU baoulé, réponses natives, repli | `APIPy`, PR #586 | fusionné |
| WhatsApp : vocal baoulé → serveur voix, réponse audio d'abord | `whatsappServeur`, PR #587 | fusionné |
| Atelier LQE : validations `mot_cle` / `paire_qr` | PR #584 et #585 | fusionnés |
| Serveur voix baoulé (notebook RunPod) | `finetune/colab/serveur_voix_baoule_runpod.ipynb` | fusionné |
| Dictionnaire démo + passage des variables dans le compose | PR #588 | **à fusionner** |

## 3. Ce qu'on demande, dans l'ordre

### Étape A — Vérifier les interrupteurs de déploiement (GitHub → Settings → Variables)

1. `DEPLOY_API_ENABLED` vaut-il `true` ? (workflow `deploy-api.yml`)
2. `DEPLOY_WA_ENABLED` vaut-il `true` ? (workflow `deploy-wa.yml`)
3. Le workflow `deploy-wa` lancé par la fusion de #587 (2026-10-22 13:18 UTC, commit `dcaeb96`)
   est-il vert ? L'image `wourri-whatsapp:latest` sur la VM est-elle bien celle-là ?

### Étape B — Après la fusion de la PR #588

La fusion déclenche `deploy-api.yml`, car elle touche `dictionnaires/**` et `docker-compose.prod.yml`.
Ce workflow copie le compose sur la VM (`/srv/wourri/`) et redéploie l'API.

4. Le workflow `deploy-api` est-il vert ?
5. Sur la VM, `docker-compose.prod.yml` contient-il bien :
   - `BCI_AUDIO_BASE_URL` pour `wouri-api` ;
   - les quatre `WOURI_BAOULE_*` pour `whatsapp-server` ?

> ⚠️ Ces variables doivent être listées dans le bloc `environment:` du compose. Sans cela, les
> écrire dans `.env.prod` n'a **aucun effet**. C'est ce que fait la PR #588.

### Étape C — Ajouter les réglages dans `/srv/wourri/.env.prod` (ne pas activer encore)

```bash
WOURI_BAOULE_SERVI=0
WOURI_BAOULE_ASR_URL=
WOURI_BAOULE_ASR_KEY=
WOURI_BAOULE_AUDIO_REPLI=
BCI_AUDIO_BASE_URL=
```

Les valeurs réelles (URL et clé) seront transmises par le chef de projet, **hors git**, au moment
où le serveur voix tournera sur RunPod. La clé ne doit jamais être commitée.

### Étape D — Le jour de la démo : activer

Le serveur voix tourne sur un GPU loué (RunPod). Son adresse a la forme
`https://<POD_ID>-8000.proxy.runpod.net` et **change à chaque nouveau pod**.

```bash
# dans /srv/wourri/.env.prod
WOURI_BAOULE_SERVI=1
WOURI_BAOULE_ASR_URL=https://<POD_ID>-8000.proxy.runpod.net
WOURI_BAOULE_ASR_KEY=<clé affichée par le notebook>
BCI_AUDIO_BASE_URL=https://<POD_ID>-8000.proxy.runpod.net/audio

cd /srv/wourri
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d wouri-api whatsapp-server
```

Il faut `up -d` (qui recrée les conteneurs) et non `restart` : `restart` ne relit pas `.env.prod`.

### Étape E — Vérifications

```bash
# depuis la VM : le serveur voix répond
curl -s https://<POD_ID>-8000.proxy.runpod.net/health

# les variables sont bien arrivées dans les conteneurs (n'affiche pas la clé)
docker compose -f docker-compose.prod.yml exec whatsapp-server printenv WOURI_BAOULE_SERVI WOURI_BAOULE_ASR_URL
docker compose -f docker-compose.prod.yml exec wouri-api printenv BCI_AUDIO_BASE_URL
```

Puis, sur WhatsApp :

1. choisir la langue baoulé ;
2. envoyer un vocal baoulé (par ex. une question sur la plantation du cacao) ;
3. on doit recevoir un audio puis un texte.

### Retour arrière (immédiat)

```bash
# dans /srv/wourri/.env.prod
WOURI_BAOULE_SERVI=0

docker compose --env-file .env.prod -f docker-compose.prod.yml up -d whatsapp-server
```

Le baoulé redevient « bientôt disponible ». Rien d'autre n'est touché.

## 4. Questions à la fenêtre déploiement

| # | Question | Réponse |
|---|---|---|
| Q1 | `DEPLOY_API_ENABLED` et `DEPLOY_WA_ENABLED` sont-ils à `true` ? | |
| Q2 | L'image WhatsApp en production contient-elle le commit `dcaeb96` (PR #587) ? | |
| Q3 | Le front de l'atelier LQE (PR #585 : ordre « plus récent en haut », affichage des types) est-il redéployé ? Sinon, comment le redéployer ? | |
| Q4 | La VM peut-elle joindre `*.proxy.runpod.net` en HTTPS (pas de pare-feu sortant) ? | |
| Q5 | Qui modifie `.env.prod` le jour J, et comment le chef de projet transmet-il la clé (canal hors git) ? | |
| Q6 | Y a-t-il un blocage à faire ces étapes avant vendredi 2026-10-24 ? | |

**Comment répondre** : remplir la colonne « Réponse » ci-dessus. Puis pousser sur la branche
`fix/475-baoule-dictionnaire-demo` (avant fusion), ou commenter la PR #588.
