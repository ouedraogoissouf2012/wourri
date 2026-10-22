# Demande — Remise à zéro des validations baoulé dans l'atelier

- **Date** : 2026-10-22
- **Demandeur** : Ouedraogo Issouf (chef de projet)
- **Destinataire** : la fenêtre « déploiement » (accès au serveur)
- **Réf.** : ADR-0045, issue #475
- **Sans lien avec la démo de vendredi** : la démo utilise le dictionnaire démo (PR #588), pas ces validations.

## 1. Pourquoi

Esse, le locuteur baoulé, a commencé à valider les mots-clés et les paires question → réponse.
Il reconnaît des erreurs et veut **tout reprendre à zéro**.

Jusqu'ici, l'atelier ne le permettait pas :
- une fiche décidée disparaissait de son écran ;
- une correction écrasait le texte d'origine.

## 2. Ce que change la PR (une fois fusionnée, Dokploy reconstruit `lqe` et `lqe-web`)

- **Écran « Mes décisions »** : le locuteur revoit ce qu'il a accepté, rejeté ou corrigé. Le bouton
  « Reprendre » remet la fiche dans « À accepter » avec son texte d'origine.
- **Texte d'origine** : à la première correction, il est gardé dans `meta.texte_origine`.
- **Script de remise à zéro en lot** : `scripts/reprendre_validations.py`. Les fichiers d'import
  d'origine sont dans l'image (`scripts/originaux/`), il n'y a rien à copier.

Le script :
- ne touche **jamais** une fiche publiée (`production`), ni une autre langue (le dioula reste intact) ;
- ne touche pas, par défaut, au contenu ni aux phrases de la dictée (table séparée) ;
- fait un essai à blanc par défaut ;
- avec `--appliquer`, écrit une sauvegarde JSON de l'état avant.

## 3. Ce qu'on demande, dans l'ordre

**Prérequis** : Esse a arrêté de valider (confirmé par le chef de projet).

1. Après la fusion, vérifier que l'image `lqe` est reconstruite et que le script est présent :

   ```bash
   docker service ls | grep -i lqe          # repérer le service de l'API atelier (pas « -web »)
   C=$(docker ps -q -f name=<service lqe> | head -1)
   docker exec "$C" ls scripts/reprendre_validations.py scripts/originaux/
   ```

2. Faire l'**essai à blanc**, qui n'écrit rien :

   ```bash
   docker exec "$C" python -m scripts.reprendre_validations --langue bci \
     --original scripts/originaux/bci_mots_cles_et_paires_2026-10-21.json \
     --original scripts/originaux/bci_mots_wiktionnaire_2026-10-22.json
   ```

   Il affiche le nombre de fiches qui seraient remises « à valider », par type et par statut, avec
   des exemples (texte actuel → texte d'origine). **Coller ce résultat en commentaire de la PR**
   avant d'aller plus loin.

3. Si le résultat est conforme, **appliquer**. La sauvegarde est écrite dans le conteneur puis
   copiée sur l'hôte, car le disque d'un conteneur Swarm disparaît au redéploiement :

   ```bash
   docker exec "$C" python -m scripts.reprendre_validations --langue bci \
     --original scripts/originaux/bci_mots_cles_et_paires_2026-10-21.json \
     --original scripts/originaux/bci_mots_wiktionnaire_2026-10-22.json \
     --appliquer --sauvegarde /tmp/reprise_bci.json
   docker cp "$C":/tmp/reprise_bci.json ./reprise_bci_$(date -u +%Y%m%d).json
   ```

4. **Contrôle** : relancer l'essai à blanc (étape 2). Il doit afficher
   `Fiches remises « a valider » : 0`.

## 4. Points d'attention

- Si l'essai à blanc annonce des **fiches publiées** : le script ne les touche pas, et c'est
  voulu. Le signaler en commentaire, le chef de projet décidera.
- Une ligne « texte d'origine introuvable » concerne une fiche sans original connu. Elle est
  remise « à valider » avec son texte actuel.
- Rejouer le script est sans risque : une fiche déjà « à valider » et intacte n'est pas touchée.

## 5. Réponse attendue

En commentaire de la PR :
- le résultat de l'essai à blanc (étape 2) ;
- puis celui de l'application (étape 3) ;
- puis celui du contrôle (étape 4).
