# Traitement des données météorologiques

> **Objet** : décrire comment Wourri transforme les données météorologiques
> reçues en un conseil agricole exploitable, avant restitution à l'agriculteur.
>
> **Périmètre** : la logique de traitement, indépendamment de la langue de
> restitution. L'acquisition des données est décrite dans
> [CONTRAT_API_OPEN_METEO.md](CONTRAT_API_OPEN_METEO.md).
>
> **Mesuré le** : 2026-09-11 · ville de référence : Bouaké
> **Code de référence** : `app/services/` @ `03796ea`

---

## Niveau de vérification

| Marque | Signification |
|---|---|
| **[MESURÉ]** | Exécuté sur données réelles pendant la session, daté, reproductible |
| **[CODE]** | Établi par lecture du code source, référence `fichier:ligne` |

---

## 1. Le principe directeur

**Wourri ne transmet pas la météo. Il la convertit en décision agronomique.**

C'est le choix structurant de toute la chaîne. L'agriculteur ne reçoit jamais
« 26,6 °C, 0 mm, code 1 » : il reçoit une **action à mener**, dérivée de ces
valeurs et replacée dans le contexte de sa zone, de sa culture et du mois en cours.

```
DONNEE BRUTE                 DECISION                    ACTION SITUEE
temperature 26.6  ─┐                              ┌─ ville et zone agricole
precipitation 0.0  ├─► 1 condition parmi 6 ──────►├─ cultures de saison
weather_code 1    ─┘                              ├─ phase du calendrier cultural
                                                  └─► message d'action
```

Cette conversion se fait en **cinq phases déterministes**, sans modèle
statistique ni génération de texte : à données identiques, la sortie est
strictement identique. C'est une propriété recherchée — le conseil délivré est
reproductible, auditable et explicable ligne à ligne.

---

## 2. Phase 1 — Normalisation

La réponse du fournisseur est convertie en un **format pivot interne**
(`weather.py:126-140`) — [CODE].

| Champ reçu | Champ interne |
|---|---|
| `current.temperature_2m` | `temperature` |
| `current.relative_humidity_2m` | `humidity` |
| `current.precipitation` | `precipitation` |
| `current.weather_code` | `weather_code` |
| `current.wind_speed_10m` | `wind_speed` |

Deux enrichissements sont ajoutés dès cette phase, depuis les référentiels
internes :

- `city` et `region`, issus du référentiel des 59 villes ;
- `weather_description`, libellé obtenu par traduction du code WMO
  (table de **18 codes**, `weather.py:69`).

**Intérêt de cette phase** : tout le reste de l'application travaille sur un
format stable, indépendant du fournisseur. Un changement de source météo
n'impacterait que ce point de conversion — le moteur de décision, les
référentiels et la composition restent inchangés.

---

## 3. Phase 2 — Mise en cache

Deux caches indépendants, **900 secondes** chacun (`weather.py:27`) — [CODE].

| Cache | Contenu | Clé |
|---|---|---|
| `_weather_cache` | météo instantanée | nom de ville, en minuscules |
| `_forecast_cache` | prévision | nom de ville, en minuscules |

La durée est alignée sur la cadence de rafraîchissement annoncée par le
fournisseur (`interval: 900`). Les deux caches sont séparés pour que la
consultation d'une prévision n'invalide pas la météo courante, et inversement.

**Intérêt** : sur une zone donnée, plusieurs agriculteurs interrogeant le service
dans la même fenêtre de quinze minutes partagent un seul appel réseau.

---

## 4. Phase 3 — Classification

C'est le cœur du traitement : la conversion des mesures en **condition
agronomique**.

Le système emploie deux régimes de décision distincts, adaptés à deux usages.

### 4.1 Régime exclusif — le parcours conversationnel

Une cascade de **6 conditions** évaluées dans l'ordre ; la première satisfaite
l'emporte et les suivantes ne sont pas évaluées (`weather_conditions.py:47`) — [CODE].

| Priorité | Condition | Règle de déclenchement | Nature de l'action induite |
|---|---|---|---|
| 1 | `orage` | `code >= 95` | mise à l'abri immédiate |
| 2 | `grosse_pluie` | `code >= 61` ou `precip > 5` | protection des récoltes, préparation du champ |
| 3 | `pluie_legere` | `code >= 51` ou `precip > 0` | fenêtre favorable aux semis |
| 4 | `couvert` | `code == 3` | pluie possible, préparer le champ |
| 5 | `chaleur` | `temp > 33` | irrigation et protection |
| 6 | `degage` | défaut | arrosage |

**L'ordre encode une priorité de risque, pas une probabilité.** Un orage prime
sur une forte pluie, qui prime sur une pluie légère. Le système retient toujours
la condition dont la conséquence pour l'exploitation est la plus lourde. C'est
une logique de sécurité agricole, délibérément asymétrique.

Structure sous-jacente : un `dataclass(frozen=True)` associant à chaque condition
sa règle de déclenchement et son message d'action. Ajouter une condition consiste
à insérer une entrée dans la liste, sans modifier la logique d'évaluation.

**Résultat** : les 18 codes WMO reconnus se ramènent à **6 décisions
opérationnelles**. Cette réduction est intentionnelle — un agriculteur n'a pas
besoin de distinguer « bruine modérée » de « bruine dense », il a besoin de savoir
s'il peut semer aujourd'hui.

### 4.2 Régime cumulable — le parcours applicatif

Pour les consommateurs applicatifs, le service expose une seconde logique où
**trois axes sont évalués indépendamment** et leurs conseils additionnés
(`weather.py:221`) — [CODE].

| Axe | Paliers | Seuils |
|---|---|---|
| Pluie | 4 | `> 10 mm`, `> 2 mm`, `> 0 mm`, sinon |
| Température | 3 | `> 35 °C`, `> 30 °C`, `< 20 °C` |
| Orage | 1 | `code >= 95` |

Chaque axe retient son premier palier satisfait ; les conseils retenus sont
concaténés.

**Les deux régimes coexistent volontairement.** Ils ne répondent pas au même
besoin : le parcours conversationnel demande **un message court et actionnable**
— d'où l'exclusivité — tandis qu'un consommateur applicatif peut exploiter
plusieurs recommandations simultanées. Les seuils diffèrent d'un régime à
l'autre parce que les sémantiques diffèrent.

---

## 5. Phase 4 — Contextualisation

La condition retenue est ensuite **située** : elle est croisée avec trois
référentiels internes pour devenir un conseil applicable à cet agriculteur, à
cet endroit, à cette date.

### 5.1 Les référentiels croisés — [MESURÉ]

| Référentiel | Volume | Rôle |
|---|---|---|
| Villes | **59** | coordonnées et région administrative |
| Régions → zones | **32** correspondances | rattachement agro-climatique |
| Zones agricoles | **4** | cultures typiques de la zone |
| Calendriers culturaux | **13** | fenêtres de plantation, entretien, récolte |
| Phases culturales | **9** | granularité du conseil dans la saison |

### 5.2 La chaîne de résolution

```
ville
  └─► region administrative
        └─► zone agro-climatique   (Sud-Foret / Centre / Nord-Savane / Ouest-Montagnes)
              └─► cultures typiques de la zone
                    └─► filtrees par le mois en cours
                          └─► cultures actuellement en plantation ou en entretien
```

Les phases « récolte » et « repos » sont volontairement exclues de cette
annonce : on ne signale que les cultures sur lesquelles une action est
actuellement possible. Trois cultures au maximum sont retenues, pour rester
mémorisable à l'oral.

Un défaut de zone est prévu (`ZONE_CENTRE`) : une région non répertoriée ne
bloque jamais la réponse.

### 5.3 Le conseil de phase culturale

Indépendamment de la météo, le système détermine **où en est la culture dans son
cycle annuel**, en croisant le mois courant avec le calendrier de la culture
détectée.

Neuf phases sont distinguées, dont trois subdivisions pour la plantation et trois
pour la récolte :

```
plantation_debut   plantation_milieu   plantation_fin   plantation_passe
entretien
recolte_debut      recolte_milieu      recolte_fin
repos
```

Cette granularité porte une information d'**urgence** : « début de saison de
plantation » et « fin de saison de plantation » appellent des comportements
différents. Le système sait dire qu'il reste peu de temps.

---

## 6. Phase 5 — Composition

Le message final est assemblé par insertion et enrichissement
(`ivr_searcher.py:126-137`) — [CODE].

```
1.  message de base
2.  ─► insertion du conseil meteo a l'emplacement prevu
3.  ─► ajout des cultures de saison de la zone
4.  ─► ajout du conseil de phase culturale
5.  ─► message final
```

L'insertion météo se fait **à un emplacement défini dans le message**, non par
concaténation en fin. Le conseil météo arrive donc là où il a du sens dans le
discours, pas en appendice.

### Exemple mesuré — Bouaké, 2026-09-11 — [MESURÉ]

Entrée : `temperature 26.6` · `precipitation 0.0` · `weather_code 1`

| Étape | Volume |
|---|---|
| Message de base | 19 mots |
| Après contextualisation complète | **47 mots** |

Message restitué (version française) :

> Bonjour à toi ! Je suis Wourri, ton assistant agricole. **Ciel dégagé sur
> Bouake, pas de pluie. Pensez à arroser vos cultures.** **En ce moment, les
> cultures de saison dans votre zone sont : riz et manioc.** Tu veux de l'aide
> sur quoi ?

En gras : les deux blocs produits par le traitement météo et la contextualisation.
Trois nombres en entrée, un conseil situé en sortie.

---

## 7. Conditions d'application

Le traitement météo ne s'applique pas uniformément à toutes les réponses.

| Parcours | Traitement météo appliqué |
|---|---|
| Message d'accueil | oui — insertion + cultures de saison |
| Question météo explicite | oui — la météo **est** la réponse |
| Conseil agricole | non — le conseil de phase culturale s'applique seul |

Ce ciblage est un choix d'économie cognitive : un agriculteur qui demande comment
conserver son maïs n'a pas besoin d'entendre la température. La météo est
délivrée quand elle porte une information actionnable.

Pour une question météo explicite, le système distingue en outre **deux horizons
temporels** — aujourd'hui ou demain — et bascule vers la prévision lorsque la
question porte sur le lendemain.

---

## 8. Dégradation maîtrisée

Chaque phase prévoit son mode dégradé, et aucune ne peut interrompre la réponse
à l'agriculteur.

| Phase | Mode dégradé |
|---|---|
| Normalisation | donnée absente → message générique de vigilance |
| Cache | vide → appel direct au fournisseur |
| Classification | condition par défaut toujours vraie — jamais d'absence de verdict |
| Contextualisation | zone inconnue → zone par défaut ; échec de calendrier → conseil omis |
| Composition | emplacements non renseignés nettoyés avant restitution |

Le principe est constant : **dégrader l'enrichissement, jamais la réponse.**
L'agriculteur reçoit toujours un message.

---

## 9. Propriétés du traitement

| Propriété | Conséquence |
|---|---|
| **Déterministe** | à données identiques, sortie identique — conseil reproductible et auditable |
| **Explicable** | chaque conseil se remonte à une règle nommée et à un seuil chiffré |
| **Sans génération** | aucun texte n'est inventé ; le système sélectionne et assemble |
| **Extensible par déclaration** | ajouter une condition, une zone ou un calendrier est une entrée de données, pas une modification de logique |
| **Testable** | 23 tests automatisés couvrent les conditions, les seuils et les modes dégradés |

Ces propriétés sont directement liées au domaine : un conseil agricole erroné a
des conséquences matérielles pour l'exploitant. Un système déterministe et
explicable permet d'identifier exactement quelle règle a produit quel conseil, et
de le corriger à la source.

---

## 10. Synthèse

```
RECU        5 mesures numeriques + code de condition

PHASE 1     normalisation vers un format pivot stable
            + libelle de condition, ville, region

PHASE 2     mise en cache 15 min, mutualisee par zone

PHASE 3     classification deterministe
            regime exclusif   -> 1 condition parmi 6   (conversationnel)
            regime cumulable  -> 3 axes independants   (applicatif)

PHASE 4     contextualisation par croisement de 5 referentiels
            59 villes / 32 regions / 4 zones / 13 calendriers / 9 phases

PHASE 5     composition par insertion situee

RESTITUE    un message d'action, contextualise par lieu, saison et culture
```

---

## 11. Journal

| Date | Ajout |
|---|---|
| 2026-09-11 | Création — les cinq phases de traitement, les deux régimes de décision, les référentiels croisés |

---

## Références techniques

- `app/services/weather.py` — normalisation, cache, régime cumulable
- `app/services/weather_conditions.py` — régime exclusif, table de décision
- `app/data/zones_agricoles.py` — rattachement agro-climatique
- `app/data/calendrier_agricole.py` — calendriers et phases culturales
- `app/services/chat/meteo_injector.py` — composition et insertion
