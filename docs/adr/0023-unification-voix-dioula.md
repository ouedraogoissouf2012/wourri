# ADR-0023 — Unification de la voix dioula (#362)

**Statut** : accepté
**Date** : 2026-08-10
**Auteur(s)** : Claude (assistant) sous direction de Ouedraogo Issouf
**Valideur** : Ouedraogo Issouf
**Lié à** : issue #362, docs/AUDIT_DIOULA_2026-08.md §7.4-7.5

---

## Contexte (faits vérifiés)

**Un même utilisateur dioula entend aujourd'hui DEUX voix différentes** :

| Ce qu'il entend | Voix servie | Chemin |
|---|---|---|
| Réponses du bot (cascade chat) | `facebook/mms-tts-dyu` (dioula) ✓ | `ivr_searcher`/`deepseek_router` → `tts_dioula.py:49` |
| Messages système (indisponibilité, onboarding, cache warmup) | `facebook/mms-tts-bam` (**bambara malien**) | whatsapp-server `tryGenerateAudioFromText` → `POST /api/tts/bambara` (`app-baileys.js:203`) |

Constaté en réel : le warmup du cache audio (`[AUDIO-CACHE] cached 4`) génère les
messages système en voix bambara — vérifié lors du test E2E de Ruben (2026-08-09).

Aggravants (audit §7.4-7.5) :
- `POST /api/tts/` avec `language=dioula` sert aussi `mms-tts-bam` (`routers/tts.py:38-40`)
  et étiquette l'audio « dioula ».
- Le registre `SUPPORTED_LANGUAGES` (`constants.py`) ne contient pas `dyu` ;
  l'alias `dioula → bam` pointe vers le modèle malien. Le vrai modèle dioula
  runtime est hardcodé hors de la source unique des langues.
- Divergence NLLB : la cascade chat traduit FR→`dyu_Latn`, mais
  `/api/tts/translate` et la compréhension BAM→FR passent par `bam_Latn`.

Mission projet (CLAUDE.md) : « Langue cible : dioula ivoirien (dyu), pas
bambara malien (bam) ».

## Questions posées avant la décision

1. Quelle voix pour TOUT ce qu'entend un utilisateur dioula (réponses + système) ?
2. Faut-il basculer aussi la compréhension NLLB (`bam_Latn` → `dyu_Latn`) ?
3. Faut-il ajouter `dyu` au registre des langues ?

## Piège technique identifié (pour cadrer les options)

Le registre `SUPPORTED_LANGUAGES` a DEUX consommateurs aux besoins différents :
- **TTS** (`tts_ivoirian`) : `dioula` devrait servir `mms-tts-dyu` ;
- **ASR** (`routers/asr.py:84`) : le code `bam` déclenche la chaîne spécialisée
  bambara/dioula (NeMo→MMS-dyu→generic). Si l'alias `dioula` basculait
  globalement vers un nouveau code `dyu`, les requêtes ASR « dioula »
  quitteraient la chaîne spécialisée pour la chaîne générique — **régression**.
→ Toute unification doit corriger les chemins TTS **sans toucher au routage ASR**.

## Options étudiées

### A — La voix dioula partout côté sortie, ciblée et sans toucher l'ASR *(recommandée)*
1. `routers/tts.py` : `Language.DIOULA` → `synthesize_dioula_text` (mms-tts-dyu)
   au lieu de `synthesize_bambara`. `/api/tts/bambara` reste réellement bambara
   (son nom redevient honnête).
2. Nouvel endpoint `POST /api/tts/dioula` (query param `text`, même contrat que
   `/api/tts/bambara`) servant `mms-tts-dyu`.
3. whatsapp-server : `tryGenerateAudioFromText` bascule sur `/api/tts/dioula`
   + **purge du cache audio** (les 4 messages système regénérés en voix dioula).
4. Registre : ne PAS modifier l'alias global (piège ASR) ; documenter dans
   `constants.py` que la voix dioula runtime vit dans `tts_dioula` (mms-tts-dyu)
   et que `bam` reste le code de routage ASR de la chaîne bambara/dioula.
5. NLLB compréhension (`bam_Latn`) : **inchangée** — bascule vers `dyu_Latn`
   uniquement après éval comparative (même esprit qu'ADR-0022 : pas de bascule
   sans mesure). La traduction de RÉPONSE (cascade chat) est déjà en `dyu_Latn`.
- **Avantages** : une seule voix pour l'utilisateur ; changement ciblé, testable ;
  zéro risque ASR ; réversible.
- **Coût** : S/M (2 fichiers API + 1 fichier whatsapp-server + purge cache + tests).

### B — Tout basculer vers `bam` (renoncer à la voix dyu)
- Une seule voix aussi… mais la mauvaise : contraire à la mission (dioula CI ≠
  bambara Mali). Rejetée.

### C — Statu quo documenté
- Deux voix assumées. Incohérence UX réelle constatée en test — rejetée.

## Décision

**Option retenue** : **A** (validée par Ruben le 2026-08-10 : « super j'ai lu et valide »).
Rappel : (voix dioula partout côté sortie, ASR intouché, NLLB
compréhension différée à une éval).

## Conséquences (si A)

- L'utilisateur dioula entend UNE voix cohérente partout.
- `/api/tts/bambara` ne ment plus (il sert du bambara, point).
- Le cache audio doit être purgé une fois (`whatsapp-server/audio_cache/`) —
  regénéré automatiquement au warmup suivant.
- La question NLLB compréhension reste ouverte, tracée ici, conditionnée à une
  éval sur phrases réelles.
- **Rollback** : revenir au mapping précédent dans `routers/tts.py` + re-pointer
  le whatsapp-server.

## Références

- Issue #362 ; audit §7.4-7.5 ; `routers/tts.py:38-40` ; `app-baileys.js:189-203` ;
  `constants.py:25-78` ; test E2E Ruben 2026-08-09 (deux voix constatées).

## Historique

- 2026-08-10 — rédaction (statut proposé). Option A recommandée.
- 2026-08-10 — **accepté** par Ruben. Implémentation Option A dans la PR liée.
