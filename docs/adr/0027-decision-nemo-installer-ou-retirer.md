# ADR-0027 — Décision NeMo Soloni : installer `nemo-toolkit` ou retirer le provider

**Statut** : accepté
**Date** : 2026-08-14
**Auteur(s)** : Claude (assistant) sous direction de Ouedraogo Issouf
**Valideur** : Ouedraogo Issouf (Ruben) — accepté 2026-08-15 (« tu peux aller », Option A)
**Lié à** : issue #358 (checklist « Trancher NeMo »), [ADR-0022](0022-composition-chaine-asr-dioula.md) (ordre des providers), [ADR-0021](0021-dedup-provider-asr-nemo.md) (source unique du provider), [ADR-0011](0011-strategie-prechargement-ml.md) (préchargement)

---

## Contexte

Le provider ASR **NeMo Soloni** (`RobotsMali/soloni-114m-tdt-ctc-v0`, décodeur TDT
bambara) est déclaré en **tête** de la chaîne ASR bambara/dioula
([asr/__init__.py:33-40](../../app/services/asr/__init__.py)) mais **n'est jamais
exécuté** : le package Python `nemo` n'est ni dans `requirements.txt`, ni dans
`requirements-dev.txt`, ni dans `Dockerfile.prod` (vérifié fichier:ligne
2026-08-14). `_nemo_available` vaut donc `False`
([nemo_provider.py:25-36](../../app/services/asr/nemo_provider.py)) et le provider
est skippé silencieusement à chaque requête.

Il a tourné en avril (les corrections `cultures_nemo_errors` en témoignent) ; la
réinstallation Python de juillet (#313) l'a perdu.

**État actuel du câblage NeMo** (ce qu'un retrait devrait défaire, ou ce qu'une
installation ré-activerait) :

| Point | Emplacement | Rôle |
|---|---|---|
| Provider | [nemo_provider.py](../../app/services/asr/nemo_provider.py) (~148 l.) | `NemoSoloniASR` + préchargement + statut |
| Ordre chaîne | [asr/__init__.py:37-40](../../app/services/asr/__init__.py) | 1er provider (skip car indispo) |
| Préchargement | [main.py:23,70-84](../../app/main.py) | `preload_nemo_model()` au démarrage — log « INDISPONIBLE » à chaque boot |
| Santé | [main.py:287](../../app/main.py) (`get_nemo_status`) | `/health` rapporte `nemo_available`, `model_path_exists`, `model_loaded` |
| Post-traitement | [asr_bambara_normalizer.py](../../app/services/asr_bambara_normalizer.py) | normalisation appelée par `NemoSoloniASR.transcribe_wav` (spécifique NeMo) |
| Modèle | cache HF `models--RobotsMali--soloni-114m-tdt-ctc-v0` (`.nemo`, ~459 Mo cité #358) | orphelin sur disque tant que `nemo` absent |
| Tests | `test_lazy_loading` (préchargement eager), `test_health_endpoint`, `test_asr_providers`, `test_asr_normalizer`… | encodent le comportement NeMo actuel |

**Pourquoi décider maintenant** : #358 a réparé l'adapter MMS-dyu (le vrai
transcripteur dioula) et demande explicitement de **trancher NeMo** : soit
l'installer et le rendre opérationnel, soit retirer proprement le code mort
(provider + préchargement + `/health` + modèle orphelin) pour arrêter de porter
une dépendance déclarée-mais-inerte et un log « INDISPONIBLE » trompeur à chaque
démarrage.

### Périmètre de cet ADR vs ADR-0022

[ADR-0022](0022-composition-chaine-asr-dioula.md) (proposé) traite **l'ordre des
providers** et pose, dans son Option A, « NeMo reste en code mais non installé »
avec un **critère de bascule WER** (≥ 30 vraies voix dioula) pour toute
modification de la chaîne. Cet ADR-0027 est **complémentaire et plus fin** : il
instruit la branche que #358 pose et qu'ADR-0022 n'a pas détaillée — le
**comparatif installer vs retirer proprement**, avec le blast radius exact du
retrait. Il ne modifie pas la décision d'ordre d'ADR-0022.

> ⚠️ Hors périmètre (géré par la fenêtre d'orchestration) : l'adapter MMS-dyu
> (#358) et le déploiement (#358 `.dockerignore` / montage volume). Cet ADR ne
> touche **que** la décision NeMo.

## Questions posées avant la décision

1. Le décodeur TDT NeMo apporte-t-il un gain de qualité **mesuré** sur le
   bambara/dioula, qui justifierait le coût d'installation ?
2. Le coût de la dépendance `nemo-toolkit` (lightning, hydra, huggingface,
   sentencepiece… + poids image Docker) est-il acceptable au regard d'ADR-0011
   (budget mémoire/boot) et du travail Docker CPU-only récent (#377, image ~5 Go) ?
3. Que coûte un **retrait propre** (code + préchargement + `/health` + tests +
   modèle orphelin), et est-il réversible ?

## Options étudiées

### Option A — Retirer proprement le provider NeMo *(recommandation — voir Décision)*

- **Description** : supprimer `nemo_provider.py`, le retirer de la chaîne
  (`asr/__init__.py`), retirer le préchargement (`main.py:23,70-84`) et l'entrée
  `/health` (`main.py:287`), adapter les tests concernés, et documenter le
  nettoyage du modèle `.nemo` orphelin du cache. `asr_bambara_normalizer` : à
  conserver **seulement** s'il a un autre consommateur (à vérifier avant retrait
  — sinon il part avec NeMo). `CLAUDE.md` corrigé (« ASR NeMo actif » → faux).
- **Avantages** : supprime le code mort le plus visible du projet ; plus de log
  « INDISPONIBLE » trompeur à chaque boot ; `/health` cesse de rapporter un
  provider fantôme ; aucune dépendance lourde ajoutée ; aligne le code déclaré
  sur le code exécuté (le principe des standards : pas de code mort masqué).
- **Inconvénients** : perte de la réversibilité « 1 ligne » qu'offre le code
  dormant (ADR-0022) — réinstaller NeMo plus tard demanderait de réintroduire le
  provider (git revert reste possible). Touche `main.py` (chemin critique boot)
  et ~6 fichiers de tests.
- **Coût** : moyen (câblage boot + tests). Réversible via `git revert`.
- **Compatibilité** : cohérent avec ADR-0021 (source unique) et ADR-0011 (boot
  allégé). N'entre pas en conflit avec ADR-0022 (qui parle d'ordre, pas de
  présence).

### Option B — Installer `nemo-toolkit` (épinglé) et rendre NeMo opérationnel

- **Description** : ajouter `nemo-toolkit` épinglé à `requirements.txt`, l'inclure
  dans `Dockerfile.prod`, garantir la présence du modèle `.nemo` (téléchargement
  cache HF), et **mesurer** (WER) avant de lui laisser la tête de chaîne.
- **Avantages** : ré-active le décodeur TDT « meilleure qualité » allégué par les
  docstrings historiques ; restaure l'intention d'origine de la chaîne.
- **Inconvénients** : dépendance **très lourde** (lightning, hydra-core,
  sentencepiece, pytorch-lightning…) → image Docker gonflée juste après l'effort
  #377 (torch CPU-only, image 19 Go → ~5 Go) ; surface de maintenance et de
  conflits de versions accrue ; **le gain de qualité n'a jamais été mesuré**
  comparativement (ADR-0022 rejette précisément la re-hiérarchisation sans éval
  WER ≥ 30 vraies voix). Installer sans mesure = payer un coût certain pour un
  bénéfice non démontré.
- **Coût** : élevé (dépendances + image + validation WER).
- **Compatibilité** : en tension avec ADR-0011 (budget boot) et #377 (image
  légère). Nécessiterait le harnais WER d'ADR-0022 avant toute promotion.

### Option C — Statu quo (code dormant, non installé) — *déjà posé par ADR-0022 §A*

- **Description** : ne rien changer ; NeMo reste déclaré, skippé, non installé.
- **Avantages** : réversibilité maximale (1 ligne) ; coût runtime nul (skip).
- **Inconvénients** : **maintient le code mort** que #358 demande de trancher ;
  log « INDISPONIBLE » à chaque boot ; `/health` rapporte un provider fantôme ;
  dette de clarté persistante (« NeMo est-il utilisé ? » — non). Ne **répond pas**
  à la demande explicite de #358.
- **Coût** : nul.
- **Compatibilité** : c'est l'état actuel (ADR-0022 §Option A).

### Comparatif

| Critère | A (retirer) | B (installer) | C (statu quo) |
|---|---|---|---|
| Répond à #358 « trancher » | ✅ oui | ✅ oui | ❌ non (reporte) |
| Supprime le code mort | ✅ | ❌ (le rend vivant) | ❌ |
| Dépendance lourde ajoutée | 🟢 aucune | 🔴 nemo-toolkit + transitives | 🟢 aucune |
| Poids image Docker | 🟢 inchangé | 🔴 gonflé (post-#377) | 🟢 inchangé |
| Gain qualité | ⚪ neutre (MMS-dyu reste) | 🟠 allégué, **non mesuré** | ⚪ neutre |
| Log boot « INDISPONIBLE » | 🟢 supprimé | 🟢 devient « OK » | 🔴 persiste |
| Réversibilité | 🟠 `git revert` | — | 🟢 1 ligne |
| Effort | 🟠 moyen | 🔴 élevé | 🟢 nul |

## Décision

**Option A retenue** (retrait propre), acceptée par Ruben le 2026-08-15.

Justification :

- Le seul transcripteur dioula réellement entraîné sur des voix dioula est
  l'adapter MMS-dyu (réparé #358) ; MMS-generic assure le fallback. **Retirer
  NeMo ne dégrade aucun chemin actif** — il est déjà skippé à 100 %.
- Le gain du décodeur TDT n'a **jamais été mesuré** comparativement (ADR-0022) ;
  Option B paie un coût certain (dépendance lourde, image gonflée juste après
  #377) pour un bénéfice hypothétique — contraire à « mesurer, pas supposer ».
- Option C ne fait que **reporter** la question que #358 demande de trancher, en
  gardant du code mort et un log trompeur.
- Si NeMo devient un jour justifié (éval WER ≥ 30 vraies voix, cf. ADR-0022),
  l'Option A reste réversible par `git revert` + Option B.

## Conséquences

- **Si A retenue** :
  - Positives : code déclaré = code exécuté ; boot plus clair ; `/health` honnête ;
    aucune dépendance lourde.
  - Négatives assumées : perte de la réversibilité 1-ligne du code dormant.
  - Travail induit : supprimer `nemo_provider.py` ; retirer de `asr/__init__.py`,
    `main.py` (préchargement + `/health`) ; vérifier si `asr_bambara_normalizer` a
    un autre consommateur (sinon le retirer) ; adapter `test_lazy_loading`,
    `test_health_endpoint`, `test_asr_providers`, `test_asr_normalizer` ; nettoyer
    le `.nemo` orphelin (doc) ; corriger `CLAUDE.md`.
  - Rollback : `git revert`.
- **Si B retenue** : épingler `nemo-toolkit`, MAJ `Dockerfile.prod`, garantir le
  `.nemo`, lancer l'éval WER avant toute promotion en tête de chaîne (ADR-0022).
- **Si C retenue** : documenter explicitement dans #358 que la décision est
  « reporter », et corriger a minima `CLAUDE.md` (NeMo ≠ actif).
- **Verrou futur** : quelle que soit l'option, toute promotion de NeMo (ou de
  tout provider) en tête de chaîne reste soumise au critère WER d'ADR-0022.

## Références

- Issue #358 (§ « Trancher NeMo ») ; docs/AUDIT_DIOULA_2026-08.md §3 C1-C3, §7.1
- [ADR-0022](0022-composition-chaine-asr-dioula.md) (ordre providers + critère WER)
- [ADR-0021](0021-dedup-provider-asr-nemo.md) (source unique provider NeMo)
- [ADR-0011](0011-strategie-prechargement-ml.md) (budget préchargement/boot)
- Câblage NeMo : `nemo_provider.py`, `asr/__init__.py:33-40`, `main.py:23,70-84,287`
- PR #377 (Docker torch CPU-only, image 19 Go → ~5 Go)

## Historique

- 2026-08-14 — rédaction initiale (statut **proposé**), après cartographie du
  câblage NeMo réel. Recommandation Option A (retrait propre).
- 2026-08-15 — **accepté** Option A (validation Ruben). `asr_bambara_normalizer`
  conservé (consommé par `asr_normalizer.py`). Modèle `.nemo` orphelin : hors
  git, nettoyage disque ops (cache HF), pas de fichier repo à supprimer.
