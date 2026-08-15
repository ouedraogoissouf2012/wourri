"""
WOURI - Traduction FR <-> Dioula (NLLB dyu_Latn).

Extrait de tts_dioula.py (modularisation 2026-08) : orchestration de la
traduction Dioula, conceptuellement distincte de la synthèse audio. Contrairement
au TTS Bambara, la traduction Dioula appelle NLLB directement (torch), d'où la
dépendance torch importée ici via le même garde-fou que les autres modules TTS.

Les imports de `app.services.translation` sont volontairement LAZY (dans le corps
des fonctions) pour éviter un cycle d'import translation <-> tts.
"""
import logging

logger = logging.getLogger(__name__)

# Garde-fou torch identique aux autres modules TTS/ASR du projet : la traduction
# NLLB (model.generate sous torch.no_grad) n'est possible que si torch est là.
TORCH_AVAILABLE = False
torch = None
try:
    import torch as _torch
    torch = _torch
    TORCH_AVAILABLE = True
except ImportError:
    logger.info("torch non installé - traduction Dioula NLLB désactivée")


def _get_nllb():
    """Retourne le modèle NLLB partagé via TranslationService (pas de doublon mémoire)."""
    from app.services.translation import get_translation_service
    return get_translation_service().get_nllb_model_and_tokenizer()


def _extract_french_greeting(text: str) -> tuple[str, str]:
    """Extrait une expression française validée depuis le dictionnaire commun."""
    from app.services.translation import Direction, get_translation_service

    return get_translation_service().translate_leading_phrase(
        text,
        Direction.FR_TO_BAM,
    )


def _nllb_translate(text: str) -> str:
    """Traduit un texte FR→Dioula via NLLB (sans gestion salutation)."""
    model, tokenizer = _get_nllb()
    if model is None:
        return text

    tokenizer.src_lang = "fra_Latn"

    inputs = tokenizer(
        text,
        return_tensors="pt",
        padding=True,
        truncation=True,
        max_length=512
    )

    forced_bos_token_id = tokenizer.convert_tokens_to_ids("dyu_Latn")

    with torch.no_grad():
        generated_tokens = model.generate(
            **inputs,
            forced_bos_token_id=forced_bos_token_id,
            max_length=512,
            num_beams=5,
            no_repeat_ngram_size=3,
            repetition_penalty=1.2,
            early_stopping=True
        )

    return tokenizer.batch_decode(generated_tokens, skip_special_tokens=True)[0]


def translate_to_dioula(french_text: str) -> str:
    """Traduit du français vers le Dioula (dyu_Latn).
    1. Détecte et extrait la salutation française (dictionnaire pur)
    2. Traduit le reste via NLLB
    3. Préfixe avec la salutation dioula correcte
    """
    from app.services.translation import Direction, get_translation_service
    service = get_translation_service()

    exact_translation = service.translate_exact_phrase(
        french_text,
        Direction.FR_TO_BAM,
    )
    if exact_translation:
        return exact_translation

    # 1. Extraire la salutation avant NLLB
    greeting_dyu, remaining = _extract_french_greeting(french_text)

    if not remaining:
        # Texte = juste une salutation
        return greeting_dyu if greeting_dyu else french_text

    if not TORCH_AVAILABLE:
        return french_text

    # 2. Traduire le reste via NLLB
    result = _nllb_translate(remaining)

    # 3. Nettoyer les répétitions
    result = clean_repetitions(result)

    # 4. Préfixer avec la salutation dioula
    if greeting_dyu:
        result = f"{greeting_dyu}, {result}"

    return result


def clean_repetitions(text: str) -> str:
    """Nettoie les répétitions dans le texte traduit"""
    if not text:
        return text

    words = text.split()
    if len(words) < 2:
        return text

    # Détecter et supprimer les répétitions de mots consécutifs
    cleaned_words = [words[0]]
    for i in range(1, len(words)):
        # Ne pas ajouter si c'est une répétition du mot précédent
        if words[i].lower() != words[i-1].lower():
            cleaned_words.append(words[i])

    # Détecter les répétitions de phrases
    result = ' '.join(cleaned_words)

    # Si le texte est très répétitif (plus de 50% de répétition), tronquer
    unique_words = set(w.lower() for w in cleaned_words)
    if len(unique_words) < len(cleaned_words) * 0.3:
        # Trop répétitif, garder seulement la première partie
        result = ' '.join(cleaned_words[:len(cleaned_words)//2])

    return result


def translate_dioula_to_french(dioula_text: str) -> str:
    """Traduit du Dioula vers le Français via NLLB partagé"""
    if not TORCH_AVAILABLE:
        return dioula_text

    model, tokenizer = _get_nllb()
    if model is None:
        return dioula_text

    tokenizer.src_lang = "dyu_Latn"

    inputs = tokenizer(
        dioula_text,
        return_tensors="pt",
        padding=True,
        truncation=True,
        max_length=512
    )

    forced_bos_token_id = tokenizer.convert_tokens_to_ids("fra_Latn")

    with torch.no_grad():
        generated_tokens = model.generate(
            **inputs,
            forced_bos_token_id=forced_bos_token_id,
            max_length=512
        )

    result = tokenizer.batch_decode(generated_tokens, skip_special_tokens=True)[0]
    return result
