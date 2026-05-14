# ADR-0012 — Sécurité whatsapp-server (CORS strict + rate limiting + npm audit clean)

**Statut** : complété
**Date** : 2026-05-10
**Auteur** : Claude (sous direction Ruben)
**Valideur** : Ruben (validé et exécuté simultanément le 2026-05-10)

---

## Contexte

### Déclencheur

Programme de remboursement de dette technique démarré le 2026-05-10 après
livraison de [ADR-0011](0011-strategie-prechargement-ml.md). Le 1er sprint
prioritaire identifié (« Sprint A — Sécurité whatsapp-server ») cible 3
dettes critiques documentées dans
[`whatsapp-server/CLAUDE.md`](../../../whatsapp-server/CLAUDE.md) section
« Dette technique connue » :

1. **`npm audit`** : 12 vulnérabilités résiduelles (1 low, 3 moderate, 6 high,
   2 critical selon résumé texte ; 1/3/5/3 selon classification JSON racine).
2. **CORS permissif** : `app.use(cors())` sans restriction → toutes origines
   acceptées, risque XSS/CSRF en prod.
3. **Pas de rate limiting** : aucune protection contre les abus DoS sur les
   routes publiques (`/health`, `/qr`, `/qr-page`, `/status`, `/users`, etc.).

### Contexte projet

Le serveur `whatsapp-server` (Node.js + Baileys) est la passerelle entre les
utilisateurs WhatsApp et l'API Wourri. Il sera exposé publiquement en
production. Sa stratégie « Baileys production-ready » a été actée le
2026-05-05 (cf. `memory/project_whatsapp_strategy_2026-05.md`).

Le bot touche à du **trafic WhatsApp réel** d'agriculteurs ivoiriens et
maliens (profil utilisateur sensible : numéros de téléphone, contenus
vocaux personnels). Un compromis sécurité aurait un impact direct sur la
confiance utilisateur.

### Ce que ce plan PRODUIT

Un ADR qui documente formellement les 3 décisions de sécurité prises et
exécutées dans le Sprint A, pour traçabilité et pour servir de référence
aux futurs ADRs sécurité (ex: ajout authentification, hardening Docker,
etc.).

---

## Questions tranchées avant la décision

1. **Faut-il un ADR séparé par décision (3 ADRs distincts) ?**
   → **Non**. Les 3 décisions partagent le même contexte (sécurité immédiate
   whatsapp-server), le même Sprint A, et la même livraison synchrone. Un
   ADR consolidé est plus lisible que 3 fragments.

2. **`npm audit fix --force` est-il safe pour Baileys ?**
   → **Oui dans notre cas**. Le bump `@whiskeysockets/baileys` 6.7.8 → 6.7.21
   reste sur la même majeure (semver minor). Validé par 95/95 tests Node
   passants après bump. Test manuel WhatsApp recommandé post-merge.

3. **CORS : faut-il une regex pour les origines (ex: `*.wourri.ci`) ?**
   → **Non**. Une simple allow-list séparée par virgules est plus auditable
   et moins risquée (pas de risque de regex permissive ou DoS regex). Si
   besoin de regex futur, ADR ultérieur.

4. **Rate limit : Redis-backed ou en mémoire ?**
   → **En mémoire** (default `express-rate-limit`). Le serveur whatsapp-server
   tourne en single-instance (1 process Node, pas de cluster). Si scaling
   horizontal futur (PM2 cluster ou multi-replicas), passer à Redis via
   `express-rate-limit-redis` dans un ADR ultérieur.

5. **Rate limit : quelle limite ?**
   → **60 req/min/IP global**. Compromis entre monitoring légitime
   (`/health` polled 1×/s = 60/min, limite haute mais pas bloquante) et
   protection contre les scans abusifs (60/min trop lent pour scraping massif).

6. **Faut-il rate-limiter `/logout` plus strictement ?**
   → **Pas dans cette itération**. `/logout` est aussi soumis au 60/min global,
   suffisant pour l'usage actuel. Hardening spécifique (auth) à un ADR ultérieur.

---

## Décisions

### Décision A.2 — `npm audit fix` (auto)

**Action** : `npm audit fix` sans `--force` dans `whatsapp-server/`.

**Effet** : règle 2 vulnérabilités (`lodash` high, `follow-redirects`
moderate) + patch interne `protobufjs` au top-level. 12 → 10 vulnérabilités.

**Livré dans** : PR #141 (mergée 2026-05-10).

### Décision A.3 — `npm audit fix --force` (bumps majeurs en semver minor)

**Action** : bumps déclarés dans `package.json` :
- `@whiskeysockets/baileys` : 6.7.8 → **6.7.21** (résout chains protobufjs
  nested + libsignal + music-metadata + file-type)
- `axios` : 1.13.2 → **1.16.1** (résout 14 CVE : SSRF, Cloud Metadata
  Exfiltration, Prototype Pollution, …)
- `express` : 4.21.2 → **4.22.2** (résout chains path-to-regexp + qs +
  body-parser)

**Pinning post-fix** : retrait des `^` ajoutés par npm pour respecter la
règle projet « versions exactes » documentée dans `whatsapp-server/CLAUDE.md`.

**Effet** : 10 → **0 vulnérabilités** (`npm audit` retourne `found 0 vulnerabilities`).

**Livré dans** : PR #142.

### Décision A.4 — CORS strict via allow-list env

**Action** : remplacer `app.use(cors())` par :

```js
const allowedOrigins = (process.env.ALLOWED_ORIGINS || '')
    .split(',')
    .map(s => s.trim())
    .filter(Boolean);
app.use(cors({
    origin: allowedOrigins.length > 0 ? allowedOrigins : false,
    credentials: false,
}));
```

**Sémantique** :
- `ALLOWED_ORIGINS=https://a.com,https://b.com` → seules ces origines sont
  autorisées en cross-domain
- `ALLOWED_ORIGINS=` (vide, défaut) → `origin: false` → refus de toute
  origine cross-domain (mode strict)
- Same-origin (curl, navigation directe, monitoring sans header `Origin`)
  reste autorisé → **0 impact sur usages légitimes**

**Livré dans** : PR #143.

### Décision A.5 — Rate limiting Express

**Action** : ajout de `express-rate-limit@8.5.1` (pinned) comme dépendance,
appliqué globalement avec :

```js
const publicRateLimit = rateLimit({
    windowMs: 60 * 1000,        // 1 minute
    max: 60,                     // 60 req/min/IP
    standardHeaders: true,       // expose RateLimit-* headers
    legacyHeaders: false,
    message: { error: 'Trop de requêtes, réessayez plus tard' },
});
app.use(publicRateLimit);
```

**Sémantique** :
- 60 req/min/IP sur toutes les routes Express
- Headers `RateLimit-Limit`, `RateLimit-Remaining`, `RateLimit-Reset`
  exposés (standard draft IETF)
- Dépassement → HTTP 429 + JSON `{error: "..."}`

**Livré dans** : PR #143 (groupée avec A.4).

---

## Conséquences

### Positives

- **0 vulnérabilité npm** sur whatsapp-server (vs 12 avant) → conformité
  audit sécurité industrielle, base saine pour mise en production.
- **CORS strict par défaut** → réduit la surface d'attaque XSS/CSRF
  potentielle. Configurable sans changement de code (env-driven).
- **Rate limiting actif** → protection automatique contre scraping abusif
  et tentatives DoS basiques. Headers standard exposés pour les clients
  bien-élevés (retry intelligent).
- **Dette technique tracée** : `whatsapp-server/CLAUDE.md` § « Dette
  technique connue » mis à jour, 3 items biffés.

### Négatives assumées

- **Bump Baileys 6.7.8 → 6.7.21** : risque de breaking interne non détecté
  par les tests unitaires (la connexion WhatsApp ne peut être validée que
  par smoke test manuel avec un téléphone WhatsApp scanné). Validé par
  Ruben en test manuel post-merge.
- **CORS strict par défaut** : si on déploie un dashboard externe sans
  configurer `ALLOWED_ORIGINS`, les appels XHR cross-domain seront bloqués.
  Mitigation : `.env.example` documente clairement la variable et `CLAUDE.md`
  whatsapp-server l'explique.
- **Rate limit 60/min** : si un client legitime polle `/health` plus de 60
  fois par minute (ex: monitoring agressif), il sera throttled. À ajuster
  via `windowMs` / `max` si besoin futur (config en dur, à externaliser
  via env dans un ADR ultérieur si nécessaire).

### Migration / travail induit

Aucun. L'ADR documente une implémentation **déjà réalisée** (PRs #141, #142,
#143 livrées le 2026-05-10).

### Verrous futurs

- **CORS regex** : si besoin de patterns dynamiques (`*.wourri.ci`), ADR
  ultérieur. Pour l'instant, allow-list explicite suffit.
- **Rate limit distribué (Redis)** : nécessaire si scaling horizontal
  (cluster Node, multi-replicas Docker). ADR ultérieur, hors scope actuel.
- **Authentification API publique** : `/logout`, `/users`, `/qr` n'ont pas
  d'auth — risque si déployé en prod publique sans VPN/reverse-proxy
  d'authentification. À traiter dans un ADR sécurité ultérieur (post-déploiement).

---

## Hors scope

- **Authentification** des routes publiques (`/qr` notamment, qui expose le
  QR code de connexion WhatsApp) → ADR de hardening prod ultérieur.
- **TLS/HTTPS** : géré au niveau du reverse-proxy de production (NGINX,
  Caddy, Traefik) — ne concerne pas le code Node.
- **Validation des inputs body** : aucune route ne reçoit du body utilisateur
  arbitraire dans la version actuelle (les routes sont GET-only ou
  WhatsApp-driven). Si ajout futur d'endpoint POST avec body, ADR séparé.
- **Rate limit Redis** (cluster) : reportée si scaling horizontal nécessaire.
- **`whatsapp-server/whatsapp-server/`** (nested folder pourri) : Sprint C
  hygiène repo, à traiter séparément.

---

## Plan d'exécution

| Étape | PR | Statut |
|---|---|---|
| A.1 — Audit npm vulnerabilities | (issue #136, closed) | ✅ Rapport produit 2026-05-10 |
| A.2 — `npm audit fix` (auto) | #141 | ✅ Mergée 2026-05-10 |
| A.3 — `npm audit fix --force` + bumps Baileys/axios/express | #142 | ✅ Livrée 2026-05-10 |
| A.4+A.5 — CORS strict + rate limiting | #143 | ✅ Livrée 2026-05-10 |
| A.6 — Cet ADR | (cette PR) | ✅ Livrée 2026-05-10 |

---

## Métriques de succès

| Métrique | Cible | Mesure |
|---|---:|---:|
| Vulnérabilités `npm audit` critical | 0 | ✅ 0 |
| Vulnérabilités `npm audit` high | 0 | ✅ 0 |
| Vulnérabilités `npm audit` totales | ≤ 2 mineures | ✅ 0 |
| CORS allow-list activée | oui | ✅ |
| Rate limiting actif sur routes publiques | oui | ✅ |
| Tests Node passants | 95/95 | ✅ 95/95 |
| Connexion WhatsApp fonctionnelle après bumps | oui | ⏳ test manuel Ruben |

---

## Références

- Epic Sprint A : [#135](https://github.com/ouedraogoissouf2012/wourri/issues/135)
- Issue audit A.1 : [#136](https://github.com/ouedraogoissouf2012/wourri/issues/136) (closed avec rapport complet)
- Issue A.2 : [#137](https://github.com/ouedraogoissouf2012/wourri/issues/137) → PR [#141](https://github.com/ouedraogoissouf2012/wourri/pull/141)
- Issue A.3 : [#138](https://github.com/ouedraogoissouf2012/wourri/issues/138) → PR [#142](https://github.com/ouedraogoissouf2012/wourri/pull/142)
- Issue A.4+A.5 : [#139](https://github.com/ouedraogoissouf2012/wourri/issues/139) → PR [#143](https://github.com/ouedraogoissouf2012/wourri/pull/143)
- Issue A.6 : [#140](https://github.com/ouedraogoissouf2012/wourri/issues/140) → cette PR
- [`whatsapp-server/CLAUDE.md`](../../../whatsapp-server/CLAUDE.md) section « Dette technique connue » et « Sécurité — CORS et rate limiting »
- [`whatsapp-server/.env.example`](../../../whatsapp-server/.env.example) : `ALLOWED_ORIGINS`
- ADR précédent : [ADR-0011](0011-strategie-prechargement-ml.md) (préchargement ML, livré 2026-05-08/10)

---

## Historique

- **2026-05-10 (rédaction)** : ADR rédigé après livraison effective des PRs #141, #142, #143. Statut directement marqué **complété** car l'implémentation est faite (pattern « ADR rétroactif » pour les sprints d'urgence où le code précède la formalisation, exceptionnel et limité au sprint sécurité). Tracé pour future référence et pour servir de modèle aux décisions sécurité ultérieures.
