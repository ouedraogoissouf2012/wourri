# ADR-0033 — Atelier LQE hors du moteur (`wouri-lqe` + front Vue)

**Statut** : **accepté**  
**Date** : 2026-08-19  
**Valideur** : Issouf — « accepter » 2026-08-19  
**À copier vers** : `wouri-api/docs/adr/0033-lqe-service-separe.md` + `docs/adr/README.md`

---

## Décision

**Option A** : service séparé, comme WhatsApp.

| | |
|---|---|
| Back | `wouri-lqe` FastAPI (sans ML) |
| Front | `wouri-lqe-web` Vue 3 + Vite + Tailwind (pas Nuxt) |
| Comptes | **Toutes les langues** : user + mdp + **`language`** (pas un login figé baoulé) |
| Atelier | Une store unique, colonne `language` (`dyu`, `bci`, …) |
| Moteur `corpus_entries` | Reste **dyu seulement** tant qu’il n’y a pas de canal WhatsApp pour l’autre langue |

```
Agriculteur → whatsapp-server → wouri-api (pgvector = dyu, PAS de colonne language)
ADC / locuteur / provider → Vue → wouri-lqe
     compte.language = bci|dyu|…
     fiches.language = même code
```

### Stockage atelier (figé)

```
id | language | status (bronze→production)
   | text_local | text_fr | intent | cultures | audio_url
```

Nouvelle langue = entrée registre ISO + comptes liés à ce code.  
**Pas** un fichier `baoule_corpus.jsonl` par langue.  
**Pas** d’écriture baoulé dans `reponse_bambara` / `corpus_entries`.

### Amendement ADR-0031

Auth **atelier** isolée (phase 1 : comptes LQE). Pas de 2ᵉ auth sur le moteur / WhatsApp.  
1 compte = 1 langue (comme les orgs Convex).

### Phases

0. ~~ADR~~ **accepté**  
1. Squelette `wouri-lqe` + `wouri-lqe-web` + login multi-langue  
2. Migrer métier (upload, dédup, onglets, promote) **générique** (`language` en paramètre)  
3. Retirer `/admin/baoule` et `/admin/lqe` de `wouri-api`  
4. Plus tard : Better Auth ; import Or+ vers pgvector **seulement** si canal + colonne/store langue côté moteur

### Hors scope

WhatsApp, chat, ASR, TTS. Invention de texte local. Nuxt. Mélanger bci dans le corpus IVR dyu.

## Historique

- 2026-08-19 — proposé Option A (FastAPI + Vue/Tailwind)  
- 2026-08-19 — **accepté** Issouf + comptes toutes langues + store atelier unique

