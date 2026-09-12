# Contrat API Open-Meteo — transmission des données

> **Objet** : décrire exactement ce que Wourri **émet** vers son fournisseur de
> données météorologiques et ce que celui-ci lui **renvoie** — la couche de
> transmission, au niveau du protocole et de la charge utile.
>
> **Périmètre** : strictement la transmission. La transformation de ces données
> en conseil agricole vocal fait l'objet d'une documentation distincte.
>
> **Mesuré le** : 2026-09-11 à 09:45 UTC · ville de référence : Bouaké
> **Code de référence** : `app/services/weather.py` @ `03796ea`

---

## Niveau de vérification

Chaque affirmation de ce document porte sa source.

| Marque | Signification |
|---|---|
| **[MESURÉ]** | Capturé lors d'un appel réel, daté, reproductible |
| **[CODE]** | Établi par lecture du code source, référence `fichier:ligne` |

---

## 1. Ce que Wourri émet

### 1.1 Caractéristiques du transport — [CODE]

| Propriété | Valeur | Source |
|---|---|---|
| Méthode | `GET` | `weather.py:116` |
| Client | `httpx.AsyncClient` (asynchrone) | `weather.py:115` |
| Timeout | **5 s** (les deux requêtes) | `weather.py:115`, `weather.py:181` |
| Authentification | aucune — service ouvert | — |
| En-têtes personnalisés | aucun | — |
| Transmission des paramètres | query string | `client.get(url, params=params)` |
| URL de base | `https://api.open-meteo.com/v1` | `config.py:46` |

L'absence d'authentification est une propriété du fournisseur retenu, ouvert et
gratuit pour cet usage. Elle simplifie l'exploitation : aucun secret à provisionner,
à faire tourner ni à surveiller sur cette intégration.

### 1.2 Requête « météo actuelle » — [CODE] `weather.py:106-112`

```python
url = f"{settings.openmeteo_base_url}/forecast"
params = {
    "latitude":  city["lat"],
    "longitude": city["lon"],
    "current":   "temperature_2m,relative_humidity_2m,precipitation,weather_code,wind_speed_10m",
    "timezone":  "Africa/Abidjan",
}
```

URL effective émise sur le réseau :

```
GET https://api.open-meteo.com/v1/forecast
    ?latitude=7.6833
    &longitude=-5.0331
    &current=temperature_2m%2Crelative_humidity_2m%2Cprecipitation%2Cweather_code%2Cwind_speed_10m
    &timezone=Africa%2FAbidjan
```

### 1.3 Requête « prévision » — [CODE] `weather.py:167-174`

```python
params = {
    "latitude":      city["lat"],
    "longitude":     city["lon"],
    "daily":         "precipitation_probability_max,precipitation_sum,weather_code,"
                     "temperature_2m_max,temperature_2m_min",
    "timezone":      "Africa/Abidjan",
    "forecast_days": 2,
}
```

URL effective :

```
GET https://api.open-meteo.com/v1/forecast
    ?latitude=7.6833
    &longitude=-5.0331
    &daily=precipitation_probability_max%2Cprecipitation_sum%2Cweather_code%2Ctemperature_2m_max%2Ctemperature_2m_min
    &timezone=Africa%2FAbidjan
    &forecast_days=2
```

### 1.4 Encodage des paramètres

- Les variables demandées forment **une seule chaîne séparée par des virgules** ;
  le client encode chaque `,` en `%2C`.
- `timezone` est un identifiant **IANA** ; le `/` est encodé `%2F`.
- Les coordonnées sont transmises en décimal, telles qu'elles figurent dans le
  référentiel de villes.

---

## 2. Les choix d'ingénierie de la requête

La requête n'est pas un appel générique. Chaque paramètre répond à une contrainte
du terrain : connectivité limitée, latence perçue par un agriculteur sur WhatsApp,
et justesse du cadre temporel ivoirien.

### 2.1 Sélection stricte des variables — sobriété réseau

Le fournisseur expose un catalogue étendu de variables météorologiques.
**Wourri en demande cinq**, exactement celles que son moteur de décision exploite.
La charge utile reçue tient en moins de 600 octets.

Pour un service destiné à des zones à faible couverture data, cette sobriété
n'est pas un détail : elle conditionne la tenue du service en conditions dégradées.

### 2.2 Fenêtre de prévision réduite au besoin réel — [MESURÉ]

Mesure du 2026-09-11 :

```
sans forecast_days   ->  7 jours renvoyes  (2026-09-11 au 2026-09-17)
avec forecast_days=2 ->  2 jours renvoyes
```

Wourri fixe explicitement `forecast_days=2` et **évite ainsi le téléchargement de
5 jours de données inutilisées à chaque appel** — soit environ 70 % du volume de
prévision par défaut.

### 2.3 Fuseau horaire local explicite — justesse agronomique

`timezone=Africa/Abidjan` est transmis à chaque requête plutôt que de laisser le
défaut UTC.

Ce choix est déterminant pour le bloc `daily` : les bornes de journée renvoyées
correspondent aux **journées réelles de l'agriculteur ivoirien**, pas à des
journées UTC décalées. Un cumul de pluie « du 11 septembre » désigne bien la
journée telle qu'elle est vécue sur le terrain.

### 2.4 Deux requêtes distinctes plutôt qu'une requête combinée

L'API accepterait `current=` et `daily=` dans un même appel. Wourri les sépare
délibérément, ce qui permet **deux caches indépendants** :

- la météo instantanée et la prévision n'ont pas le même rythme de péremption ;
- consulter la prévision n'invalide pas la météo courante, et réciproquement ;
- une indisponibilité sur l'un des deux blocs ne prive pas l'autre.

### 2.5 Cache aligné sur la cadence réelle du modèle

La réponse déclare `interval: 900` — le fournisseur rafraîchit au quart d'heure.
Le cache de Wourri est fixé à **15 minutes** : exactement la granularité utile.
Plus court, il multiplierait les appels sans gagner en fraîcheur ; plus long, il
servirait une donnée périmée.

### 2.6 Coordonnées résolues localement — une requête au lieu de deux

Les coordonnées proviennent d'un référentiel interne de **59 villes de Côte
d'Ivoire**, avec leur région administrative (`app/data/cities.py`). Aucun appel
de géocodage n'est nécessaire.

Trois bénéfices : un aller-retour réseau économisé par requête, une latence
réduite, et un référentiel maîtrisé — les villes servies sont celles qui ont été
validées, sans dépendance à un service tiers de géocodage.

### 2.7 Timeout court — la réactivité prime

5 secondes, là où la valeur par défaut d'un client HTTP se compte en dizaines de
secondes. Le service fait le choix explicite de **répondre vite, quitte à répondre
sans météo**, plutôt que de laisser un agriculteur attendre devant WhatsApp.

### 2.8 Distinction explicite entre quantité et probabilité

La requête de prévision demande **à la fois** `precipitation_sum` (millimètres)
et `precipitation_probability_max` (pourcentage). Ce sont deux grandeurs
différentes, aux noms voisins, fréquemment confondues dans les intégrations
météo.

Wourri les traite séparément, le code documente la distinction, et un test
automatisé verrouille ce comportement
(`test_build_prevision_precip_mm_pilote_grosse_pluie_pas_la_proba`).

---

## 3. Ce que l'API renvoie

### 3.1 En-têtes HTTP — [MESURÉ]

```
HTTP/1.1 200 OK
Date: Fri, 11 Sep 2026 09:55:16 GMT
Content-Type: application/json; charset=utf-8
Transfer-Encoding: chunked
Connection: keep-alive
```

- Réponse en `chunked`, sans `Content-Length`.
- **`charset=utf-8` déclaré** — les unités contiennent `°C`, caractère non-ASCII.
  Le décodage est pris en charge nativement par le client HTTP.

### 3.2 Réponse intégrale — météo actuelle — [MESURÉ]

Capturée le 2026-09-11 à 09:45, Bouaké :

```json
{
  "latitude": 7.6977153,
  "longitude": -5.0553284,
  "generationtime_ms": 0.1710653305053711,
  "utc_offset_seconds": 0,
  "timezone": "Africa/Abidjan",
  "timezone_abbreviation": "GMT",
  "elevation": 363.0,
  "current_units": {
    "time": "iso8601",
    "interval": "seconds",
    "temperature_2m": "°C",
    "relative_humidity_2m": "%",
    "precipitation": "mm",
    "weather_code": "wmo code",
    "wind_speed_10m": "km/h"
  },
  "current": {
    "time": "2026-09-11T09:45",
    "interval": 900,
    "temperature_2m": 25.2,
    "relative_humidity_2m": 79,
    "precipitation": 0.0,
    "weather_code": 3,
    "wind_speed_10m": 13.5
  }
}
```

### 3.3 Réponse intégrale — prévision — [MESURÉ]

```json
{
  "latitude": 7.6977153,
  "longitude": -5.0553284,
  "generationtime_ms": 0.6296634674072266,
  "utc_offset_seconds": 0,
  "timezone": "Africa/Abidjan",
  "timezone_abbreviation": "GMT",
  "elevation": 363.0,
  "daily_units": {
    "time": "iso8601",
    "precipitation_probability_max": "%",
    "precipitation_sum": "mm",
    "weather_code": "wmo code",
    "temperature_2m_max": "°C",
    "temperature_2m_min": "°C"
  },
  "daily": {
    "time":                          ["2026-09-11", "2026-09-12"],
    "precipitation_probability_max": [77,   88  ],
    "precipitation_sum":             [1.7,  4.7 ],
    "weather_code":                  [51,   80  ],
    "temperature_2m_max":            [29.1, 29.3],
    "temperature_2m_min":            [22.6, 22.4]
  }
}
```

---

## 4. La structure de réponse : `current` et `daily`

L'API emploie deux structures distinctes selon l'horizon temporel.

| | `current` | `daily` |
|---|---|---|
| Forme | **objet plat** | **colonnes parallèles** |
| Valeurs | scalaires | tableaux alignés par index |
| Accès | `data["current"]["temperature_2m"]` | `data["daily"]["weather_code"][1]` |
| Longueur | — | déterminée par `forecast_days` |

`daily` n'est pas une liste d'objets-jours : c'est un objet dont chaque clé est un
tableau, tous de même longueur, l'index correspondant à la position dans `time[]` :

```
index :        0              1
time  : "2026-09-11"   "2026-09-12"
        aujourd'hui       demain
```

C'est une structure **colonnaire**, efficace pour les séries temporelles : elle
évite de répéter les noms de champs pour chaque jour et réduit d'autant la charge
utile.

Wourri y accède par index (`weather.py:186-194`) et protège cet accès par une
garde explicite `if len(times) < 2: return None` (`weather.py:187`) — la
structure est vérifiée avant d'être lue, plutôt que de supposer sa forme.

---

## 5. L'enveloppe de réponse — un contrat auto-descriptif

Chaque réponse est accompagnée de 7 champs de contexte. **C'est le principe d'une
API scientifique auto-descriptive** : la réponse ne livre pas seulement des
valeurs, elle documente les conditions dans lesquelles elles ont été produites.

| Champ | Type | Valeur reçue | Rôle dans le contrat |
|---|---|---|---|
| `latitude` / `longitude` | float | `7.6977153` / `-5.0553284` | Point de grille effectivement servi |
| `elevation` | float | `363.0` | Altitude du point — contextualise la température |
| `timezone` | str | `"Africa/Abidjan"` | Confirme que le fuseau demandé a été honoré |
| `timezone_abbreviation` | str | `"GMT"` | Abréviation correspondante |
| `utc_offset_seconds` | int | `0` | Décalage appliqué aux horodatages |
| `generationtime_ms` | float | `0.171` | Temps de calcul côté serveur |
| `current_units` / `daily_units` | objet | bloc complet | Unité déclarée de chaque variable |

### 5.1 Le recalage sur la grille : le fonctionnement attendu d'un modèle numérique

On envoie `7.6833 / -5.0331`, l'API répond `7.6977 / -5.0553`.

**C'est le comportement normal, et c'est une marque de transparence du
fournisseur.** Un modèle météorologique numérique ne calcule pas en tout point du
globe : il calcule sur une grille régulière. Toute requête est servie par le nœud
de grille le plus proche, et en renvoyant ses coordonnées réelles, l'API indique
explicitement quel point a produit la mesure.

L'écart mesuré ici est d'environ 2,5 km, à 363 m d'altitude. À cette échelle, dans
une zone agro-climatique homogène comme le centre ivoirien, la différence est sans
portée agronomique : les phénomènes exploités par Wourri — pluie, orage,
température, humidité — ont une extension spatiale très supérieure.

### 5.2 Un contrat figé côté Wourri

Wourri s'appuie sur un contrat établi à la conception : les unités de chaque
variable sont connues et stables, et le code les traite comme telles sans relire
le bloc `*_units` à chaque appel. C'est un choix cohérent — relire une déclaration
invariante à chaque requête coûterait du traitement sans bénéfice opérationnel.

L'enveloppe reste une **ressource disponible** pour renforcer la traçabilité au
fil des évolutions :

- `latitude` / `longitude` / `elevation` — journalisés une fois par ville au
  démarrage, ils documenteraient le point de grille servi pour chacune des 59 villes ;
- `*_units` — vérifiés une fois au démarrage, ils transformeraient une convention
  implicite en contrôle explicite du contrat fournisseur ;
- `generationtime_ms` — agrégé, il alimenterait le tableau de bord d'observabilité.

Ce sont des enrichissements d'outillage, pas des prérequis : le service est
pleinement fonctionnel sans eux.

---

## 6. Les variables reçues, en détail

### 6.1 Bloc `current` — 5 variables + 2 champs de contexte

| Clé | Type | Unité déclarée | Exemple reçu | Signification |
|---|---|---|---|---|
| `time` | str | `iso8601` | `"2026-09-11T09:45"` | horodatage de la mesure, arrondi au quart d'heure |
| `interval` | int | `seconds` | `900` | fenêtre de la mesure : 15 minutes |
| `temperature_2m` | float | `°C` | `25.2` | température à 2 m du sol |
| `relative_humidity_2m` | int | `%` | `79` | humidité relative à 2 m |
| `precipitation` | float | `mm` | `0.0` | précipitations sur la fenêtre |
| `weather_code` | int | `wmo code` | `3` | condition, code WMO |
| `wind_speed_10m` | float | `km/h` | `13.5` | vent à 10 m du sol |

### 6.2 Bloc `daily` — 5 variables + l'axe temporel

| Clé | Type | Unité déclarée | Exemple reçu | Signification |
|---|---|---|---|---|
| `time` | str[] | `iso8601` | `["2026-09-11","2026-09-12"]` | axe des jours — sert d'index |
| `precipitation_probability_max` | int[] | `%` | `[77, 88]` | **probabilité** maximale de pluie |
| `precipitation_sum` | float[] | `mm` | `[1.7, 4.7]` | **cumul** de pluie sur la journée |
| `weather_code` | int[] | `wmo code` | `[51, 80]` | condition dominante du jour |
| `temperature_2m_max` | float[] | `°C` | `[29.1, 29.3]` | température maximale |
| `temperature_2m_min` | float[] | `°C` | `[22.6, 22.4]` | température minimale |

### 6.3 Deux grandeurs de précipitation, deux fenêtres

| Champ | Bloc | Fenêtre temporelle |
|---|---|---|
| `precipitation` | `current` | **15 minutes** (`interval: 900`) |
| `precipitation_sum` | `daily` | **24 heures** |

Les deux s'expriment en millimètres et portent des noms voisins, mais ne décrivent
pas le même phénomène. Cette distinction est explicitement portée par le code et
verrouillée par les tests automatisés.

---

## 7. Codes WMO reçus

`weather_code` est un entier du référentiel de l'Organisation météorologique
mondiale. Wourri maintient une table de correspondance de **18 codes** vers un
libellé français (`weather.py:69`) — [CODE] :

```
0, 1, 2, 3, 45, 48, 51, 53, 55, 61, 63, 65, 80, 81, 82, 95, 96, 99
```

La table couvre l'intégralité des conditions observables en Côte d'Ivoire : ciel
clair, nuages, brouillard, bruine, pluie, averses, orages. Les familles neige et
verglas sont volontairement absentes du périmètre.

Tout code hors table produit le libellé neutre `"Inconnu"` — la lecture ne peut
pas échouer sur une valeur inattendue.

Codes effectivement reçus pendant les mesures de cette session :
`3` (Couvert), `51` (Bruine légère), `80` (Averses légères), `95` (Orage).

---

## 8. Ce que Wourri retient de la réponse

La donnée reçue est normalisée vers un format interne stable, indépendant du
fournisseur (`weather.py:126-140` et `weather.py:196-207`).

### 8.1 Météo actuelle

| Reçu | Retenu | Nom interne |
|---|:---:|---|
| `current.temperature_2m` | oui | `temperature` |
| `current.relative_humidity_2m` | oui | `humidity` |
| `current.precipitation` | oui | `precipitation` |
| `current.weather_code` | oui | `weather_code` |
| `current.wind_speed_10m` | oui | `wind_speed` |

Wourri **enrichit** ensuite cette base avec ses propres sources : `city` et
`region` depuis son référentiel de villes, `weather_description` par traduction du
code WMO, et `advice` par application de ses règles agronomiques.

Cette normalisation isole le reste de l'application du format du fournisseur :
un changement de source météo n'impacterait que ce point de conversion.

### 8.2 Prévision

| Reçu | Retenu | Nom interne |
|---|:---:|---|
| `daily.time[1]` | oui | `date` |
| `daily.temperature_2m_max[1]` | oui | `temperature_max` |
| `daily.temperature_2m_min[1]` | oui | `temperature_min` |
| `daily.precipitation_probability_max[1]` | oui | `precipitation_probability` |
| `daily.precipitation_sum[1]` | oui | `precipitation_mm` |
| `daily.weather_code[1]` | oui | `weather_code` |

L'index `[1]` correspond au lendemain, horizon de la fonction de prévision.
L'index `[0]` — l'agrégat de la journée en cours — est présent dans la même
réponse : il constitue une **ressource déjà disponible** pour un enrichissement
futur du conseil, sans appel réseau supplémentaire.

---

## 9. Stratégie de dégradation

Le service privilégie la réactivité et la continuité : une donnée météo
indisponible ne bloque jamais la réponse à l'agriculteur.

| Situation | Comportement | Source |
|---|---|---|
| Ville hors référentiel | aucune requête émise — économie d'un appel inutile | `weather.py:102` |
| Réponse non conforme | retour neutre, la requête se poursuit | `weather.py:119`, `weather.py:181` |
| Dépassement du délai de 5 s | journalisé, retour neutre | `weather.py:146`, `weather.py:214` |
| Structure de prévision incomplète | garde de forme, retour neutre | `weather.py:187` |

Dans tous les cas, la chaîne conversationnelle continue et l'agriculteur reçoit
une réponse. Le parti pris est assumé : **répondre sans météo plutôt que faire
attendre**, cohérent avec un usage sur réseau mobile en zone rurale.

---

## 10. Synthèse du contrat

```
EMIS      GET, service ouvert, 4 a 5 parametres cibles en query string
          5 variables demandees, fenetre de prevision reduite a 2 jours
          fuseau local explicite, timeout 5 s

RECU      HTTP 200, application/json; charset=utf-8
          7 champs de contexte   (tracabilite, unites, fuseau)
          1 bloc d'unites        (contrat auto-descriptif)
          1 bloc de donnees      current = objet plat
                                 daily   = structure colonnaire indexee

RETENU    normalisation vers un format interne stable,
          enrichi par les referentiels Wourri (ville, region, libelle, conseil)
```

---

## 11. Journal

| Date | Ajout |
|---|---|
| 2026-09-11 | Création — requête émise, choix d'ingénierie, réponse reçue, structure, normalisation |

> **Règle** : toute mesure ajoutée ici est une capture réelle, datée, avec sa
> ville et son heure. Une valeur reprise d'une documentation externe n'est jamais
> présentée comme mesurée.

---

## Références techniques

- `app/services/weather.py` — émission, réception, normalisation
- `app/data/cities.py` — référentiel des 59 villes et de leurs coordonnées
- `app/services/weather_conditions.py` — table de correspondance des conditions
