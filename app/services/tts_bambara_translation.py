"""
WOURI - Orchestration de la traduction FR <-> Bambara.

Extrait de tts_bambara.py (modularisation 2026-08) : orchestration de la
traduction, sans dépendance torch. Délègue au TranslationService (dictionnaire
Bamadaba + NLLB) et chaîne le prétraitement/nettoyage fourni par
tts_bambara_text.

Les imports de `app.services.translation` sont volontairement LAZY (dans le
corps des fonctions) pour éviter un cycle d'import translation <-> tts — à
préserver tel quel.
"""
import logging

from app.services.tts_bambara_text import (
    protect_city_names,
    restore_city_names,
    preprocess_french_text,
    split_into_sentences,
    clean_bambara_text,
)

logger = logging.getLogger(__name__)


def _detect_and_strip_greeting(text: str) -> tuple[str, str]:
    """Extrait une expression française validée depuis le dictionnaire commun."""
    from app.services.translation import Direction, get_translation_service

    return get_translation_service().translate_leading_phrase(
        text,
        Direction.FR_TO_BAM,
    )


def translate_to_bambara(french_text: str) -> str:
    """
    Traduit du français vers le Bambara.
    Stratégie :
      0. Détecter et extraire les salutations (dictionnaire pur, pas NLLB)
      1. Protéger les noms de villes
      2. Prétraiter le texte
      3. Découper en phrases courtes (NLLB fonctionne mieux phrase par phrase)
      4. Pour chaque phrase : essayer phrase exacte du dictionnaire, sinon NLLB
      5. Post-traitement anti-répétition
      6. Restaurer les noms de villes
      7. Préfixer avec la salutation bambara
    """
    if not french_text or not french_text.strip():
        return french_text

    from app.services.translation import Direction, get_translation_service
    service = get_translation_service()

    # Une phrase complète validée est prioritaire sur l'extraction de son
    # éventuelle salutation initiale.
    exact_translation = service.translate_exact_phrase(
        french_text,
        Direction.FR_TO_BAM,
    )
    if exact_translation:
        return exact_translation

    # 0. Détecter et extraire la salutation (sera ajoutée en bambara pur)
    greeting_bam, remaining_text = _detect_and_strip_greeting(french_text)
    if not remaining_text:
        # Si le texte n'est qu'une salutation
        return greeting_bam if greeting_bam else french_text

    # Protéger les noms de villes
    protected_text, city_map = protect_city_names(remaining_text)
    if city_map:
        logger.info(f"[Traduction] Villes protégées: {list(city_map.values())}")

    # Prétraitement
    preprocessed = preprocess_french_text(protected_text)
    if not preprocessed:
        return french_text

    # Découper en phrases courtes pour une meilleure traduction
    sentences = split_into_sentences(preprocessed)
    if not sentences:
        sentences = [preprocessed]

    translated_parts = []
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue

        # Traduire chaque phrase individuellement
        result = service.translate(sentence, Direction.FR_TO_BAM)

        if result and result.confidence > 0:
            translated_parts.append(result.text)
        else:
            # Si aucune stratégie ne marche, garder le texte original
            translated_parts.append(sentence)

    result = " ".join(translated_parts)

    # Post-traitement anti-répétition
    result = clean_bambara_text(result)

    # Restaurer les noms de villes
    if city_map:
        result = restore_city_names(result, city_map)

    # Préfixer avec l'expression bambara validée (dictionnaire pur, jamais NLLB)
    if greeting_bam:
        result = f"{greeting_bam}, {result}"

    try:
        logger.info(f"[Bambara] Traduit: {len(french_text)} chars -> {len(result)} chars")
    except UnicodeEncodeError:
        logger.info("[Bambara] Traduction effectuee")

    return result


def _split_bam_greeting(text: str) -> tuple[str, str]:
    """Extrait une expression bambara validée depuis le dictionnaire commun."""
    from app.services.translation import Direction, get_translation_service

    return get_translation_service().translate_leading_phrase(
        text,
        Direction.BAM_TO_FR,
    )


def translate_to_french(bambara_text: str) -> str:
    """
    Traduit du Bambara vers le Français.
    1. Détecte les salutations collées par l'ASR (inisɔgɔma -> Bonjour)
    2. Délègue au TranslationService (dictionnaire 11k+ mots + NLLB fallback)
    """
    if not bambara_text or not bambara_text.strip():
        return bambara_text

    from app.services.translation import Direction, get_translation_service
    service = get_translation_service()

    exact_translation = service.translate_exact_phrase(
        bambara_text,
        Direction.BAM_TO_FR,
    )
    if exact_translation:
        return exact_translation

    # Détecter et séparer une salutation collée par l'ASR
    greeting_fr, remaining = _split_bam_greeting(bambara_text)

    if remaining:
        result = service.translate_to_french(remaining)
    else:
        # Texte = juste une salutation
        return greeting_fr if greeting_fr else bambara_text

    # Capitaliser la première lettre
    if result and result[0].islower():
        result = result[0].upper() + result[1:]

    # Préfixer avec l'expression française
    if greeting_fr:
        result = f"{greeting_fr}, {result}"

    return result
