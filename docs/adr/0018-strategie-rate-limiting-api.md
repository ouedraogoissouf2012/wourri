# ADR-0018 — Stratégie de rate limiting de l'API

**Statut** : accepté
**Date** : 2026-07-29 (proposé) / 2026-08-14 (accepté)
**Auteur(s)** : Claude (assistant) sous direction de Ouedraogo Issouf
**Valideur** : Ouedraogo Issouf (réponses stratégiques Q1-Q3 du 2026-07-29 +
mandat d'orchestration du lot sécurité F2, 2026-08-14)

---

## Contexte

Le rate limiting de l'API FastAPI est aujourd'hui incohérent et porte une
faille latente. État factuel **revérifié** dans le code (`origin/APIPy`,
commit `d9abf14`, 2026-08-14 — le compte a encore dérivé depuis la rédaction
initiale, cf. Historique) :

- **20 décorateurs `@limiter.limit("10/minute")` en dur** sur 8 routers
  (mesuré par grep — l'issue #307 annonçait « 21 », la version initiale de
  cet ADR « 19 ») : `asr.py` ×2, `chat.py` ×2, `feedback.py` ×2, `rag.py` ×4,
  `stt.py` ×1, `tts.py` ×7, `weather.py` ×2. **Aucune** valeur distincte :
  tout à `10/minute`.
- `config.py` ne déclare **plus aucun** setting `rate_limit`, et
  `security.py:21` construit `Limiter(key_func=get_remote_address,
  default_limits=["10/minute"])` **en dur**. La « config morte »
  (`rate_limit = "120/minute"` + exemption loopback) décrite par l'issue #307
  a été retirée entre-temps plutôt que réparée : il n'existe aujourd'hui
  **aucun** moyen de configurer la limite, et **aucune** exemption — le
  whatsapp-server (IP conteneur `172.x`) est throttlé à 10/min comme
  n'importe quel client. Un vocal = 2 appels backend → ~5 vocaux/min max
  par utilisateur... pour TOUT le trafic agrégé du bot (une seule IP source).
- **Faille latente X-Forwarded-For** : `Dockerfile.prod:205` lance uvicorn
  avec `--proxy-headers` sans `--forwarded-allow-ips` explicite. Vérifié sur
  uvicorn 0.27.0 (version pinnée) : le défaut est `127.0.0.1` (sûr
  aujourd'hui — l'IP conteneur du client n'est pas loopback, donc les
  en-têtes forgés sont ignorés), mais surchargable par l'env
  `FORWARDED_ALLOW_IPS`. Le jour où un reverse proxy est ajouté (Sprint J
  #202) avec une valeur trop large (`*`), un attaquant forgeant
  `X-Forwarded-For` ferait tourner la clé de rate limiting sur des IP
  arbitraires → bypass par rotation d'IP fictives. À verrouiller AVANT le
  proxy.

**Pourquoi maintenant** : la revue Senior 2026-07-21 a révélé que le fix
« rate limit configurable » était en grande partie mort (issue #307, CRITIQUE).
Cause racine assumée : fix appliqué sans lire les 19 décorateurs
(violation `investigate_before_answering`). Aligné sur `constraints.md`
(pas de code mort, sécurité par défaut) et `docs/vision.md` (trafic issu du
whatsapp-server unique).

## Questions posées avant la décision

1. Granularité du rate limiting (global unique vs par groupe de routes) ?
2. Comment exempter le trafic légitime (whatsapp-server) de façon sûre ?
3. Horizon du reverse proxy (Sprint J #202) — la faille proxy est-elle active ?

Réponses obtenues (Ruben, 2026-07-29) :

- **Q1 → Global unique configurable.** Une seule limite pour toute l'API,
  pilotée par `RATE_LIMIT` du `.env`. Simplicité prioritaire.
- **Q2 → Exemption par clé API interne (X-API-Key).** Robuste, indépendant
  de l'IP et du proxy.
- **Q3 → Pas encore de proxy.** La faille X-Forwarded-For est latente
  (pas exploitable aujourd'hui) mais doit être corrigée avant l'ajout du proxy.

**Fait vérifié pendant la découverte** : le mécanisme X-API-Key existe déjà de
bout en bout. Le whatsapp-server envoie `X-API-Key: WOURI_API_KEY`
(`app-baileys.js:59`, propagé via `authHeaders`) et l'API le valide via
`require_api_key` (`security.py:49`, contre `API_SECRET_KEY` + rotation
`API_SECRET_KEY_PREVIOUS`). L'exemption par clé API ne demande donc aucun
nouveau plumbing.

## Options étudiées

### Option A — Global unique configurable + exemption par clé API *(alignée sur les réponses)*

- **Description** : supprimer les 19 décorateurs `@limiter.limit("10/minute")`.
  Piloter toutes les routes `/api/*` par `default_limits=[settings.rate_limit]`
  (`RATE_LIMIT` du `.env`, défaut prod raisonnable). Exempter le trafic
  authentifié par clé API interne via un `request_filter` slowapi qui retourne
  `True` (skip) quand `X-API-Key` est une clé valide. Fixer
  `--forwarded-allow-ips` dans `Dockerfile.prod` (durcissement proxy futur).
- **Avantages** :
  - `RATE_LIMIT` du `.env` a enfin un **effet réel et mesurable** sur toutes
    les routes (grep `@limiter.limit(` → vide).
  - Exemption indépendante de l'IP → fonctionne identique en local, Docker, prod.
  - Réutilise l'auth X-API-Key existante (P0-02) → **zéro nouveau plumbing**,
    faible surface de risque.
  - Supprime la sentinelle `""` → ferme la faille X-Forwarded-For.
- **Inconvénients** : une seule limite globale → un endpoint léger (TTS court)
  et un endpoint lourd (ASR) partagent le même plafond. Acceptable vu Q1.
- **Coût** : faible. ~1 j : retrait 19 décorateurs, `request_filter`, tests,
  `.env.example`, 1 ligne Dockerfile.prod.
- **Compatibilité** : conforme `constraints.md` (pas de code mort, sécurité
  par défaut). S'appuie sur ADR-0012 (sécurité whatsapp-server) pour la clé.

### Option B — Limites par groupe de routes + exemption par sous-réseau

- **Description** : `ASR_RATE_LIMIT`, `CHAT_RATE_LIMIT`, `TTS_RATE_LIMIT`…
  configurables par famille. Exemption par plage IP de confiance
  (`ipaddress.ip_network` du réseau Docker) + `--forwarded-allow-ips`.
- **Avantages** : granularité fine reflétant le coût réel de chaque endpoint.
  Pas de dépendance à la clé API (utile si un jour du trafic non authentifié
  légitime existe).
- **Inconvénients** : plus de config à maintenir ; exemption dépend de la
  topologie réseau (fragile si l'IP Docker change) ; ne réutilise pas l'auth
  existante. Rejeté sur Q1 (global voulu) et Q2 (clé API voulue).
- **Coût** : moyen. ~2 j (plus de surface de test, gestion des sous-réseaux).
- **Compatibilité** : ok mais surdimensionné pour le besoin actuel.

### Option C — Retirer le rate limiting

- **Description** : supprimer slowapi entièrement, s'appuyer sur le reverse
  proxy (Sprint J) pour le throttling.
- **Avantages** : zéro code applicatif de rate limiting.
- **Inconvénients** : aucune protection tant que le proxy n'existe pas (Q3 :
  pas encore de proxy) → régression de sécurité immédiate. Déplace un souci
  sécurité applicatif vers de l'infra non encore en place.
- **Coût** : faible en code, **élevé en risque**.
- **Compatibilité** : viole `constraints.md` (sécurité par défaut).

### Comparatif

| Critère | A (global + clé API) | B (par groupe + sous-réseau) | C (suppression) |
|---|---|---|---|
| `RATE_LIMIT` effectif | ✅ oui | ✅ oui (par groupe) | n/a |
| Exemption robuste (proxy-safe) | ✅ clé API | ⚠️ dépend IP/topologie | n/a |
| Ferme faille X-Forwarded-For | ✅ | ✅ | ✅ (plus de rate limit) |
| Réutilise l'existant | ✅ auth P0-02 | ❌ | — |
| Complexité config | faible | moyenne | nulle |
| Protection sans proxy | ✅ | ✅ | ❌ |
| Coût dev | ~1 j | ~2 j | ~0.5 j |
| Aligné réponses Ruben | ✅ Q1+Q2+Q3 | ❌ | ❌ |

## Décision

**Option retenue** : **A — Rate limiting global unique configurable + exemption
par clé API interne** (validée : réponses Q1-Q3 de Ruben 2026-07-29 + mandat
lot sécurité F2 2026-08-14).

**Ajustement d'implémentation constaté pendant la réalisation** : le
`request_filter` slowapi envisagé n'existe qu'en interne
(`Limiter._request_filters`) et ses callbacks ne reçoivent **pas** la requête
(`fn()` sans argument, vérifié dans slowapi 0.1.9 installé) — inutilisable pour
inspecter `X-API-Key`. L'exemption est donc réalisée par un **middleware ASGI
maison** (`app/middleware/rate_limit.py`) qui court-circuite le
`SlowAPIASGIMiddleware` quand la clé API est valide (comparaison
`secrets.compare_digest`, clé courante OU précédente — fenêtre de rotation
#222). Même effet, même surface : zéro sentinelle, exemption cryptographique
insensible aux en-têtes forgés.

**Justification** : elle répond exactement aux 3 réponses stratégiques (global,
clé API, faille latente à fermer), réutilise l'auth X-API-Key déjà déployée
(donc surface de risque minimale et pas de nouveau plumbing vérifié dans le
code), et ferme la faille X-Forwarded-For en supprimant la sentinelle `""`.
La granularité par route (Option B) pourra faire l'objet d'un ADR ultérieur si
le besoin de plafonds différenciés émerge — non prématuré aujourd'hui.

## Conséquences

- **Positives** : `RATE_LIMIT` du `.env` pilote réellement l'API ; exemption
  fiable en tout environnement ; faille de bypass fermée ; code mort supprimé.
- **Négatives assumées** : un seul plafond pour des endpoints de coûts
  différents (accepté). L'exemption dépend de la bonne configuration de
  `API_SECRET_KEY` (déjà obligatoire en prod via ADR-0012).
- **Migration / travail induit** :
  1. Retirer les **20** `@limiter.limit("10/minute")` (8 routers).
  2. `config.py` : ajouter `rate_limit` (défaut `120/minute`) ; `security.py` :
     `Limiter(default_limits=[settings.rate_limit])` + validation fail-fast du
     format au démarrage (`limits.parse_many`) + `is_valid_api_key()` en
     comparaison constante (`secrets.compare_digest`).
  3. `app/middleware/rate_limit.py` : middleware ASGI d'exemption par clé API
     (cf. §Décision — ajustement) ; `main.py` : câblage + `@limiter.exempt`
     sur `/health` (sonde Docker).
  4. `Dockerfile.prod` : documenter `--proxy-headers` + `FORWARDED_ALLOW_IPS`
     (défaut uvicorn `127.0.0.1` vérifié = pas de trust par défaut) ; compose :
     passthrough `FORWARDED_ALLOW_IPS` explicite, à renseigner au Sprint J.
  5. `.env.example` + `.env.prod.template` : documenter `RATE_LIMIT`.
  6. Tests : `RATE_LIMIT` effectif (429 au-delà) ; clé API valide non
     limitée ; clé invalide/absente limitée ; pas de bypass via
     `X-Forwarded-For` ; garde-fou « aucun `@limiter.limit` dans les
     routers » ; format `RATE_LIMIT` invalide → refus au démarrage.
  - **Rollback** : réversible (réintroduire les décorateurs). Aucune migration
    de données.
- **Périmètre et hypothèses (vérifiés en revue adversariale 2026-08-14)** :
  - Le rate limiting couvre les **routes déclarées** uniquement : le mount
    `/static` (dont les audios TTS), les 404 et les 405 sont hors périmètre
    (slowapi exempte tout scope sans handler de route). Le throttling du
    statique/du scan de chemins relève du reverse proxy **Sprint J #202** —
    limitation assumée, à couvrir là-bas.
  - Les **429 ne traversent pas** `AdminMetricsMiddleware` (le rejet est
    volontairement le plus externe → coût minimal sous attaque). Conséquence :
    une attaque throttlée est invisible du dashboard ADR-0017 ; un compteur
    de 429 pourra être ajouté plus tard si le besoin d'observabilité émerge.
    Protection d'abord, métrique ensuite — choix explicite.
  - Hypothèse : uvicorn sert en TCP → `request.client` est toujours renseigné.
    En cas de passage à un socket Unix (option possible avec le proxy
    Sprint J), `get_remote_address` renverrait `127.0.0.1` pour TOUT le
    trafic (un seul compteur mondial) → à réévaluer à ce moment-là.
  - Le fail-fast `RATE_LIMIT` invalide se manifeste, avec uvicorn 0.27
    `--workers 2`, par des workers morts + un parent vivant (pas de
    supervision des workers avant uvicorn 0.30) : le conteneur passe
    `unhealthy` via le healthcheck plutôt que de crasher franchement. Même
    comportement que le garde `API_SECRET_KEY` préexistant — dette tracée :
    upgrade uvicorn ≥ 0.30.
  - slowapi 0.1.9 : son middleware ASGI casse le protocole sur les réponses
    **multi-chunks** (réémission de `http.response.start`). Aucune route
    limitée ne streame aujourd'hui — ne pas ajouter de
    FileResponse/StreamingResponse sur une route limitée sans traiter ce
    point (pin slowapi==0.1.9).
  - `/api/health/memory` reste **limité** (contrairement à `/health`,
    exempté pour la sonde Docker) : la route expose des infos process sans
    authentification — la limite globale est sa seule protection. Un scraper
    Prometheus futur devra soit s'authentifier (exemption), soit compter
    dans le budget de son IP. Choix assumé.
- **Verrous futurs** : passer plus tard à des limites par groupe (Option B)
  restera possible mais demandera de réintroduire de la config par famille.

## Références

- Issue #307 (CRITIQUE) — https://github.com/ouedraogoissouf2012/wourri/issues/307
- Code vérifié : `app/security.py`, `app/config.py`, 8 routers, `Dockerfile.prod`
- whatsapp-server : `app-baileys.js:56-64` (envoi X-API-Key)
- ADR-0012 (sécurité whatsapp-server, clé API obligatoire en prod)
- slowapi : override de `default_limits` par décorateur explicite ;
  `request_filter` pour exempter des requêtes
- Sprint J #202 (reverse proxy — horizon proxy)

## Historique

- 2026-07-29 — rédaction initiale (statut proposé), après questions
  stratégiques à Ruben. Décision Option A en attente de validation explicite.
- 2026-08-14 — **accepté** (lot sécurité F2, issue #307) et versionné dans le
  repo (le fichier vivait hors git). Contexte revérifié sur `d9abf14` :
  20 décorateurs (et plus 19), et la « config morte » a été retirée
  entre-temps (plus de setting `rate_limit` ni d'exemption du tout — le
  whatsapp-server est throttlé à 10/min agrégés). Ajustement d'implémentation :
  exemption par middleware ASGI maison (le `request_filter` slowapi ne reçoit
  pas la requête — vérifié dans slowapi 0.1.9). Faille XFF requalifiée :
  uvicorn 0.27 a un défaut sûr (`127.0.0.1`) ; le risque réel est une
  future config proxy trop large → verrouillage documenté avant Sprint J.
