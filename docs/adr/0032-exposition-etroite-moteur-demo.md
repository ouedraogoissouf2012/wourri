# ADR-0032 — Exposition étroite du moteur pour la démo Console (L4)

**Statut** : accepté
**Date** : 2026-08-16
**Auteur(s)** : Claude (sous direction Issouf)
**Valideur** : Issouf — accepté 2026-08-16 (« okay » expo étroite)

---

## Contexte

[ADR-0026](0026-deploiement-wourri-dokploy.md) impose **interne only**.
L'issue #411 a été fermée sur cette base.

Le site Console est sur **Vercel (public)**. Le moteur n'a **aucun** label
Traefik. La démo traduction ignore le texte saisi. Sans URL HTTPS + CORS +
clé, le navigateur ne peut pas commander le moteur.

Le collaborateur demande un sous-domaine **protégé**, uniquement les chemins
utiles, pas `/docs` / `/openapi.json` / `/admin/*`.

## Questions

1. Exposer tout le service ou un sous-ensemble ?
2. CORS `*` en prod ?

Réponses : **sous-ensemble** ; CORS = **liste Vercel**, jamais `*`.

## Options

### Option A — Expo étroite (retenue)

Chemins publics possibles (Traefik, hors code) :

- `/api/chat`, `/api/tts`, `/health`, `/static`

Interdits sur Internet :

- `/docs`, `/redoc`, `/openapi.json`, `/admin/*`, `/admin/lqe`

Code : `docs_url` / `openapi_url` **off** dès que `ENV=production` **ou**
`ALLOWED_ORIGINS` est posé. CORS prod = cette liste. `X-API-Key` inchangé.

Domaine TLS = **Dokploy / Issouf**, pas ce PR.

### Option B — Rester 100 % interne

Console reste factice. Rejeté : la démo du 17 ne peut pas commander le moteur.

### Option C — Tout exposer puis filtrer plus tard

Rejeté : `/docs` et `/admin/lqe` fuitent le contrat et le sas linguistique.

## Décision

**Option A.** Amende ADR-0026 sur un point : l'API peut avoir **un** hostname
public **étroit**. WhatsApp, Postgres, `/admin` restent internes.

## Conséquences

- Marcel pose `ENGINE_URL` + `ENGINE_API_KEY` **après** le domaine.
- `ALLOWED_ORIGINS=https://<console>.vercel.app` dans Dokploy API.
- Rate-limit déjà SlowAPI ; le proxy peut ajouter le sien.
- Rollback : retirer le domaine Traefik.

## Références

- ADR-0026, ADR-0030, #411 (fermée), brief collaborateur 16/08

## Historique

- 2026-08-16 — proposé, Option A.
- 2026-08-16 — **accepté** (Issouf). Code : docs/openapi off si prod ou ALLOWED_ORIGINS.
