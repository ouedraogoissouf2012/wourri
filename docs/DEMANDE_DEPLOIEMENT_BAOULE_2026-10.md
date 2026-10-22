# Demande de déploiement — Baoulé (version démo terrain)

- **Date** : 2026-10-22 (révisé le même jour d'après les mesures de la fenêtre déploiement)
- **Demandeur** : Ouedraogo Issouf (chef de projet)
- **Échéance** : vendredi 2026-10-24 (présentation aux paysans)
- **Destinataire** : la fenêtre « déploiement » (accès au serveur et à Dokploy)
- **Réf.** : ADR-0045, issue #475, ADR-0026 (Dokploy)
- **Réponses Q1–Q6** : https://github.com/ouedraogoissouf2012/wourri/pull/588#issuecomment-6344084737

## 1. Ce qu'on veut obtenir

Un paysan envoie un **message vocal en baoulé** sur WhatsApp. Il reçoit en retour **l'enregistrement
audio de la réponse** dicté par un locuteur natif, puis le texte.

Si la question n'est pas dans le corpus, il reçoit un message de repli honnête et la question
est remontée à l'équipe.

Tout est derrière un interrupteur **éteint par défaut** : `WOURI_BAOULE_SERVI=0`. Tant qu'il est
à 0, rien ne change pour les utilisateurs.

## 2. Comment la production est déployée (mesuré le 2026-10-22)

| Élément | Réalité |
|---|---|
| Serveur | VPS Contabo piloté par **Dokploy**, services **Docker Swarm** |
| Service API | `wourri-wouriapi-4phcqw` |
| Service WhatsApp | `wourri-whatsappserver-wtpodc` |
| Construction des images | Dokploy surveille les branches et reconstruit à chaque fusion |
| Variables d'environnement | saisies **dans Dokploy, par service** (onglet *Environment*) |

Ce qui n'existe pas et ne doit pas être utilisé : `/srv/wourri`, `.env.prod`, `docker compose up -d`,
les workflows GitHub `deploy-api` / `deploy-wa`.

Les workflows `deploy-api` / `deploy-wa` visent l'ancien hôte Scaleway. Leur job *deploy* est
sauté, car `DEPLOY_*_ENABLED` n'est pas défini. **Ne pas activer ces variables.**

> Le bloc `environment:` de `docker-compose.prod.yml` liste aussi ces variables (PR #588). C'est
> pour la cohérence du dépôt et le contrôle CI `check_env_consistency` : en production, c'est
> Dokploy qui fait foi.

## 3. Ce qui est déjà en place

| Brique | État mesuré |
|---|---|
| WhatsApp : vocal baoulé → serveur voix, réponse audio d'abord (PR #587, `dcaeb96`) | ✅ dans l'image du 2026-10-22 13:28 |
| API : NLU baoulé, réponses natives, repli (PR #586) | ✅ image du 2026-10-22 13:27 |
| Front de l'atelier LQE (PR #585) | ✅ image du 2026-10-22 13:18 |
| Sortie HTTPS du serveur vers `*.proxy.runpod.net` | ✅ ouverte |
| Dictionnaire démo (PR #588) | **à fusionner**. Dokploy reconstruit alors l'API, qui embarque `dictionnaires/` |
| Variables baoulé dans les conteneurs | ❌ aucune pour l'instant (`printenv` vide) — normal |

## 4. Mise en service

### Étape C — Répétition, AVANT jeudi, interrupteur ÉTEINT

But : vérifier la chaîne Dokploy → conteneur sans rien changer pour les utilisateurs.

1. Dans Dokploy, service **whatsapp-server**, onglet *Environment*, ajouter :

   ```
   WOURI_BAOULE_SERVI=0
   ```

2. Cliquer **Deploy**.
3. Vérifier **dans le conteneur**, sans se fier à l'interface seule :

   ```bash
   C=$(docker ps -q -f name=wourri-whatsappserver-wtpodc | head -1)
   docker exec "$C" printenv WOURI_BAOULE_SERVI          # attendu : 0
   ```

4. Si rien ne s'affiche, regarder si la variable est dans la définition du service.
   La commande n'affiche que les **noms** des variables, jamais les valeurs :

   ```bash
   docker service inspect wourri-whatsappserver-wtpodc \
     --format '{{range .Spec.TaskTemplate.ContainerSpec.Env}}{{println .}}{{end}}' | cut -d= -f1
   ```

   - **Le nom est présent** mais `printenv` reste vide : `docker service update --force wourri-whatsappserver-wtpodc`.
   - **Le nom est absent** : Dokploy n'a pas appliqué le changement. Refaire *Deploy* dans Dokploy, puis revérifier.

5. Noter ici ce qui a marché (Deploy seul, ou Deploy + `--force`). C'est ce qu'on refera jeudi.

### Étape D — Le jour de la démo : allumer

Le serveur voix tourne sur un GPU loué (RunPod). Son adresse a la forme
`https://<POD_ID>-8000.proxy.runpod.net` et **change à chaque nouveau pod**.

Le chef de projet transmet l'adresse et la clé **par message privé, jamais sur git**. Il n'y a
pas de clé pour `BCI_AUDIO_BASE_URL`, qui n'est qu'une adresse.

1. Dokploy, service **API** (`wouri-api`), onglet *Environment* :

   ```
   BCI_AUDIO_BASE_URL=https://<POD_ID>-8000.proxy.runpod.net/audio
   ```

   Puis **Deploy**.

2. Dokploy, service **whatsapp-server**, onglet *Environment* :

   ```
   WOURI_BAOULE_SERVI=1
   WOURI_BAOULE_ASR_URL=https://<POD_ID>-8000.proxy.runpod.net
   WOURI_BAOULE_ASR_KEY=<clé affichée par le notebook>
   ```

   Puis **Deploy**. `WOURI_BAOULE_AUDIO_REPLI` (vocal de repli) est facultatif : le laisser absent.

### Étape E — Vérifications

```bash
# 1. le serveur voix répond (depuis le serveur)
curl -s https://<POD_ID>-8000.proxy.runpod.net/health

# 2. les variables sont dans les conteneurs (la clé : on vérifie sa longueur, pas sa valeur)
W=$(docker ps -q -f name=wourri-whatsappserver-wtpodc | head -1)
docker exec "$W" printenv WOURI_BAOULE_SERVI WOURI_BAOULE_ASR_URL
docker exec "$W" sh -c 'printf %s "$WOURI_BAOULE_ASR_KEY" | wc -c'      # attendu : > 0
A=$(docker ps -q -f name=wourri-wouriapi-4phcqw | head -1)
docker exec "$A" printenv BCI_AUDIO_BASE_URL

# 3. un enregistrement de réponse est servi (nom pris dans dictionnaires/corpus_ivr_bci.json, en .ogg)
curl -s -o /dev/null -w '%{http_code}\n' "https://<POD_ID>-8000.proxy.runpod.net/audio/<nom>.ogg"   # attendu : 200
```

Puis, sur WhatsApp :

1. choisir la langue baoulé ;
2. envoyer un vocal baoulé (par ex. une question sur la plantation du cacao) ;
3. on doit recevoir un audio puis un texte.

### Retour arrière (immédiat)

1. Dans Dokploy, service **whatsapp-server** : `WOURI_BAOULE_SERVI=0`, puis **Deploy**.
2. Vérifier avec `printenv`, comme à l'étape C.

Le baoulé redevient « bientôt disponible ». Rien d'autre n'est touché.

### Après la démo

- Le pod RunPod est arrêté (*Terminate*) par le chef de projet.
- Remettre `WOURI_BAOULE_SERVI=0`. Sinon les vocaux baoulé partent vers une adresse morte, et le paysan reçoit le message d'erreur de transcription.

## 5. Questions restantes

| # | Question | Réponse |
|---|---|---|
| Q5 | Qui saisit les variables dans Dokploy le jour J ? | à fixer par le chef de projet |
| Q7 | Résultat de la répétition (étape C) : Deploy seul suffit-il, ou faut-il `--force` ? | |

**Comment répondre** : en commentaire sur la PR #588 (le fichier reste lisible après fusion,
dans `docs/` sur `APIPy`).
