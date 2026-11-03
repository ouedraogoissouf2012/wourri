# ADR-0049 — Messages système d'une langue : texte validé versionné, voix publiée depuis l'atelier

**Statut** : accepté
**Date** : 2026-11-02
**Auteur(s)** : Claude (assistant) sous direction de Ouedraogo Issouf
**Valideur** : Ouedraogo Issouf — **option B retenue le 2026-11-03**
**ADRs liés** : [ADR-0031](0031-moteur-amelioration-linguistique.md) (jamais d'invention linguistique), [ADR-0034](0034-atelier-parite-linguistique.md) (réponses natives produites par l'atelier), [ADR-0039](0039-politique-reponse-llm-et-escalade.md) (accusé rendu en français — dette tracée), [ADR-0043](0043-accueil-baoule-langue-annoncee.md) (langue annoncée, repli honnête), [ADR-0045](0045-nlu-baoule-methode-dioula-validation-atelier.md) (corpus baoulé construit depuis l'atelier), [ADR-0048](0048-voix-baoule-sur-contabo-processeur.md) (serveur voix baoulé)
**Issues** : #475, #476, #477

---

## Contexte

Un **message système** est une phrase que Wourri prononce de lui-même : le repli quand
il n'a pas compris, l'accusé d'escalade, la salutation. Ce n'est pas une réponse de
corpus : aucune question de l'agriculteur ne la déclenche par ressemblance.

**Aujourd'hui, tous les messages système sont en français, en dur dans le code,
sans voix.**

- Repli baoulé : chaîne littérale dans `app/services/chat/handlers/baoule_handler.py`,
  renvoyée sans `response_local` ni `audio_url`.
- Accusé d'escalade : `ESCALATION_MESSAGE_FR` dans `app/services/chat/llm_guard.py`.

**Les deux langues servies ont le même trou, et il est déjà écrit** :

- ADR-0039 : *« l'accusé est rendu en FRANÇAIS même en dioula/both […] La formulation
  dioula viendra d'une validation native. »* — dette tracée le 2026-09-24, non payée.
- ADR-0043 : *« la réponse est en texte français, alors qu'une partie du public baoulé
  lit peu le français. »* — négative assumée le 2026-10-17, non levée.

**Pourquoi on décide maintenant.** Le 2026-11-02, un agriculteur écrit « Bonjour » en
baoulé et reçoit un texte français. Le baoulé est **en service** depuis ce jour
(193 réponses natives avec la voix du locuteur) : le repli est devenu le seul endroit
où Wourri parle encore exclusivement français à un public qui lit peu le français.
Le défaut n'est plus théorique, il est en production.

### État vérifié du chemin audio (2026-11-02)

Le constat qui pèse le plus lourd sur cette décision :

| Maillon | Emplacement | Nombre | Automatisé ? |
|---|---|---|---|
| Enregistrement du locuteur | atelier, `/data/audio` (`.webm`) | 448 | oui (écran Dictée) |
| Conversion + copie | — | — | **non — fait à la main** |
| Fichier servi | serveur voix, `/donnees/reponses_ogg` (`.ogg`) | 433 | — |
| Service HTTP | `GET /audio/{nom}` du serveur voix | — | oui |

Les 433 `.ogg` ont été convertis et copiés **à la main le 2026-11-02 à 16 h 49**.
**Aucun script ne fait ce transfert.** Conséquence immédiate et mesurable : les
**70 réponses corrigées** que le locuteur doit réenregistrer (#475) arriveront en
`.webm` dans l'atelier et **ne seront pas servies**, faute de publication.

Autrement dit : décider où ranger le *texte* d'un message système ne sert à rien si la
*voix* n'a pas de chemin. Les deux questions sont une seule décision.

### Contraintes applicables

- **ADR-0031 / `constraints.md` §3.3** — aucun mot inventé : le texte d'un message
  système doit venir d'un locuteur natif, validé dans l'atelier.
- **Brief d'intégration (OCP)** — le code existant est extensible, pas modifiable :
  `tts_*.py`, `asr/`, `translation/` sont gelés. On **ajoute**, on ne réécrit pas.
- **ADR-0033** — l'atelier est un service séparé ; le moteur **ne lit pas** sa base.
  Le motif établi est : le moteur écrit, l'atelier lit — jamais l'inverse.
- **ADR-0034 P4** — « activer une langue = un INSERT, zéro code, zéro `if`-langue ».
  Toute solution qui exige un `if language == "bci"` est disqualifiée.

## Questions posées avant la décision

1. L'ADR couvre-t-il le seul baoulé, ou les messages système de **toutes** les langues ?
2. Où vivent les **textes** système validés : fichier versionné du dépôt, ou base de l'atelier ?
3. Comment obtient-on la **voix** : par la dictée (texte imposé, il lit) ou par l'atelier
   (il produit texte et voix ensemble) ?

Réponses obtenues (arbitrage Issouf, 2026-11-02) :

- **Q1 → toutes les langues.** Le dioula a la même dette (ADR-0039) ; un seul ADR solde
  les deux et fixe le motif pour le prochain parler.
- **Q2 → fichier versionné du dépôt.** Même motif que `corpus_ivr_bci.json` : relu au
  démarrage, aucune dépendance nouvelle entre services. Le coût assumé est qu'une
  correction exige un commit et un redéploiement.
- **Q3 → par l'atelier.** Le locuteur produit texte **et** voix en un seul passage, avec
  le mécanisme de « Mes demandes » livré par la PR #605.

Ces trois réponses **excluent** d'emblée : un fichier par langue lu depuis la base
(contredit Q2), un texte écrit par l'équipe sans validation native (contredit ADR-0031),
et une dictée à texte imposé (contredit Q3, et supposerait d'avoir déjà le texte).

## Options étudiées

Les trois options partagent le même amont — le locuteur produit texte + voix dans
l'atelier, sur des concepts système réservés — et se distinguent **uniquement par la
façon dont le résultat atteint la production**. C'est là qu'est la décision.

### Option A — Un fichier par langue + publication manuelle des audios

- **Description.** Nouveau fichier versionné `dictionnaires/messages_systeme_<lang>.json`
  (`{concept: {texte, audio}}`), construit par un script depuis les productions validées.
  Les `.ogg` sont convertis et copiés **à la main** sur le serveur voix, comme aujourd'hui.
- **Avantages.** Aucun mécanisme nouveau ; reproduit exactement le motif de
  `corpus_ivr_bci.json`, déjà éprouvé. Livrable en une PR.
- **Inconvénients.** **Conserve le défaut qui vient de coûter onze jours** : les
  corrections du locuteur sont restées invisibles parce qu'une étape manuelle n'avait
  pas été refaite. On recrée délibérément le même piège, pour les audios cette fois.
  Les 70 réenregistrements resteront muets tant que personne n'y pensera.
- **Coût.** Faible à écrire, **récurrent et invisible** à l'usage.
- **Compatibilité.** Respecte Q2, Q3, OCP, ADR-0033.

### Option B — Un fichier par langue + script de publication des audios

- **Description.** Identique à A pour le texte. En plus, un script
  `scripts/publier_audios.py <langue>` qui : lit les productions validées de l'atelier,
  récupère les `.webm` manquants, les convertit en `.ogg` et les dépose dans le volume
  du serveur voix. Le script est **idempotent** (il ne traite que ce qui manque) et
  **rend compte** (combien publiés, combien déjà présents, lesquels sans audio).
- **Avantages.** La même commande sert **trois besoins** : les messages système, les
  **70 réenregistrements en attente**, et toute collecte future — y compris dans une
  langue qui n'existe pas encore. Rend le transfert **vérifiable** : un écart entre
  l'atelier et le serveur voix devient un chiffre, plus un oubli silencieux.
- **Inconvénients.** Un script de plus à maintenir. Exige `ffmpeg` (ou équivalent) là
  où le script tourne — pas sur le serveur de production, dont ADR-0035 a explicitement
  écarté la dépendance ffmpeg.
- **Coût.** Une demi-journée de plus qu'A. **Supprime** un travail manuel récurrent et
  un mode de panne déjà survenu.
- **Compatibilité.** Respecte Q2, Q3, OCP, ADR-0033 (le script lit l'atelier par son
  API, il n'ouvre aucun accès base entre services), ADR-0035 (conversion hors serveur).

### Option C — Les audios système versionnés dans le dépôt

- **Description.** Texte et `.ogg` des messages système commités ensemble dans
  `dictionnaires/audio_systeme/`, servis par le moteur lui-même.
- **Avantages.** Le message système devient atomique : texte et voix voyagent ensemble,
  impossible d'en déployer un sans l'autre. Aucun transfert à faire.
- **Inconvénients.** Met du **binaire dans Git** — chaque correction de prononciation
  ajoute un `.ogg` à l'historique, définitivement. À une poignée de messages par langue
  c'est tenable ; au-delà, non. Et ça **n'aide pas les 70 réenregistrements**, qui sont
  des réponses de corpus, pas des messages système : le transfert manuel resterait requis
  pour eux. Crée donc **deux chemins audio différents** selon la nature du contenu.
- **Coût.** Faible à écrire, dette de dépôt croissante, et ne règle que la moitié du problème.
- **Compatibilité.** Respecte Q2, Q3, OCP. Heurte la sobriété du dépôt.

### Comparatif

| Critère | A | B | C |
|---|---|---|---|
| Sert aussi les 70 réenregistrements | non | **oui** | non |
| Sert une langue future sans code | oui | **oui** | oui |
| Étape manuelle résiduelle | **oui** | non | non (système seulement) |
| Écart atelier ↔ production détectable | non | **oui** | sans objet |
| Binaire dans Git | non | non | **oui, croissant** |
| Chemins audio distincts à maintenir | 1 | **1** | 2 |
| Effort initial | le plus faible | +0,5 j | faible |
| Reproduit un mode de panne déjà vécu | **oui** | non | partiellement |

## Décision

**Option retenue** : **B — fichier versionné par langue + script de publication des audios.**

**Justification** : les trois options coûtent presque la même chose à écrire ; une seule
supprime l'étape manuelle qui a déjà fait perdre onze jours de travail du locuteur, et
c'est la seule qui serve aussi les 70 réenregistrements déjà en attente dans l'atelier.
L'option A revenait à recréer sciemment le piège qu'on venait de constater ; l'option C
met du binaire croissant dans Git et laisse un second chemin audio à maintenir.

Arbitrage d'Issouf, 2026-11-03.

## Conséquences

### Conséquences de B

- **Positives** :
  - le repli et la salutation sont dits **en baoulé, avec la voix du locuteur**, et en
    dioula dès qu'il aura validé les siens — la dette ADR-0039 est soldée ;
  - les 70 réenregistrements sont publiés par la même commande, sans travail nouveau ;
  - l'écart entre l'atelier et la production devient un **chiffre affiché**, plus un oubli ;
  - une langue nouvelle hérite du mécanisme sans une ligne de code (ADR-0034 P4).
- **Négatives assumées** :
  - une correction d'un message système exige toujours **commit + redéploiement**
    (conséquence directe de Q2, assumée par le valideur) ;
  - dépendance à `ffmpeg` sur le poste qui publie ;
  - tant que le locuteur n'a pas produit les textes, **le repli reste en français** :
    cet ADR décide le mécanisme, il ne crée aucun contenu.
- **Dégradation définie** : si un message système n'a pas de version validée dans la
  langue, on sert **le français**, jamais un texte généré ni une langue voisine
  (ADR-0046 : une tournure dioula n'est pas du baoulé). Le comportement actuel devient
  donc le repli explicite du mécanisme, et non plus un défaut.

### Travail induit (après acceptation)

1. Concepts système réservés dans le catalogue NLU (`_SYSTEME_REPLI`, `_SYSTEME_SALUTATION`),
   assignables au locuteur via `/assign` — catalogue `nlu`, mécanisme PR #605.
2. `scripts/construire_messages_systeme.py` → `dictionnaires/messages_systeme_<lang>.json`.
3. `scripts/publier_audios.py <langue>` (option B).
4. Câblage dans `baoule_handler` et `llm_guard` : servir `response_local` + `audio_url`
   quand la langue a un message validé, le français sinon.
5. Tests : présence du repli natif, dégradation vers le français, **et** un test qui
   échoue si un message système est servi dans une autre langue que celle demandée.

### Ce que cet ADR ne décide pas

- Les **salutations horaires** (`salutation_matin/midi/soir/nuit`) contiennent un gabarit
  `{{METEO_CONTEXTUEL}}` rempli par un texte météo qui n'existe dans aucune langue
  locale validée. Elles sont **hors périmètre** : seules `generic_salutation` et
  `generic_fallback` sont traitées ici.
- La régularisation du **statut de l'ADR-0043**, encore `proposé` alors que son code est
  en production depuis le 2026-10-17. À traiter séparément.

## Historique

| Date | Évolution |
|---|---|
| 2026-11-02 | Rédaction. Arbitrages Q1/Q2/Q3 obtenus d'Issouf. Décision laissée TBD. |
| 2026-11-03 | **Option B retenue par Issouf.** Statut : accepté. Mise en œuvre ouverte. |
