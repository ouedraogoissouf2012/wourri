# Registre des constats — préparation d'issues

> **Usage interne.** Ce document n'est pas destiné à un tiers. Il consigne
> l'ensemble des manquements relevés lors de la session de lecture du
> 2026-09-10/11, dans un format directement convertible en issues.
>
> **Périmètre** : `wouri-api` uniquement.
> **Code de référence** : `03796ea` (branche `fix/docker-copy-static`), branche
> principale `APIPy`.
> **Constats** : 26, dont 5 critiques.

---

## Convention

| Marque | Signification |
|---|---|
| **[PROUVÉ]** | Exécuté ou mesuré pendant la session — sortie de commande, appel réel, exécution du code |
| **[LU]** | Établi par lecture du code, référence `fichier:ligne` vérifiée |

| Gravité | Critère |
|---|---|
| **Critique** | Produit un échec fonctionnel silencieux aujourd'hui, en production |
| **Majeur** | Dégrade la qualité du service ou bloque une évolution prévue |
| **Mineur** | Dette, incohérence, ou piège armé pour plus tard |

Les cinq constats critiques ont été **revalidés en bloc** avant rédaction.

---

## 1. Vue d'ensemble

| Thème | Constats | Dont critiques |
|---|---:|---:|
| Persistance et état | 5 | 2 |
| Chaîne météo | 8 | 2 |
| Corpus et données métier | 5 | 0 |
| Surface d'entrée | 2 | 1 |
| Architecture et dette | 6 | 0 |

### Recoupement avec les issues ouvertes

| Constat | Issue existante | Statut |
|---|---|---|
| `C-14` recherche vectorielle inopérante | **#297** | à rattacher — l'ADR traite le *gating*, pas le texte de requête |
| `C-15` calendrier incomplet, `C-16` sorgho | **#298** | à rattacher — même famille « trous de données » |
| `C-24` numérotation ADR | branche `fix/debt-adr-renumber` | travail déjà engagé |

Les 23 autres constats **n'ont pas d'issue**.

---

## 2. Persistance et état

### C-01 · Deux fichiers de feedback ne survivent pas à un redéploiement
**Critique · [PROUVÉ]**

`app/routers/feedback.py:43` et `:50` écrivent dans `../../data/`, soit
`/app/data/` en conteneur. Ce chemin **n'est pas monté** dans les volumes du
service API (`hf_cache`, `audio_output`, `api_logs` uniquement).

`app/services/lqe_paths.py` documente pourtant le problème dès sa première
ligne — *« En prod Dokploy, /app/data n'est PAS monté → perdu à chaque
Redeploy »* — et contourne en écrivant sous `/app/logs/lqe`. La file
d'amélioration a été migrée ; `feedback_candidates.jsonl` et
`feedback_negatif.jsonl` ne l'ont pas été.

**Effet** : la file de revue native d'ADR-0019 et le signal de réécriture C5 sont
vidés à chaque merge, puisque le déploiement est automatique.

**Piste** : appliquer `lqe_paths` à ces deux chemins, ou monter un volume `data`.

> **Issue [#518](https://github.com/ouedraogoissouf2012/wourri/issues/518)** — `fix(feedback): persister feedback_candidates et feedback_negatif hors de /app/data`

---

### C-02 · L'historique de conversation n'est pas partagé entre les workers
**Critique · [PROUVÉ]**

`app/services/conversation_history.py:10` — `_conversation_history` est un
`defaultdict` module-level. `Dockerfile.prod:211` lance `--workers 2`.

**Effet** : deux processus, deux dictionnaires. Un agriculteur dont les messages
alternent entre workers perd son contexte une fois sur deux. Ce n'est pas lié au
redémarrage : c'est permanent.

**Piste** : externaliser l'historique (table, ou store partagé), ou documenter
explicitement la limite et réduire à un worker.

> **Issue [#520](https://github.com/ouedraogoissouf2012/wourri/issues/520)** — `fix(chat): historique conversationnel partagé entre workers`

---

### C-03 · La météo n'est jamais persistée
**Majeur · [PROUVÉ]**

`app/services/weather.py` — deux caches RAM de 900 s, aucune écriture en base.

**Effet** : aucune grandeur cumulée n'est calculable — séquence sèche, cumul
décadaire, degrés-jours, durée d'humectation. C'est le verrou qui bloque toute
évolution vers un conseil agronomique, **indépendamment de la source de
données**.

**Piste** : historiser les observations reçues. Débloque quatre familles
d'indicateurs sans donnée nouvelle.

> **Issue [#521](https://github.com/ouedraogoissouf2012/wourri/issues/521)** — `feat(meteo): historiser les observations reçues (socle des indicateurs cumulés)`

---

### C-04 · Le cache météo est dupliqué par worker
**Mineur · [LU]**

Même mécanique que `C-02`, impact bénin : jusqu'à deux fois plus d'appels au
fournisseur.

> **Traité dans [#520](https://github.com/ouedraogoissouf2012/wourri/issues/520)** — section « Constat lié ».

---

### C-05 · Aucun point d'ingestion météo côté FastAPI
**Majeur · [PROUVÉ]**

Recherche sur `app/routers/` : aucun endpoint d'ingestion météo. Le seul point
d'entrée est la mutation Convex `publishWeatherObservation`.

**Effet** : la table `weatherObservations` — conçue pour une source d'autorité,
avec provenance, fenêtre de validité et abstention — **n'est pas reliée au moteur
de conversation**, qui est porté par FastAPI.

**Piste** : pont de lecture Convex → FastAPI, ou point d'ingestion FastAPI. C'est
le chantier technique central de tout changement de fournisseur.

> **Issue [#522](https://github.com/ouedraogoissouf2012/wourri/issues/522)** — `feat(meteo): relier la table d'observations au moteur de conversation`

---

## 3. Chaîne météo

### C-06 · La résolution de ville échoue sur les accents
**Critique · [PROUVÉ]**

`app/data/cities.py` est incohérent : certaines clés sont accentuées (`Séguéla`,
`Odienné`, `Soubré`, `Bouaflé`), d'autres non (`Bouake`, `Korhogo`). `get_city()`
ne normalise pas les diacritiques.

```
get_city('Bouake')  -> Bouake        get_city('Bouaké')  -> None
get_city('Séguéla') -> Séguéla       get_city('Seguela') -> None
detect_city('je suis a Bouaké')      -> None
```

**Aggravation** : `app/routers/demo.py` déclare `city: str = "Bouaké"` **avec
accent**, et le répète en fallback. Toute requête démo sans ville explicite part
donc avec une ville introuvable → `weather_data = None`. C'est la surface exposée
à la Console.

**Piste** : normaliser en NFD des deux côtés de la comparaison. Le mécanisme
existe déjà dans le projet — `strip_tones()` dans `nlu/concept_extractor.py`.

> **Issue [#516](https://github.com/ouedraogoissouf2012/wourri/issues/516)** — `fix(cities): normaliser les accents dans get_city et detect_city (+ défaut démo)`

---

### C-07 · Le chat lit la mesure instantanée au lieu du cumul journalier
**Critique · [PROUVÉ]**

`get_weather_forecast_tomorrow` appelle `forecast_days=2` et ne lit que l'index
`[1]` (`weather.py:186-194`). L'index `[0]` — l'agrégat de la journée en cours —
**est téléchargé puis jeté**.

Mesure du 2026-09-10 sur Bouaké, même réponse API :

| Source | Valeurs | Verdict produit |
|---|---|---|
| `current` (13:15) — seul lu | code 51, 0,10 mm | `pluie_legere` → « bon moment pour semer » |
| `daily[0]` — journée entière | code **95**, **12,60 mm**, 94 % | `orage` → « mettez à l'abri immédiatement » |

**Effet** : conseil de semis délivré un jour d'orage annoncé.

**Piste** : exploiter `daily[0]`, déjà présent dans la réponse. Aucun appel
supplémentaire.

> **Issue [#517](https://github.com/ouedraogoissouf2012/wourri/issues/517)** — `fix(meteo): utiliser l'agrégat journalier (daily[0]) pour le conseil, pas la mesure instantanée`

---

### C-08 · Les mêmes seuils sont appliqués à deux fenêtres temporelles
**Majeur · [PROUVÉ]**

`classify_meteo` reçoit les mêmes seuils (`> 5 mm`, `> 0 mm`) depuis deux
appelants :

- `build_meteo_bambara` → `precipitation` **courante**, fenêtre 15 min (`interval: 900`) ;
- `build_meteo_prevision` → `precipitation_sum` **journalier**.

5 mm en un quart d'heure est une averse violente ; 5 mm sur 24 h est une pluie
modérée.

Borne mesurée : `4.9 → pluie_legere`, `5.0 → pluie_legere` (`> 5` strict),
`5.1 → grosse_pluie`. La prévision du 2026-09-11 était à exactement 5,00 mm.

> **Issue [#524](https://github.com/ouedraogoissouf2012/wourri/issues/524)** — `fix(meteo): seuils de précipitation distincts selon la fenêtre temporelle`

---

### C-09 · Humidité et vent reçus mais jamais utilisés en décision
**Majeur · [PROUVÉ]**

`classify_meteo(temperature, precipitation, weather_code)` ne prend que trois
paramètres. `humidity` et `wind_speed` ne sont lus que dans le bloc de prompt du
LLM et dans la réponse REST.

**Effet** : deux des cinq variables reçues n'influencent en rien le conseil. Or
l'humidité relative est la variable maîtresse des stades séchage et stockage, et
un signal fort de pression fongique.

> **Issue [#523](https://github.com/ouedraogoissouf2012/wourri/issues/523)** — `feat(meteo): exploiter l'humidité relative dans le moteur de décision`

---

### C-10 · Le brouillard est classé « ciel dégagé »
**Majeur · [LU]**

Les codes WMO **45** et **48** sont mappés dans `WEATHER_CODES` mais aucun
prédicat de `classify_meteo` ne les capture — ils tombent sur la condition par
défaut `degage`.

**Effet** : l'agriculteur s'entend dire que le soleil est clair un matin de
brouillard. Fréquent en zone forestière, et pertinent agronomiquement.

> **Issue [#527](https://github.com/ouedraogoissouf2012/wourri/issues/527)** — `fix(meteo): traiter le brouillard (codes 45/48) comme condition propre`

---

### C-11 · `advice` est calculé et jamais lu
**Mineur · [PROUVÉ]**

Produit à `weather.py:135`, relu dans aucun autre fichier de `app/`. Il ne sort
que par `/api/weather/{city}`, route que le serveur WhatsApp n'appelle jamais —
zéro occurrence de « weather » ou « meteo » dans `whatsapp-server/lib/`.

Cette route n'est pas non plus instrumentée : `_MONITORED_PREFIXES` ne la couvre
pas.

> **Issue [#530](https://github.com/ouedraogoissouf2012/wourri/issues/530)** — `chore(meteo): statuer sur generate_farming_advice (brancher ou retirer)`

---

### C-12 · Zone morte de conseil entre 20 et 30 °C
**Mineur · [PROUVÉ]**

`TEMP_ADVICE_FR` teste `> 35`, `> 30`, `< 20`. L'intervalle [20, 30] ne déclenche
rien — c'est la plage la plus fréquente en Côte d'Ivoire.

Latent tant que `C-11` n'est pas résolu.

> **Traité dans [#530](https://github.com/ouedraogoissouf2012/wourri/issues/530)** — section « Constat lié ».

---

### C-13 · La météo est appelée à chaque requête chat
**Mineur · [LU]**

`chat_service.py:94-96` appelle `get_weather(city)` pour 100 % des requêtes, y
compris en anglais ou pour une question de stockage. Le cache absorbe
l'essentiel, mais le premier appel de chaque fenêtre coûte jusqu'à 5 s sur le
chemin critique.

> **Issue [#538](https://github.com/ouedraogoissouf2012/wourri/issues/538)** — `perf(chat): n'appeler la météo que lorsqu'elle est exploitée`

---

## 4. Corpus et données métier

### C-14 · La recherche vectorielle ne participe pas au routage
**Majeur · [LU]** — rattacher à **#297**

`corpus_service.py:288` : le texte embeddé est `f"{intent} {culture}"`, soit
littéralement `"CONSEIL_PRODUCTION CULTURE_RIZ"` — pas la question de
l'agriculteur. Le `WHERE` filtre déjà sur `intent` et `cultures` ; l'`ORDER BY`
ne classe qu'un sous-ensemble déjà correct, et `_best_result_pg` le reclasse par
`season_scoring` en ignorant la distance.

**Effet** : le routage est assuré à 100 % par l'`IntentClassifier`. L'index
vectoriel ne décide de rien. C'est ce qui bloque les *free-form queries* visées
en P2.

ADR-0028 traite le *gating* de la distance, mais pas le texte de requête.

> **Issue [#528](https://github.com/ouedraogoissouf2012/wourri/issues/528)** — `fix(corpus): embedder la question de l'utilisateur, pas l'étiquette d'intent` — rattacher #297

---

### C-15 · Dix cultures du corpus n'ont aucun calendrier
**Majeur · [PROUVÉ]** — rattacher à **#298**

```
cultures du corpus    : 22
cultures au calendrier: 13
```

Sans calendrier, aucun conseil saisonnier n'est ajouté. Les cultures concernées :

`ANACARDE · PALMIER_HUILE · BANANE · CAFE · ANANAS · GOMBO · OIGNON · MANGUE · NERE · AGRUMES`

**Aggravation** : ce sont les deux **mieux couvertes** du corpus — anacarde
**20 entrées** (1ʳᵉ), palmier à huile **15** (2ᵉ). Les cultures les plus investies
en validation reçoivent la réponse la moins enrichie.

> **Issue [#525](https://github.com/ouedraogoissouf2012/wourri/issues/525)** — `data(calendrier): ajouter les calendriers culturaux manquants (10 cultures)` — rattacher #298

---

### C-16 · `CULTURE_SORGHO` est inatteignable, et les labels divergent
**Mineur · [PROUVÉ]** — rattacher à **#298**

`CULTURE_SORGHO` a un label (`sentence_builder.py:22`) et un calendrier complet
(`calendrier_agricole.py:89`, nom dioula `keninge`), mais n'existe **ni** dans
`nlu_concepts.json` (23 concepts `CULTURE_*`) **ni** dans le corpus.

Par ailleurs `CULTURE_LABELS` est **dupliqué** entre `sentence_builder.py`
(24 entrées) et `chat/nlu_preprocessor.py` (23), avec cette divergence exacte —
alors que `docs/constraints.md` §1.2 interdit le hardcoding de données métier.

> **Issue [#531](https://github.com/ouedraogoissouf2012/wourri/issues/531)** — `fix(nlu): source unique pour CULTURE_LABELS + statuer sur le sorgho`

---

### C-17 · Le registre pronominal diverge entre les sources de texte
**Majeur · [PROUVÉ]**

Mesure sur les trois sources qui composent un message :

| Source | Registre | Mesure |
|---|---|---|
| Corpus IVR | `Aw` / `Alu` (2ᵉ pl.) | **180 entrées sur 197** |
| Templates météo | `Aw` | 5 templates sur 6 |
| Conseils calendrier | **`I`** (2ᵉ sg.) | **4 phases sur 9** |

Message réellement assemblé sur le chemin conseil riz :

> `Aw ye màlo sɛnɛ… Aw ye dugukolo… Aw ye sɛnɛ… **I ka i ka** foro kɔlɔsi.`

Le français porte la même rupture : *« à **toi** … **ton** assistant … **Pensez**
à arroser **vos** cultures … **Tu** veux de l'aide ? »*

`CLAUDE.md` pose pourtant la règle : *« Impératif pluriel : Aw ye + objet +
verbe »*.

**Piste** : réécrire les 4 chaînes `CONSEILS_BAMBARA` concernées, avec
re-validation native (ADR-0014) limitée à ces 4 chaînes.

> **Issue [#526](https://github.com/ouedraogoissouf2012/wourri/issues/526)** — `fix(calendrier): harmoniser le registre pronominal des conseils de phase (Aw)`

---

### C-18 · Le RAG n'est pas branché au chat
**Majeur · [PROUVÉ]**

`app/services/rag_knowledge.py` existe et est exposé sur `/api/rag/*`, mais
**zéro import** dans `chat_service.py`, `app/services/chat/` ou
`app/routers/chat.py`.

**Effet** : la base de connaissances agricoles n'atteint jamais l'agriculteur.
C'est pourtant la brique que `docs/vision.md` désigne comme centrale en P2.

> **Issue [#529](https://github.com/ouedraogoissouf2012/wourri/issues/529)** — `feat(chat): statuer sur le RAG — brancher dans la cascade ou retirer`

---

## 5. Surface d'entrée

### C-19 · Photos, documents et localisation totalement ignorés
**Critique · [PROUVÉ]**

Recherche sur `whatsapp-server/lib/` : **aucune occurrence** de `imageMessage`,
`documentMessage`, `videoMessage`, `stickerMessage`, `locationMessage`.

**Effet** : un agriculteur qui envoie une photo de feuille malade ne reçoit
**rien** — `_extractMessageText` renvoie une chaîne vide, puis
`if (!messageText) continue`. Aucun message d'erreur, aucun accusé.

C'est l'absence la plus notable pour un bot agricole : le diagnostic visuel est
l'usage naturel de la photo, et `DIAGNOSTIC_PROBLEME` est le 2ᵉ intent du corpus
avec 26 entrées. La localisation GPS est également ignorée, alors que la ville
est le pivot de toute la météo.

**Piste minimale** : accuser réception et orienter, plutôt que d'ignorer
silencieusement.

> **Issue [#519](https://github.com/ouedraogoissouf2012/wourri/issues/519)** — `feat(whatsapp): traiter les messages non textuels (photo, localisation) — a minima accuser réception`

---

### C-20 · `ChatRequest.message` sans limite de longueur
**Mineur · [LU]**

`app/models/schemas.py` — `message: str` sans contrainte, alors que
`DemoAgriRequest` plafonne à 2000 caractères. Asymétrie non justifiée.

> **Issue [#536](https://github.com/ouedraogoissouf2012/wourri/issues/536)** — `fix(schemas): borner la longueur de ChatRequest.message`

---

## 6. Architecture et dette

### C-21 · Le singleton du filtre LM ignore ses paramètres injectés
**Majeur · [LU]**

`app/services/validation/lm_filter.py` combine `__new__` renvoyant
`cls._instance` et `if hasattr(self, '_initialized'): return`. Si une instance est
construite avant `get_lm_filter()`, les seuils et le flag lus depuis la config
sont **abandonnés sans erreur ni log**.

Sans conséquence aujourd'hui (`enable_lm_rescoring: False`, `config.py:229`),
mais c'est un piège armé pour le jour de l'activation.

> **Issue [#537](https://github.com/ouedraogoissouf2012/wourri/issues/537)** — `fix(lm-filter): supprimer le pattern singleton silencieux`

---

### C-22 · Documentation d'entrée contredisant le code
**Majeur · [LU]**

| Fichier | Décrit | Réalité |
|---|---|---|
| `README.md` | Edge-TTS, OpenWeatherMap | Piper, Open-Meteo |
| `ROADMAP.md` | ChromaDB, NeMo comme cible | retirés (#203, ADR-0027) |
| `PROGRESS.md` | « ASR Soloni NeMo ✅ Fonctionnel » | retiré |
| `main.py:378` | `"tts_french": True  # Edge-TTS est toujours disponible` | Piper |
| `config.py:45` | `tts_french_voice` (voix Edge) | inutilisé |

Ce sont les trois premiers fichiers que lirait un développeur tiers — l'équipe à
constituer prévue par `docs/vision.md` §7.

> **Issue [#533](https://github.com/ouedraogoissouf2012/wourri/issues/533)** — `docs: remettre README, ROADMAP et PROGRESS en cohérence avec le code`

---

### C-23 · `docker-compose.prod.yml` décrit une infrastructure abandonnée
**Mineur · [LU]**

L'en-tête décrit une VM Scaleway et le chemin `/srv/wourri/`, contredit par
ADR-0024 (Contabo + Dokploy).

> **Issue [#534](https://github.com/ouedraogoissouf2012/wourri/issues/534)** — `docs(deploy): aligner l'en-tête docker-compose.prod.yml sur ADR-0024`

---

### C-24 · Collision de numéros ADR
**Mineur · [PROUVÉ]** — travail engagé sur `fix/debt-adr-renumber`

Deux fichiers `0024-*` coexistent (`deploiement-wourri-dokploy`,
`transition-convex-multitenant`). `0026-plateforme-api-produit-convex.md`
(statut « proposé », non commité) doublonne `0030` (statut « accepté »).

> **Issue** — rattacher à la branche existante.

---

### C-25 · Fichiers non commités dans le dépôt
**Mineur · [PROUVÉ]**

20 entrées non suivies : 5 brouillons de validation dioula, `docs/linguaops/`,
`docs/research/`, 5 modules `tools/_bv_*.py`, plus 2 fichiers modifiés
(`tools/bambara_validator.py` et son test).

> **Issue [#535](https://github.com/ouedraogoissouf2012/wourri/issues/535)** — `chore(repo): statuer sur les fichiers non suivis (committer ou ignorer)`

---

### C-26 · `phrases_attestees` lues mais jamais restituées
**Mineur · [LU]**

Lues en base par `get_phrases_for_intent`, puis placées **uniquement dans
`meta`** (`ivr_searcher.py:163`) — jamais dans le texte envoyé. Elles servent à
l'observabilité, pas à la réponse. Le coût de lecture est payé sans usage
utilisateur.

> **Issue [#532](https://github.com/ouedraogoissouf2012/wourri/issues/532)** — `chore(corpus): statuer sur l'usage de phrases_attestees`

---

## 7. Proposition de séquencement

### Lot 1 — Échecs fonctionnels silencieux en production

| Constat | Issue | Titre |
|---|---|---|
| `C-06` | #516 | normaliser les accents dans `get_city` / `detect_city` |
| `C-07` | #517 | utiliser l'agrégat journalier pour le conseil |
| `C-01` | #518 | persister les fichiers de feedback |
| `C-19` | #519 | traiter les messages non textuels, a minima accuser réception |
| `C-02` | #520 | historique conversationnel partagé entre workers |

Ces cinq constats produisent aujourd'hui, en production, un échec que
l'utilisateur ne voit pas et que le système ne signale pas.

### Lot 2 — Socle des évolutions agronomiques

| Constat | Issue | Titre |
|---|---|---|
| `C-03` | #521 | historiser les observations météo |
| `C-05` | #522 | relier la table d'observations au moteur |
| `C-09` | #523 | exploiter l'humidité relative |
| `C-08` | #524 | seuils distincts selon la fenêtre temporelle |

`C-03` conditionne tout le reste : sans historisation, aucune grandeur cumulée.

### Lot 3 — Qualité du conseil

| Constat | Issue | Titre |
|---|---|---|
| `C-15` | #525 | calendriers culturaux manquants (10 cultures) |
| `C-17` | #526 | harmoniser le registre pronominal |
| `C-10` | #527 | traiter le brouillard |
| `C-14` | #528 | embedder la question, pas l'étiquette d'intent |

### Lot 4 — Décisions à prendre

`C-11` / `C-12` (`advice`), `C-18` (RAG), `C-26` (`phrases_attestees`),
`C-16` (sorgho) : quatre briques entretenues sans usage produit. Chacune appelle
une décision — brancher ou retirer — plutôt qu'un correctif.

### Lot 5 — Dette documentaire

`C-22`, `C-23`, `C-24`, `C-25`, `C-20`, `C-13`, `C-21`, `C-04`.

---

## 8. Note de méthode

Deux enseignements de la session valent d'être consignés.

**La lecture du code établit le contrat, pas le comportement.** Les constats
`C-07`, `C-08` et `C-12` ne sont apparus qu'à l'exécution sur des données
réelles. Une relecture, aussi attentive soit-elle, ne les aurait pas révélés.

**Une suite de tests verte ne protège pas d'une mauvaise entrée.** Vingt-trois
tests couvrent la chaîne météo, y compris deux tests qui vérifient qu'on ne
confond pas probabilité et millimètres. Aucun ne pose la question de savoir si
`current.precipitation` est la bonne grandeur à donner à `classify_meteo` —
c'est précisément `C-07`.

---

## 9. Journal

| Date | Ajout |
|---|---|
| 2026-09-11 | Création — 26 constats issus de la session de lecture des 10 et 11 septembre |
| 2026-09-11 | Ouverture de **23 issues** (#516 → #538) — numéros reportés ci-dessus |
