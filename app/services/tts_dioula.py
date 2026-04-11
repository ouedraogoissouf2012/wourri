"""
WOURI - TTS Dioula (Côte d'Ivoire)
100% GRATUIT - facebook/mms-tts-dyu + NLLB-200 (dyu_Latn)

Ce service est spécifique au Dioula ivoirien, distinct du Bambara malien.
Les deux langues sont mutuellement intelligibles mais ont des différences
de prononciation et de vocabulaire.

Modèles utilisés:
- TTS: facebook/mms-tts-dyu (Dioula)
- Traduction: facebook/nllb-200-distilled-600M (dyu_Latn)
"""
import uuid
import os
import subprocess
import logging
from app.config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()

# Vérifier si torch est disponible
TORCH_AVAILABLE = False
torch = None
np = None
wav = None

try:
    import torch as _torch
    import numpy as _np
    import scipy.io.wavfile as _wav
    torch = _torch
    np = _np
    wav = _wav
    TORCH_AVAILABLE = True
except ImportError:
    logger.info("torch non installé - TTS Dioula désactivé")

from app.services.model_registry import registry


def _load_tts_dioula():
    """Charge le modèle TTS Dioula (model, tokenizer)."""
    logger.info("Chargement du modèle TTS Dioula (mms-tts-dyu)...")
    from transformers import VitsModel, AutoTokenizer

    model = VitsModel.from_pretrained("facebook/mms-tts-dyu")
    tokenizer = AutoTokenizer.from_pretrained("facebook/mms-tts-dyu")
    logger.info("Modèle TTS Dioula chargé!")
    return model, tokenizer


def get_tts_model_dioula():
    """Charge le modèle TTS Dioula (lazy loading via ModelRegistry)"""
    if not TORCH_AVAILABLE:
        return None, None

    return registry.get("tts_dioula", loader=_load_tts_dioula)


def _get_nllb():
    """Retourne le modèle NLLB partagé via TranslationService (pas de doublon mémoire)."""
    from app.services.translation import get_translation_service
    return get_translation_service().get_nllb_model_and_tokenizer()


# Salutations françaises → Dioula (dictionnaire pur, jamais NLLB)
# NLLB traduit "Bonjour" par "Barokun nin na" au lieu de "i ni ce"
_FR_TO_DIOULA_GREETINGS = {
    "bonjour": "i ni ce,",
    "bonsoir": "i ni wula,",
    "bonne nuit": "i ni su,",
    "salut": "i ni ce,",
    "merci": "i ni ce,",
}


def _extract_french_greeting(text: str) -> tuple[str, str]:
    """Détecte une salutation française au début du texte.
    Retourne (salutation_dioula, texte_sans_salutation).
    Ex: 'Bonjour ! Il y a...' -> ('i ni ce,', 'Il y a...')
    """
    text_stripped = text.strip()
    text_lower = text_stripped.lower()
    # Trier par longueur décroissante pour matcher "bonne nuit" avant "bonjour"
    for fr_greet in sorted(_FR_TO_DIOULA_GREETINGS, key=len, reverse=True):
        if text_lower.startswith(fr_greet):
            dyu_greet = _FR_TO_DIOULA_GREETINGS[fr_greet]
            rest = text_stripped[len(fr_greet):].lstrip(" ,!.;:")
            if rest:
                return dyu_greet, rest
            else:
                return dyu_greet.rstrip(","), ""
    return "", text_stripped


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
    if not TORCH_AVAILABLE:
        return french_text

    # 1. Extraire la salutation avant NLLB
    greeting_dyu, remaining = _extract_french_greeting(french_text)

    if not remaining:
        # Texte = juste une salutation
        return greeting_dyu if greeting_dyu else french_text

    # 2. Traduire le reste via NLLB
    result = _nllb_translate(remaining)

    # 3. Nettoyer les répétitions
    result = clean_repetitions(result)

    # 4. Préfixer avec la salutation dioula
    if greeting_dyu:
        result = f"{greeting_dyu} {result}"

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


from app.services._ffmpeg import get_ffmpeg as find_ffmpeg, wav_to_ogg_normalized


def convert_wav_to_ogg(wav_path: str, ogg_path: str) -> bool:
    """Convertit un fichier WAV en OGG Opus avec normalisation loudnorm EBU R128.
    Délègue à _ffmpeg.wav_to_ogg_normalized (source unique, loudnorm si disponible).
    Fallback pydub si ffmpeg échoue.
    """
    if wav_to_ogg_normalized(wav_path, ogg_path):
        return True

    # Fallback pydub (sans loudnorm)
    try:
        from pydub import AudioSegment
        try:
            ffmpeg_path = find_ffmpeg()
            if ffmpeg_path != 'ffmpeg':
                AudioSegment.converter = ffmpeg_path
        except RuntimeError:
            pass
        audio = AudioSegment.from_wav(wav_path)
        audio.export(ogg_path, format="ogg", codec="libopus", bitrate="64k")
        try:
            os.remove(wav_path)
        except OSError:
            pass
        return True
    except Exception as e:
        logger.error(f"[TTS] Erreur pydub fallback: {e}")

    return False


_TECH_KEYWORDS = (
    'NPK', 'santimɛtiri', 'nɔgɔ', 'kilogramu', 'literi', 'poursan',
    'fertilisan', 'pestisidi', 'fungisidi', 'insektisidi', 'tɔnni',
)

# Marqueurs discursifs bambara → pause AVANT eux (découpage naturel)
# Format : (pattern_regex, pause_secondes_apres_segment_precedent)
_BAMBARA_DISCOURSE_MARKERS = [
    (r'\bnka\b', 0.30),    # "mais / cependant"
    (r'\bnɔ\b',  0.30),    # "alors / ensuite" (séquentiel)
    (r'\bfɔlɔ\b', 0.25),   # "d'abord"
    (r'\bkɔ\b',  0.25),    # "après ça" (souvent en fin de segment)
]


def _get_speaking_rate(sentence: str) -> float:
    """Détermine le speaking_rate selon le type de phrase.

    Valeurs calibrées pour MMS-TTS-DYU (VITS) — validées en production :
    - Salutation courte  → 1.05 : naturel, presque normal
    - Conseil agricole   → 1.15 : clair, fluide (défaut)
    - Technique (NPK…)   → 1.25 : lent, bien articulé
    """
    import re
    stripped = sentence.strip()
    if re.match(r'^(Aw ni|Alu ni|I ni|A ni)', stripped) or (
        stripped.endswith('!') and len(stripped.split()) <= 8
    ):
        return 1.05
    if any(kw in stripped for kw in _TECH_KEYWORDS):
        return 1.25
    return 1.15


def _split_on_bambara_markers(text: str) -> list[tuple[str, float]]:
    """Découpe un segment sur les marqueurs discursifs bambara.
    Retourne une liste de (fragment, pause_apres_en_secondes).
    Ne découpe QUE si les deux parties résultantes ont chacune >= 4 mots
    (évite les micro-fragments inutiles).
    """
    import re
    result = [(text, 0.0)]

    for pattern, pause in _BAMBARA_DISCOURSE_MARKERS:
        new_result = []
        for seg, seg_pause in result:
            parts = re.split(r'(?=\s+' + pattern + r')', seg, maxsplit=2)
            # Ne découper que si les deux parties ont chacune >= 4 mots
            if len(parts) > 1 and all(len(p.strip().split()) >= 4 for p in parts if p.strip()):
                for i, p in enumerate(parts):
                    p = p.strip()
                    if not p:
                        continue
                    is_last = (i == len(parts) - 1)
                    new_result.append((p, seg_pause if is_last else pause))
            else:
                new_result.append((seg, seg_pause))
        result = new_result

    return result


def _force_split_long(text: str, pause: float, max_words: int = 20) -> list[tuple[str, float]]:
    """Découpe un segment > max_words mots en deux parties égales.
    Coupe à la frontière de mot la plus proche du milieu.
    """
    words = text.split()
    if len(words) <= max_words:
        return [(text, pause)]

    mid = len(words) // 2
    first = ' '.join(words[:mid])
    second = ' '.join(words[mid:])
    return [(first, 0.30), (second, pause)]


def _split_sentences(text: str) -> list[tuple[str, float]]:
    """Découpe le texte en segments avec leur pause associée (en secondes).

    Hiérarchie des pauses :
    - !  →  0.50s  (exclamation)
    - ?  →  0.50s  (question)
    - .  →  0.45s  (fin de phrase)
    - ,  →  0.20s  (respiration / virgule)
    - marqueur bambara (nka, nɔ…) → 0.30s
    - découpage forcé (>12 mots)  → 0.25s
    """
    import re
    # Supprimer les templates {{...}}
    text = re.sub(r'\{\{[^}]+\}\}', '', text).strip()
    if not text:
        return []

    results: list[tuple[str, float]] = []

    # Étape 1 : découper sur ponctuation forte (. ! ?)
    strong_parts = re.split(r'(?<=[.!?])\s+', text)

    for part in strong_parts:
        part = part.strip()
        if not part:
            continue
        # Pause selon le signe de ponctuation qui termine ce bloc
        if part.endswith('!') or part.endswith('?'):
            end_pause = 0.50
        elif part.endswith('.'):
            end_pause = 0.45
        else:
            end_pause = 0.40  # dernier fragment sans ponctuation

        # Étape 2 : découper sur les virgules
        comma_parts = re.split(r',\s*', part)

        for ci, sub in enumerate(comma_parts):
            sub = sub.strip()
            if not sub:
                continue
            is_last_comma = (ci == len(comma_parts) - 1)
            comma_pause = end_pause if is_last_comma else 0.20

            # Étape 3 : découper sur marqueurs discursifs bambara
            marker_segs = _split_on_bambara_markers(sub)
            for mi, (seg, _) in enumerate(marker_segs):
                is_last_marker = (mi == len(marker_segs) - 1)
                seg_pause = comma_pause if is_last_marker else 0.30

                # Étape 4 : forcer la coupure si segment encore trop long
                results.extend(_force_split_long(seg, seg_pause))

    # Filtrer les fragments vides ou trop courts (< 3 mots → fusionner avec le suivant)
    cleaned: list[tuple[str, float]] = []
    for s, p in results:
        s = s.strip()
        if not s:
            continue
        if len(s.split()) < 3 and cleaned:
            # Fusionner ce micro-fragment avec le segment précédent
            prev_s, _ = cleaned[-1]
            cleaned[-1] = (prev_s + ' ' + s, p)
        elif len(s.split()) >= 2 or (len(s.split()) == 1 and len(s) > 3):
            cleaned.append((s, p))
    return cleaned


def _trim_leading_silence(waveform: np.ndarray, threshold: float = 0.01,
                          keep_ms: int = 30, sample_rate: int = 16000) -> np.ndarray:
    """Coupe le silence naturel au début d'un waveform VITS.

    MMS-TTS-DYU produit ~400ms de silence au début de chaque segment
    (transitoire du modèle). On garde keep_ms (30ms) pour éviter
    un démarrage trop brusque.
    """
    above = np.where(np.abs(waveform) > threshold)[0]
    if len(above) == 0:
        return waveform
    voice_start = above[0]
    keep_samples = int(sample_rate * keep_ms / 1000)
    trim_point = max(0, voice_start - keep_samples)
    return waveform[trim_point:]


def _clean_for_tts(text: str) -> str:
    """Nettoie le texte bambara pour le TTS MMS-DYU.

    MMS-TTS-DYU ne gère pas :
    - Les tons diacritiques (à, è, ì, ò, ù) → produit du bruit
    - Les apostrophes dans les contractions (b'a, k'a, n'a) → prononciation erronée

    On retire les tons tout en gardant les caractères bambara (ɛ, ɔ, ŋ, ɲ).
    """
    import unicodedata
    # Décomposer les caractères accentués, retirer les marques de ton
    result = []
    for ch in unicodedata.normalize("NFD", text):
        if unicodedata.category(ch) == "Mn":  # Mark, Nonspacing (tons)
            continue
        result.append(ch)
    cleaned = "".join(result)
    # Remplacer les apostrophes par un espace (b'a → b a)
    cleaned = cleaned.replace("'", " ").replace("'", " ")
    # Réduire les espaces multiples
    cleaned = " ".join(cleaned.split())
    return cleaned


def _synthesize_sentence(sentence: str, model, tokenizer,
                         speaking_rate: float = 1.15) -> np.ndarray | None:
    """Synthétise un segment unique avec le speaking_rate donné.

    Nettoie les tons + apostrophes avant synthèse.
    Trim le silence naturel VITS (~400ms) au début de chaque segment.
    """
    try:
        sentence = _clean_for_tts(sentence)
        inputs = tokenizer(sentence, return_tensors="pt")
        original_rate = model.config.speaking_rate
        model.config.speaking_rate = speaking_rate
        try:
            with torch.no_grad():
                output = model(**inputs).waveform
        finally:
            model.config.speaking_rate = original_rate
        waveform = output.squeeze().cpu().numpy()
        return _trim_leading_silence(waveform, sample_rate=model.config.sampling_rate)
    except Exception as e:
        logger.error(f"[TTS] Erreur synthèse '{sentence[:40]}': {e}")
        return None


def synthesize_dioula_text(dioula_text: str) -> str | None:
    """Génère un fichier audio OGG à partir de texte Dioula.

    v3 — pauses variables :
    - Découpage hiérarchique : . ! ? → virgule → marqueurs bambara → forcé
    - Pause adaptée : 200ms (virgule) / 300ms (marqueur) / 450ms (fin phrase)
    - speaking_rate : 1.05 (salutation) / 1.15 (défaut) / 1.25 (technique)
    """
    if not TORCH_AVAILABLE or not dioula_text:
        return None

    try:
        model, tokenizer = get_tts_model_dioula()
        if model is None:
            return None

        sample_rate = model.config.sampling_rate

        segments = _split_sentences(dioula_text)
        if not segments:
            segments = [(dioula_text, 0.40)]

        audio_parts = []

        # Silence initial 50ms — compense le preskip Opus (104 samples)
        audio_parts.append(np.zeros(int(sample_rate * 0.05), dtype=np.float32))

        for i, (sentence, pause_s) in enumerate(segments):
            rate = _get_speaking_rate(sentence)
            waveform = _synthesize_sentence(sentence, model, tokenizer, speaking_rate=rate)
            if waveform is None:
                continue
            audio_parts.append(waveform)
            # Ajouter le silence APRÈS ce segment
            # Dernier segment → silence de fin 0.30s (évite la coupure brusque)
            actual_pause = pause_s if i < len(segments) - 1 else 0.30
            silence_samples = int(sample_rate * actual_pause)
            audio_parts.append(np.zeros(silence_samples, dtype=np.float32))

        if not audio_parts:
            return None

        combined = np.concatenate(audio_parts)

        # Normalisation
        max_val = np.max(np.abs(combined))
        if max_val > 0:
            combined = combined / max_val
        combined = (combined * 32767).astype(np.int16)

        file_id = uuid.uuid4()
        wav_filename = f"dyu_{file_id}.wav"
        ogg_filename = f"dyu_{file_id}.ogg"
        wav_filepath = os.path.join(settings.audio_output_dir, wav_filename)
        ogg_filepath = os.path.join(settings.audio_output_dir, ogg_filename)
        os.makedirs(settings.audio_output_dir, exist_ok=True)

        wav.write(wav_filepath, rate=sample_rate, data=combined)

        if convert_wav_to_ogg(wav_filepath, ogg_filepath):
            if os.path.exists(ogg_filepath) and os.path.getsize(ogg_filepath) > 0:
                return f"/static/audio/{ogg_filename}"

        if os.path.exists(wav_filepath) and os.path.getsize(wav_filepath) > 0:
            return f"/static/audio/{wav_filename}"

    except Exception as e:
        logger.error(f"Erreur TTS Dioula: {e}")

    return None


async def synthesize_dioula(french_text: str) -> tuple[str | None, str | None]:
    """Traduit du français vers le Dioula et génère l'audio"""
    if not TORCH_AVAILABLE or not french_text:
        return None, None

    try:
        dioula_text = translate_to_dioula(french_text)
        try:
            logger.info(f"Traduction Dioula: {french_text[:50]}... -> {dioula_text[:50]}...")
        except UnicodeEncodeError:
            logger.info("Traduction Dioula effectuée")

        audio_url = synthesize_dioula_text(dioula_text)
        return audio_url, dioula_text

    except Exception as e:
        logger.error(f"Erreur synthèse Dioula: {e}")
        return None, None


def check_dioula_status() -> dict:
    """Vérifie le statut des modèles Dioula"""
    from app.services.translation import get_translation_service
    nllb_model, _ = get_translation_service().get_nllb_model_and_tokenizer()
    return {
        "torch_available": TORCH_AVAILABLE,
        "tts_loaded": registry.is_loaded("tts_dioula"),
        "translator_loaded": nllb_model is not None,
        "tts_model": "facebook/mms-tts-dyu",
        "translation_code": "dyu_Latn",
        "nllb_shared": True
    }
