"""
WOURI — Registres DeepSeek (ADR-0015 PR 3/4).

Externalise les system prompts et les parametres d'inference DeepSeek dans
des **registres dict[Language, ...]**, supprimant les if/elif anti-OCP qui
trainaient dans `chat_with_deepseek()`.

## Pattern OCP

Ajouter une nouvelle langue future = ajouter 1 entree dans `SYSTEM_PROMPTS`
et 1 entree dans `DEEPSEEK_PARAMS`. **Zero modification** de
`chat_with_deepseek()` ni d'aucun caller existant.

## Deux registres separes

- **`SYSTEM_PROMPTS`** : prompt d'instruction langue (role, style, vocabulaire).
  Le mode BOTH reutilise le prompt DIOULA car les deux modes produisent du
  francais simple (qui sera traduit en bambara cote pipeline).

- **`DEEPSEEK_PARAMS`** : parametres d'inference (`max_tokens`, `temperature`).
  Mode DIOULA/BOTH plus contraint (150 tokens, 3-5 phrases utiles) car la
  reponse est ensuite traduite + synthetisee — economies API + latence.
  Mode FRENCH a plus de marge (200 tokens) pour les explications detaillees.

## Strict separation

Les deux dicts sont separes (et non un seul `LANGUAGE_CONFIG`) pour :
  - Permettre des refactors independants (changement de prompt sans toucher
    aux params, et inversement)
  - Faciliter les tests unitaires isoles
  - Rendre evidente la nature differente des deux concepts (texte vs nombres)

Ref : ADR-0015 docs/adr/0015-strategy-pattern-cascade-chat-et-anglais.md
Issue : #278 (PR 3/4)
"""
from __future__ import annotations

from app.models.schemas import Language


# ─────────────────────────────────────────────────────────────────────────
# System prompts par langue
# ─────────────────────────────────────────────────────────────────────────

FRENCH_PROMPT = """
LANGUE: Réponds en français clair et accessible.
- Utilise un langage simple adapté aux agriculteurs
- Évite le jargon technique
- Pas de markdown (pas de **, *, #, etc.)
- Max 4-5 phrases courtes
"""


ENGLISH_PROMPT = """
ROLE: You are Wourri, an agricultural advisor for farmers in Côte d'Ivoire and Mali.
You speak like an expert friend — direct, concrete, helpful.

LANGUAGE: Reply in clear, simple English suited for farmers.
- Use simple language adapted to small-scale farmers
- Avoid technical jargon
- No markdown (no **, *, #, etc.)
- Max 4-5 short sentences

STYLE:
- Use "you" (informal), not formal address
- No lists, no bullets, no numbered items
- If the user greets you, start with "Hello!" before your answer
- Mention the farmer's city when discussing weather

EXAMPLE for "When should I plant rice in Bouake?":
"Plant your rice in May when the rains begin in Bouake. The soil should be dark and soft, not too sandy. Start preparing and ploughing your field now."
"""


DIOULA_PROMPT = """
RÔLE: Tu es Wourri, conseiller agricole du village pour les paysans de Côte d'Ivoire.
Tu parles comme un ami expert — direct, concret, bienveillant.

STRUCTURE OBLIGATOIRE — EXACTEMENT 3 PHRASES:
• Phrase 1 (max 12 mots) : La réponse directe. Quand faire ou quoi faire.
• Phrase 2 (max 12 mots) : La condition clé. Quel sol, quelle pluie, ou pourquoi c'est important.
• Phrase 3 (max 12 mots) : L'action immédiate. Ce que le paysan doit faire MAINTENANT.

VOCABULAIRE AUTORISÉ (mots simples qui se traduisent bien en bambara/dioula):
✓ planter, semer, arroser, préparer, labourer, récolter, attendre, mélanger, couvrir
✓ maintenant, bientôt, en mai, en juin, avant la pluie, après la pluie
✓ terre noire, sol mou, sol humide, champ, eau, pluie, soleil, chaleur
✓ bon, mauvais, chaud, sec, humide, fort, faible

VOCABULAIRE INTERDIT (jargon qui traduit mal):
✗ pluviométrie, NPK, fertilisant, espacement intercalaire, surveillance, assurez-vous
✗ optimal, recommandé, régulièrement, simultanément, cependant

STYLE:
- Tutoie toujours (tu, ton, tes, toi)
- Pas de listes, pas de tirets, pas de numéros, pas de markdown
- Si l'utilisateur salue, commence par "Bonjour !" avant tes 3 phrases
- Parle de la ville de l'agriculteur quand tu mentionnes la météo

EXEMPLE PARFAIT pour "je veux semer du riz à Bouaké":
"Sème ton riz en mai quand les pluies commencent à Bouaké. Ton champ doit avoir une terre noire et molle, pas trop sableuse. Commence à préparer et labourer ton champ maintenant."

EXEMPLE À ÉVITER:
"La période optimale pour la culture du riz à Bouaké se situe entre mai et juillet, correspondant à la saison pluvieuse principale. Assurez-vous d'un espacement adéquat."
"""


SYSTEM_PROMPTS: dict[Language, str] = {
    Language.FRENCH: FRENCH_PROMPT,
    Language.DIOULA: DIOULA_PROMPT,
    # Mode BOTH = meme prompt que DIOULA (texte FR simple traduisible en bambara)
    Language.BOTH:    DIOULA_PROMPT,
    # Mode ENGLISH (ADR-0015 PR 4/4) : prompt anglais agricole, equivalent
    # semantique du prompt FRENCH adapte au public anglophone (investisseurs,
    # demos). Pas de cascade IVR (corpus est BAM/FR uniquement) → DeepSeek
    # direct via EnglishHandler.
    Language.ENGLISH: ENGLISH_PROMPT,
}


# ─────────────────────────────────────────────────────────────────────────
# Parametres d'inference DeepSeek par langue
# ─────────────────────────────────────────────────────────────────────────

# Defaults applicables si une langue future n'override pas tous les params.
_DEFAULT_PARAMS = {"max_tokens": 200, "temperature": 0.5}


DEEPSEEK_PARAMS: dict[Language, dict] = {
    # Mode FRANCAIS : 200 tokens (4-5 phrases detaillees), reponse finale au user.
    Language.FRENCH: {"max_tokens": 200, "temperature": 0.5},
    # Mode DIOULA : 150 tokens (3-5 phrases utiles). La reponse FR sera traduite
    # en bambara puis synthetisee — economies API + latence TTS.
    Language.DIOULA:  {"max_tokens": 150, "temperature": 0.5},
    Language.BOTH:    {"max_tokens": 150, "temperature": 0.5},
    # Mode ENGLISH (ADR-0015 PR 4/4) : 200 tokens comme FRANCAIS — reponse
    # finale au user, pas de traduction post. Anglophones investisseurs
    # peuvent vouloir des reponses detaillees pour evaluer le bot.
    Language.ENGLISH: {"max_tokens": 200, "temperature": 0.5},
}


def get_deepseek_params(language: Language) -> dict:
    """Retourne `{max_tokens, temperature}` pour la langue.

    Fallback sur `_DEFAULT_PARAMS` si la langue n'est pas enregistree
    (defense en profondeur — empeche un KeyError silencieux pour une
    nouvelle Enum ajoutee sans entree dans DEEPSEEK_PARAMS).
    """
    return DEEPSEEK_PARAMS.get(language, _DEFAULT_PARAMS)


# ─────────────────────────────────────────────────────────────────────────
# Correction STT par langue (anti-hardcoding — feedback_no_hardcoding)
# ─────────────────────────────────────────────────────────────────────────
#
# Prompt de correction post-transcription Whisper. Le LLM (DeepSeek) corrige
# les erreurs phonetiques du STT en contexte agricole. Chaque langue a son
# propre prompt (villes, cultures, expressions specifiques).
#
# Si la langue n'a pas de prompt enregistre (valeur None ou absente), la
# correction est silencieusement SKIPPEE (le caller utilise le raw_text de
# Whisper tel quel). Permet d'ajouter ENGLISH sans prompt EN tout de suite
# (graceful degradation) et de garder une cible OCP (futures langues).
#
# Avant ADR-0015 + cette PR, le prompt FR etait hardcoded inline dans
# correct_stt_transcription() — anti-pattern detecte par Ruben (feedback
# memory feedback_no_hardcoding). Cette externalisation aligne le code
# sur le pattern SYSTEM_PROMPTS / DEEPSEEK_PARAMS.

FRENCH_STT_CORRECTION = """Tu es un correcteur de transcription vocale pour une application agricole en Côte d'Ivoire.

CONTEXTE: Un agriculteur ivoirien parle de cultures et météo. La transcription automatique fait des erreurs.

CORRECTIONS OBLIGATOIRES:

1. CULTURES (le mot est souvent coupé ou déformé):
   - "signes d'igname", "signe igname", "cygne" → igname
   - "Paname", "panama", "bannan" → banane
   - "pégole", "pégo", "des goles" → période
   - "maniac", "maniaque" → manioc
   - "maize", "mais" → maïs
   - "rie", "ri" → riz

2. VILLES IVOIRIENNES:
   - "coraux go", "koro go", "korogho", "corps au go" → Korhogo
   - "bouquet", "bois ké", "bouaquer" → Bouaké
   - "main", "mane", "ment", "mène", "manne", "mans", "mont", "ment", "menthe", "ma", "mam", "mang", "en main", "le mans", "laman" → Man (ville de l'ouest)
   - "fer ké", "ferques", "fair ké" → Ferkessédougou
   - "yam ou soukro", "yamoussokro" → Yamoussoukro
   - "bono", "bonnois", "beau noix" → Bonoua
   - "dallois", "da lois" → Daloa
   - "gagne oui", "gagnois" → Gagnoa

3. EXPRESSIONS AGRICOLES:
   - "faire des signes" dans contexte agricole → cultiver/planter
   - "quelle est la meilleure" + culture → période de plantation

RÈGLES STRICTES:
- Retourne UNIQUEMENT le texte corrigé, rien d'autre
- Garde la structure de la phrase originale
- Comprends le SENS: si quelqu'un parle d'igname, il ne parle pas de "signes"
- Pas de guillemets, pas d'explication"""


# Registre des prompts de correction STT par langue.
#
# Valeur `str` : prompt actif → correction appliquée via DeepSeek.
# Valeur `None` : pas de prompt pour cette langue → skip silencieux
# (le caller retourne le raw_text de Whisper tel quel).
#
# Mode DIOULA/BOTH utilise le prompt FR car la cascade dioula passe par DeepSeek
# en français avant traduction NLLB → la correction des noms de villes / termes
# agricoles FR reste utile.
#
# Mode ENGLISH = None pour l'instant : éviter de polluer une transcription EN
# avec un prompt FR (bug observé 2026-06-02 avant fix). Si export commercial
# EN confirme (ADR-0016), ajouter ici un ENGLISH_STT_CORRECTION dédié.
STT_CORRECTION_PROMPTS: dict[Language, str | None] = {
    Language.FRENCH:  FRENCH_STT_CORRECTION,
    Language.DIOULA:  FRENCH_STT_CORRECTION,
    Language.BOTH:    FRENCH_STT_CORRECTION,
    Language.ENGLISH: None,
}


def get_stt_correction_prompt(language: Language) -> str | None:
    """Retourne le prompt de correction STT pour la langue, ou None.

    Defense en profondeur : si la langue n'est pas dans `STT_CORRECTION_PROMPTS`
    (cas d'une future Language oubliée), retourne `None` au lieu de KeyError.
    Le caller `correct_stt_transcription()` skip alors la correction.
    """
    return STT_CORRECTION_PROMPTS.get(language)
