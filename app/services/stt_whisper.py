"""
WOURI - Speech-to-Text avec Faster-Whisper
Utilise CTranslate2 pour des performances 4x plus rapides

NOTE: Necessite faster-whisper
Pour installer: pip install faster-whisper
"""
import asyncio
import json
import logging
import os
import re
from functools import lru_cache
from pathlib import Path

# Désactiver les symlinks sur Windows (évite les erreurs de permission)
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
os.environ["HF_HUB_DISABLE_SYMLINKS"] = "1"

import uuid
import tempfile
import subprocess
from app.config import get_settings
from app.services._ffmpeg import get_ffmpeg
# Sprint refactor 2026-05-28 : heuristiques deplacees dans stt/postprocess.py
# (extractions ADR-0005 / dette `is_likely_dioula_input` a supprimer apres
# integration AfroLID). Re-exportees ici pour compat des callsites internes.
from app.services.stt.postprocess import (
    is_likely_hallucination,
    is_likely_dioula_input,
)

logger = logging.getLogger(__name__)

settings = get_settings()

# Sprint refactor 2026-05-28 : corrections externalisees en JSON pour
# permettre aux contributeurs non-Python (linguistes, agronomes) de
# les enrichir sans toucher au code. Fichiers : agriculture.json (99
# entrees) + cities.json (132 entrees), charges lazy + caches via lru_cache.
_CORRECTIONS_DIR = Path(__file__).resolve().parent.parent / "data" / "stt_whisper_corrections"


# @lru_cache choisi (vs constante module-level) pour anticiper l'ajout
# de N domaines (cf. ADR-0005 Phase D : detection langue AfroLID pourra
# venir avec son propre fichier de patterns externalise).
@lru_cache(maxsize=None)
def _load_corrections(name: str) -> dict[str, str]:
    """Charge un fichier de corrections JSON (cache module-level).

    Mode degrade en cas de fichier absent OU corrompu : retourne `{}` (no-op)
    pour ne pas casser la transcription. La doc invite des contributeurs
    non-Python a editer ces JSON ; un JSONDecodeError (virgule trainante,
    guillemet manquant) doit logger un error explicite mais pas crasher
    la chaine de transcription.
    """
    path = _CORRECTIONS_DIR / f"{name}.json"
    try:
        with open(path, encoding="utf-8") as f:
            data: dict[str, str] = json.load(f)
            return data
    except FileNotFoundError:
        logger.warning(f"[Faster-Whisper] Corrections {name}.json introuvable, no-op")
        return {}
    except json.JSONDecodeError as e:
        logger.error(
            f"[Faster-Whisper] Corrections {name}.json corrompu ({e}), no-op. "
            "Verifier la syntaxe JSON (virgule trainante, guillemets manquants)."
        )
        return {}


def _apply_corrections(text: str, corrections: dict[str, str], label: str) -> str:
    """Applique les corrections (case-insensitive, word boundary, regex sur match).

    Word boundary `\\b` (issue #228) : sans ce garde, des entrees courtes
    comme `ment` matchent dans `vraiment`/`comment` -> `vraiMan`/`comMan`.
    Le filtre prealable `wrong in text_lower` n'attrape pas non plus le
    cas substring : la regex avec `\\b` est l'autorite finale.
    """
    if not text or not corrections:
        return text
    result = text
    text_lower = text.lower()
    for wrong, correct in corrections.items():
        if wrong in text_lower:
            pattern = re.compile(r"\b" + re.escape(wrong) + r"\b", re.IGNORECASE)
            # Sub peut renvoyer le meme texte si le match etait substring sans
            # word boundary -> on ne log que si une vraie substitution a eu lieu.
            new_result = pattern.sub(correct, result)
            if new_result != result:
                logger.info(f"[Faster-Whisper] Correction {label}: '{wrong}' -> '{correct}'")
                result = new_result
    return result

# Chemin ffmpeg — résolu au premier appel via get_ffmpeg()
def find_ffmpeg():
    try:
        return get_ffmpeg()
    except RuntimeError:
        return None

_ffmpeg_executable = find_ffmpeg()
if _ffmpeg_executable:
    logger.info(f"FFmpeg trouve: {_ffmpeg_executable}")
else:
    logger.warning("ATTENTION: FFmpeg non trouve - STT peut ne pas fonctionner")


def convert_audio_to_wav(input_path: str) -> str | None:
    """
    Convertit un fichier audio (OGG, MP3, etc.) en WAV 16kHz mono.
    Ceci améliore considérablement la qualité de transcription Whisper.

    Args:
        input_path: Chemin vers le fichier audio source

    Returns:
        Chemin vers le fichier WAV converti ou None si erreur
    """
    if not _ffmpeg_executable:
        logger.warning("[STT] FFmpeg non disponible - utilisation du fichier original")
        return None

    # Créer un chemin pour le fichier WAV temporaire
    wav_path = os.path.splitext(input_path)[0] + "_converted.wav"

    try:
        # Convertir en WAV 16kHz mono (optimal pour Whisper)
        cmd = [
            _ffmpeg_executable,
            '-i', input_path,
            '-ar', '16000',      # 16kHz sample rate (requis par Whisper)
            '-ac', '1',          # Mono
            '-c:a', 'pcm_s16le', # PCM 16-bit
            '-y',                # Écraser si existe
            wav_path
        ]

        result = subprocess.run(cmd, capture_output=True, timeout=10)

        if result.returncode == 0 and os.path.exists(wav_path):
            logger.info(f"[STT] Audio converti en WAV: {wav_path}")
            return wav_path
        else:
            logger.error(f"[STT] Erreur conversion audio: {result.stderr.decode() if result.stderr else 'Unknown'}")
            return None

    except subprocess.TimeoutExpired:
        logger.warning("[STT] Timeout conversion audio")
        return None
    except Exception as e:
        logger.error(f"[STT] Erreur conversion: {e}")
        return None

# Verifier si faster-whisper est disponible (import check)
WHISPER_AVAILABLE = False
WhisperModel = None

try:
    from faster_whisper import WhisperModel as _WhisperModel
    WhisperModel = _WhisperModel
    WHISPER_AVAILABLE = True
    logger.info("faster-whisper disponible")
except ImportError:
    logger.info("INFO: faster-whisper non installe - STT desactive")
    logger.info("Pour activer: pip install faster-whisper")


def is_whisper_enabled() -> bool:
    """Combine import disponible + flag `ENABLE_WHISPER` (issue #42).

    Lecture lazy de `get_settings().enable_whisper` à chaque appel pour
    permettre le monkeypatch en tests et la prise en compte d'un éventuel
    rechargement de config sans redémarrage.

    Cette fonction est utilisée par les endpoints/services qui doivent
    respecter le flag (ex: stt.py router 503 si désactivé). Le constant
    `WHISPER_AVAILABLE` reste à la valeur import-time pour la rétrocompat
    des tests existants qui le monkeypatchent directement.
    """
    if not WHISPER_AVAILABLE:
        return False
    try:
        from app.config import get_settings
        return get_settings().enable_whisper
    except Exception:
        return WHISPER_AVAILABLE

# Modele Faster-Whisper (constante de configuration)
# Note: "large-v3-turbo" est 6-8x plus rapide que large-v3, précision équivalente à large-v2
_MODEL_NAME = "large-v3-turbo"

# Migration ADR-0011 Phase 2 : Whisper passe par ModelRegistry (lock thread-safe,
# unload dispo, comportement uniforme avec NeMo / TTS).
from app.services.model_registry import registry


def _load_whisper():
    """Loader Faster-Whisper appelé par ModelRegistry.

    Configuration optimisée pour CPU Windows :
      - compute_type=int8 : quantification pour vitesse CPU et moins de RAM
      - device=cpu : compatibilité maximale
      - cpu_threads=4, num_workers=1 : stabilité sur CPU 8 cores
    """
    logger.info(f"Chargement du modele Faster-Whisper ({_MODEL_NAME})...")
    logger.info("(Premier chargement peut prendre 1-2 minutes pour telecharger le modele)")
    model = WhisperModel(
        _MODEL_NAME,
        device="cpu",
        compute_type="int8",
        cpu_threads=4,
        num_workers=1,
    )
    logger.info(f"Modele Faster-Whisper ({_MODEL_NAME}) charge!")
    return model


def get_whisper_model(model_name: str = None):
    """Charge le modele Faster-Whisper (lazy loading via ModelRegistry).

    L'argument `model_name` est conservé pour rétrocompatibilité de l'API
    publique mais ignoré : le modèle utilisé est `_MODEL_NAME` (constante).

    Respect du flag `ENABLE_WHISPER` (issue #42) : si False, retourne None
    immédiatement sans tenter le chargement (économise ~3 GB RAM).
    """
    if not is_whisper_enabled():
        return None
    if model_name and model_name != _MODEL_NAME:
        logger.warning(
            "[Whisper] Argument model_name=%r ignoré (modèle figé à %r depuis ADR-0011)",
            model_name, _MODEL_NAME,
        )
    return registry.get("whisper", loader=_load_whisper)


# Prompt initial pour guider Faster-Whisper : aide à reconnaître les termes
# agricoles et noms de villes ivoiriennes (contexte WOURI).
_WHISPER_INITIAL_PROMPT = (
    "Transcription français Côte d'Ivoire, contexte agricole. "
    "Villes: Ferkessédougou, Korhogo, Bouaké, Yamoussoukro, Abidjan, "
    "San-Pedro, Daloa, Divo, Man, Gagnoa, Bonoua, Soubré, Abengourou. "
    "Cultures: banane, manioc, maïs, riz, cacao, café, igname, arachide, "
    "palmier, hévéa, anacarde, coton, tomate, aubergine, piment, oignon, gombo. "
    "Termes agricoles: planter, cultiver, récolter, semer, période, saison, "
    "pluie, irrigation, engrais, pesticide, rendement, parcelle, tubercule."
)


def _collect_segments(segments) -> tuple[list[dict], str]:
    """Matérialise les segments Faster-Whisper (générateur) en liste + texte concaténé."""
    all_segments = []
    transcribed_texts = []
    for segment in segments:
        all_segments.append({
            "start": segment.start,
            "end": segment.end,
            "text": segment.text.strip()
        })
        transcribed_texts.append(segment.text.strip())
    return all_segments, " ".join(transcribed_texts).strip()


def _postprocess_transcription(transcribed_text: str, info, all_segments: list[dict]) -> dict | None:
    """Corrige le texte, filtre les hallucinations, détecte le dioula et construit
    le résultat. Retourne None si le texte est jugé être une hallucination."""
    # Corriger les termes agricoles mal transcrits (AVANT les villes)
    transcribed_text = correct_agricultural_terms(transcribed_text)
    logger.info(f"[Faster-Whisper] Après correction agricole: '{transcribed_text}'")

    # Corriger les noms de villes mal transcrits
    transcribed_text = correct_city_names(transcribed_text)
    logger.info(f"[Faster-Whisper] Après correction villes: '{transcribed_text}'")

    # Vérifier si le résultat semble être une hallucination
    if is_likely_hallucination(transcribed_text):
        logger.warning(f"[Faster-Whisper] Détection d'hallucination possible, texte ignoré")
        return None

    # Détecter si l'audio était probablement en Dioula
    likely_dioula = is_likely_dioula_input(transcribed_text, info.language_probability)
    if likely_dioula:
        logger.warning(f"[Faster-Whisper] ATTENTION: Audio probablement en Dioula, transcription peut être incorrecte")

    return {
        "text": transcribed_text,
        "language": info.language,
        "language_probability": info.language_probability,
        "likely_dioula_input": likely_dioula,
        "segments": all_segments
    }


def transcribe_audio(audio_path: str, language: str = "fr") -> dict | None:
    """
    Transcrit un fichier audio en texte avec Faster-Whisper.

    Args:
        audio_path: Chemin vers le fichier audio (mp3, wav, ogg, etc.)
        language: Code langue (fr, en, bam, etc.) ou None pour detection auto

    Returns:
        dict avec 'text', 'language', 'segments' ou None si erreur
    """
    if not WHISPER_AVAILABLE:
        return None

    if not os.path.exists(audio_path):
        logger.error(f"Fichier audio non trouve: {audio_path}")
        return None

    # Convertir l'audio en WAV pour une meilleure qualité
    wav_path = None
    transcribe_path = audio_path

    try:
        # Ne convertir que les formats problématiques
        formats_needing_conversion = ['.mp3', '.m4a', '.flac', '.aac']
        if any(audio_path.lower().endswith(f) for f in formats_needing_conversion):
            wav_path = convert_audio_to_wav(audio_path)
            if wav_path and os.path.exists(wav_path):
                transcribe_path = wav_path
                logger.info(f"[Whisper] Fichier converti en WAV")

        model = get_whisper_model()
        if model is None:
            return None

        # Transcrire avec Faster-Whisper
        logger.info(f"[Faster-Whisper] Transcription avec modele {_MODEL_NAME}")
        logger.info(f"[Faster-Whisper] Fichier: {transcribe_path}")

        # Configuration optimisée pour vitesse et précision
        segments, info = model.transcribe(
            transcribe_path,
            language="fr",           # Forcer le français
            task="transcribe",
            beam_size=2,             # Réduit pour vitesse (5 -> 2)
            best_of=1,               # Pas de sampling multiple
            patience=1.0,            # Patience standard
            temperature=0.0,         # Pas de sampling (déterministe)
            compression_ratio_threshold=2.4,
            log_prob_threshold=-1.0,
            no_speech_threshold=0.6,
            condition_on_previous_text=False,  # Éviter les hallucinations
            initial_prompt=_WHISPER_INITIAL_PROMPT,
            vad_filter=True,         # Filtrage VAD pour ignorer le silence
            vad_parameters={
                "min_silence_duration_ms": 500,  # Silence min 500ms
                "speech_pad_ms": 200             # Padding autour de la parole
            }
        )

        all_segments, transcribed_text = _collect_segments(segments)
        logger.info(f"[Faster-Whisper] Résultat brut: '{transcribed_text}'")
        logger.info(f"[Faster-Whisper] Langue détectée: {info.language} (prob: {info.language_probability:.2f})")
        logger.info(f"[Faster-Whisper] Durée audio: {info.duration:.1f}s")

        return _postprocess_transcription(transcribed_text, info, all_segments)

    except Exception as e:
        logger.error(f"Erreur transcription Faster-Whisper: {e}", exc_info=True)
        return None

    finally:
        # Nettoyer le fichier WAV temporaire
        if wav_path and os.path.exists(wav_path):
            try:
                os.remove(wav_path)
            except Exception:
                pass


def correct_agricultural_terms(text: str) -> str:
    """Corrige les termes agricoles mal transcrits par Whisper.

    Le dictionnaire est externalise dans
    app/data/stt_whisper_corrections/agriculture.json pour permettre aux
    contributeurs non-Python (linguistes, agronomes) de l'enrichir.
    """
    return _apply_corrections(text, _load_corrections("agriculture"), "agricole")


def correct_city_names(text: str) -> str:
    """Corrige les noms de villes ivoiriennes mal transcrits par Whisper.

    Le dictionnaire est externalise dans
    `app/data/stt_whisper_corrections/cities.json` pour permettre aux
    contributeurs non-Python de l'enrichir sans toucher le code.
    """
    return _apply_corrections(text, _load_corrections("cities"), "ville")


async def transcribe_audio_bytes(audio_bytes: bytes, filename: str = "audio.wav", language: str = "fr") -> dict | None:
    """
    Transcrit des bytes audio en texte.

    Args:
        audio_bytes: Contenu audio en bytes
        filename: Nom du fichier (pour determiner l'extension)
        language: Code langue

    Returns:
        dict avec 'text', 'language', 'segments' ou None si erreur
    """
    if not WHISPER_AVAILABLE or not audio_bytes:
        return None

    # Determiner l'extension
    ext = os.path.splitext(filename)[1] or ".wav"

    # Sauvegarder temporairement
    temp_path = os.path.join(tempfile.gettempdir(), f"whisper_{uuid.uuid4()}{ext}")

    # Dump debug OPT-IN uniquement (fix PII audit 2026-07-21) : les vocaux
    # utilisateurs sont des donnees personnelles (conformite ARTCI). Avant ce
    # fix, CHAQUE vocal etait copie inconditionnellement dans un dossier
    # jamais nettoye. Desormais : aucun dump sauf si l'operateur definit
    # explicitement WOURRI_DEBUG_AUDIO_DIR (diagnostic ponctuel, a purger).
    debug_dir = os.getenv("WOURRI_DEBUG_AUDIO_DIR")

    try:
        with open(temp_path, "wb") as f:
            f.write(audio_bytes)

        if debug_dir:
            os.makedirs(debug_dir, exist_ok=True)
            debug_path = os.path.join(debug_dir, f"audio_{uuid.uuid4()}{ext}")
            with open(debug_path, "wb") as f:
                f.write(audio_bytes)
            logger.info(f"[STT DEBUG] Audio sauvegarde: {debug_path} ({len(audio_bytes)} bytes)")

        result = await asyncio.to_thread(transcribe_audio, temp_path, language)

        # Log longueur seulement, pas le contenu (discipline PII Sprint H.1b :
        # la transcription est de la parole utilisateur en clair)
        if result:
            logger.info(f"[STT] Transcription OK ({len(result['text'])} chars)")
        else:
            logger.warning("[STT] Transcription echouee (None)")

        return result

    finally:
        # Nettoyer le fichier temporaire
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass


def check_whisper_status() -> dict:
    """Verifie le statut de Faster-Whisper"""
    return {
        "whisper_available": WHISPER_AVAILABLE,
        "model_loaded": registry.is_loaded("whisper"),
        "model_name": _MODEL_NAME,
        "engine": "faster-whisper (CTranslate2)",
        "supported_languages": ["fr", "en", "bam", "wo", "ff"]  # Langues principales
    }
