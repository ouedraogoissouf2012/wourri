# Environnements Dokploy : staging et production (INF-06)

Spécification à appliquer dans l'interface Dokploy du serveur applicatif
(`https://dokploy.africandigitconsulting.com`). Objectif de la tâche INF-06 :
deux projets distincts, avec des secrets distincts, sans qu'aucun secret ni
aucune base de production ne soit partagé avec le staging.

Aucune valeur de secret ne figure dans ce document : uniquement des NOMS de
variables et la procédure. Les valeurs se saisissent dans Dokploy, jamais dans
Git.

## 1. Point de départ : l'isolation est déjà écrite dans le code

Les fichiers `docker-compose.staging.yml` et `docker-compose.prod.yml` séparent
déjà tout ce qui doit l'être. Il n'y a donc rien à modifier dans le code : INF-06
consiste à créer les deux projets Dokploy et à leur donner des valeurs
distinctes.

| Élément | Staging | Production |
| --- | --- | --- |
| Réseau Docker | `wourri_staging_net` | `wourri_net` |
| Base PostgreSQL | `wourri_staging` | `wourri_prod` |
| Conteneur API | `wourri_api_staging` | `wourri_api_prod` |
| Conteneur WhatsApp | `wourri_whatsapp_staging` | `wourri_whatsapp_prod` |
| Conteneur PostgreSQL | `wourri_postgres_staging` | `wourri_postgres_prod` |
| Volumes | préfixe `wourri_staging_*` | préfixe `wourri_*` |
| Port API (loopback) | `127.0.0.1:8001` | `127.0.0.1:8000` |
| Port WhatsApp (loopback) | `127.0.0.1:3002` | `127.0.0.1:3001` |
| Observabilité | Loki `127.0.0.1:3100` + Alloy | non déployée |

Les ports ne sont publiés que sur la boucle locale : l'exposition publique passe
par Traefik en HTTPS, jamais par un port ouvert.

## 2. Projets à créer dans Dokploy

Créer deux projets **séparés** (et non deux services d'un même projet), pour que
les variables et secrets ne puissent pas être partagés par erreur.

| Projet Dokploy | Fichier compose | Branche déployée |
| --- | --- | --- |
| `wouri-staging` | `docker-compose.staging.yml` | branche d'intégration |
| `wouri-production` | `docker-compose.prod.yml` | branche de production |

## 3. Variables d'environnement, par projet

Mêmes NOMS dans les deux projets, **valeurs obligatoirement différentes** pour
tout ce qui est secret ou identifiant de base.

| Variable | Staging | Production | Doit différer |
| --- | --- | --- | --- |
| `POSTGRES_USER` | utilisateur staging | utilisateur production | oui |
| `POSTGRES_PASSWORD` | mot de passe staging | mot de passe production | **oui, impératif** |
| `POSTGRES_DB` | `wourri_staging` | `wourri_prod` | oui |
| `WOURI_API_KEY` | clé staging | clé production | **oui, impératif** |
| `WOURI_API_KEY_PREVIOUS` | ancienne clé staging (rotation) | ancienne clé production | oui |
| `ALLOWED_ORIGINS` | domaines staging | domaines production | oui |
| `API_IMAGE_TAG` | `staging` | tag de version figé | oui |
| `WA_IMAGE_TAG` | `staging` | tag de version figé | oui |
| `LOG_LEVEL` | `DEBUG` ou `INFO` | `INFO` | recommandé |
| `HEALTHCHECKS_API_URL` | ping staging | ping production | oui |
| `HEALTHCHECKS_BACKUP_URL` | ping staging | ping production | oui |
| `HEALTHCHECKS_WA_URL` | ping staging | ping production | oui |

En production, épingler `API_IMAGE_TAG` et `WA_IMAGE_TAG` sur une version
précise plutôt que sur un tag mouvant : un redéploiement doit être reproductible
et un retour arrière possible.

## 4. Fichiers de secrets Docker

Les deux compose montent deux secrets depuis des fichiers, à créer **dans le
répertoire de chaque projet, séparément** :

```
secrets/postgres_password
secrets/api_secret_key
```

Contraintes :

- contenu différent entre staging et production ;
- permissions restrictives (`chmod 600`) ;
- jamais commités. Le dépôt les ignore désormais explicitement (`secrets/` dans
  `.gitignore`), mais la vigilance reste requise : ne jamais les coller dans un
  ticket, une capture ou un rapport.

## 5. Vérifications d'isolation après création

À exécuter sur le serveur une fois les deux projets déployés. Chaque commande
doit renvoyer des ensembles disjoints.

```bash
# Réseaux : deux réseaux distincts, aucun conteneur commun
docker network ls | grep wourri

# Volumes : aucun volume partagé entre les deux environnements
docker volume ls | grep wourri

# Bases : la base de production ne doit pas être joignable depuis le conteneur staging
docker exec wourri_api_staging sh -c 'echo $POSTGRES_URL' | grep -c wourri_prod
# Résultat attendu : 0
```

Critère d'acceptation INF-06 : aucun secret ni base de production partagé avec le
staging. Les trois commandes ci-dessus le démontrent.

## 6. Correspondance avec les environnements Convex

Le plan de données Convex a sa propre isolation, par projet Convex. Les deux
doivent être cohérents : un service Dokploy staging pointe vers le Convex
staging, jamais vers la production.

| Environnement | Projet Dokploy | Déploiement Convex |
| --- | --- | --- |
| Staging | `wouri-staging` | `https://spotted-chickadee-971.convex.cloud` |
| Production | `wouri-production` | `https://grand-alligator-409.convex.cloud` |

Quand le frontend et les services consommeront Convex, ajouter dans chaque projet
Dokploy la variable d'URL Convex correspondante, et poser symétriquement
`SITE_URL` côté Convex (voir `convex-runbook.md`).

## 7. Point de vigilance relevé à l'audit

Le répertoire `/etc/dokploy` est en permissions `777`. Les sous-répertoires
sensibles sont correctement protégés (`ssh` en `700`, `acme.json` en `600`), mais
resserrer `/etc/dokploy` en `755` est recommandé lors de l'audit Docker/UFW prévu
en priorité haute par le rapport d'infrastructure.
