"""
WOURI - TTS Bambara (Hugging Face)
100% GRATUIT - facebook/mms-tts-bam

NOTE: Necessite torch, transformers, scipy (environ 2GB)
Pour installer: pip install torch transformers scipy pydub

Système de traduction amélioré:
- Prétraitement du texte français (simplification, segmentation)
- Traduction par phrases courtes pour meilleure qualité
- Post-traitement anti-répétition avancé
- Paramètres NLLB optimisés
"""
import uuid
import os
import re
import subprocess
from app.config import get_settings

settings = get_settings()

# Chemin du modele TTS Bambara local
TTS_MODEL_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "modeles_manuels"
)

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
    print("INFO: torch non installé - TTS Bambara désactivé")
    print("Pour activer: pip install torch transformers scipy")

# Cache des modèles
_tts_model = None
_tts_tokenizer = None
_translator_model = None
_translator_tokenizer = None


def get_tts_model():
    """Charge le modele TTS Bambara (lazy loading)"""
    global _tts_model, _tts_tokenizer

    if not TORCH_AVAILABLE:
        return None, None

    if _tts_model is None:
        print("Chargement du modele TTS Bambara...")
        from transformers import VitsModel, AutoTokenizer

        # Utiliser le modele local s'il existe
        if os.path.exists(TTS_MODEL_PATH) and os.path.exists(os.path.join(TTS_MODEL_PATH, "model.safetensors")):
            print(f"Utilisation du modele local: {TTS_MODEL_PATH}")
            _tts_model = VitsModel.from_pretrained(TTS_MODEL_PATH)
            _tts_tokenizer = AutoTokenizer.from_pretrained(TTS_MODEL_PATH)
        else:
            print("Telechargement depuis HuggingFace...")
            _tts_model = VitsModel.from_pretrained(settings.hf_tts_model)
            _tts_tokenizer = AutoTokenizer.from_pretrained(settings.hf_tts_model)
        print("Modele TTS Bambara charge!")

    return _tts_model, _tts_tokenizer


def get_translator():
    """Charge le modèle de traduction NLLB (lazy loading)"""
    global _translator_model, _translator_tokenizer

    if not TORCH_AVAILABLE:
        return None, None

    if _translator_model is None:
        print("Chargement du modèle de traduction (NLLB-200)...")
        from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

        _translator_tokenizer = AutoTokenizer.from_pretrained(settings.hf_translator_model)
        _translator_model = AutoModelForSeq2SeqLM.from_pretrained(settings.hf_translator_model)
        print("Modèle de traduction chargé!")

    return _translator_model, _translator_tokenizer


def preprocess_french_text(text: str) -> str:
    """
    Prétraitement du texte français pour améliorer la traduction.
    - Simplifie les phrases complexes
    - Normalise la ponctuation
    - Supprime les éléments problématiques
    """
    if not text:
        return text

    # Normaliser les espaces
    text = re.sub(r'\s+', ' ', text).strip()

    # Remplacer les guillemets et apostrophes spéciaux
    text = text.replace('"', '"').replace('"', '"')
    text = text.replace(''', "'").replace(''', "'")

    # Supprimer les parenthèses avec leur contenu (souvent problématique)
    text = re.sub(r'\([^)]*\)', '', text)

    # Supprimer les pourcentages et symboles complexes
    text = re.sub(r'\d+%', '', text)
    text = text.replace('°C', ' degrés')
    text = text.replace('°', ' degrés')

    # Simplifier les nombres avec décimales
    text = re.sub(r'(\d+)[.,](\d+)', r'\1', text)

    # Nettoyer les espaces multiples après modifications
    text = re.sub(r'\s+', ' ', text).strip()

    return text


def split_into_sentences(text: str) -> list[str]:
    """
    Divise le texte en phrases courtes pour une meilleure traduction.
    NLLB fonctionne mieux avec des phrases courtes et simples.
    """
    if not text:
        return []

    # Séparer par ponctuation finale
    sentences = re.split(r'(?<=[.!?])\s+', text)

    result = []
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue

        # Si la phrase est trop longue (> 80 caractères), la diviser
        if len(sentence) > 80:
            # Diviser par virgules ou points-virgules
            parts = re.split(r'[,;:]\s*', sentence)
            for part in parts:
                part = part.strip()
                if part and len(part) > 3:
                    result.append(part)
        else:
            result.append(sentence)

    return result


def translate_single_sentence(text: str, model, tokenizer, forced_bos_token_id) -> str:
    """Traduit une seule phrase courte avec des paramètres optimisés."""
    if not text or len(text.strip()) < 2:
        return ""

    # Dictionnaire de traductions directes pour éviter les hallucinations NLLB
    # sur les mots courts courants
    direct_translations = {
        "bonjour": "I ni ce",
        "bonsoir": "I ni wula",
        "bonne nuit": "I ni su",
        "merci": "I ni ce",
        "au revoir": "K'an bɛn",
        "oui": "Ɔwɔ",
        "non": "Ayi",
        "salut": "I ni ce",
    }

    text_lower = text.lower().strip().rstrip('.!?,;:')
    if text_lower in direct_translations:
        return direct_translations[text_lower]

    inputs = tokenizer(
        text,
        return_tensors="pt",
        padding=True,
        truncation=True,
        max_length=128  # Phrases courtes = limite plus basse
    )

    with torch.no_grad():
        generated_tokens = model.generate(
            **inputs,
            forced_bos_token_id=forced_bos_token_id,
            max_length=80,   # Réduit pour plus de vitesse (100 -> 80)
            num_beams=1,     # Greedy decoding = plus rapide (2 -> 1)
            no_repeat_ngram_size=2,
            repetition_penalty=1.3,
            early_stopping=True,
            do_sample=False
        )

    result = tokenizer.batch_decode(generated_tokens, skip_special_tokens=True)[0]

    # Filtrer les hallucinations connues de NLLB
    hallucinations = ["bonjour bébé", "bonjour bebe", "bébé", "bebe"]
    result_lower = result.lower().strip()
    for hallucination in hallucinations:
        if result_lower.startswith(hallucination):
            # Remplacer par une salutation correcte en Bambara
            result = result_lower.replace(hallucination, "I ni ce", 1)
            result = result[0].upper() + result[1:] if result else result
            break

    return result


def clean_bambara_text(text: str) -> str:
    """
    Post-traitement avancé du texte Bambara.
    Nettoie les répétitions et améliore la fluidité.
    """
    if not text:
        return text

    # Étape 1: Supprimer les répétitions de mots consécutifs
    words = text.split()
    if len(words) < 2:
        return text

    cleaned_words = [words[0]]
    for i in range(1, len(words)):
        current = words[i].lower().strip('.,!?')
        previous = words[i-1].lower().strip('.,!?')
        if current != previous:
            cleaned_words.append(words[i])

    # Étape 2: Détecter les patterns répétitifs (bi-grams, tri-grams)
    text = ' '.join(cleaned_words)

    # Supprimer les répétitions de bi-grams (ex: "ka bo ka bo ka bo")
    for n in [3, 2]:  # Tri-grams puis bi-grams
        words = text.split()
        if len(words) < n * 2:
            continue

        cleaned = []
        i = 0
        while i < len(words):
            if i + n * 2 <= len(words):
                pattern = ' '.join(words[i:i+n])
                next_pattern = ' '.join(words[i+n:i+n*2])
                if pattern.lower() == next_pattern.lower():
                    # Répétition détectée, garder seulement une occurrence
                    cleaned.extend(words[i:i+n])
                    # Sauter toutes les répétitions
                    i += n
                    while i + n <= len(words):
                        check = ' '.join(words[i:i+n])
                        if check.lower() == pattern.lower():
                            i += n
                        else:
                            break
                else:
                    cleaned.append(words[i])
                    i += 1
            else:
                cleaned.append(words[i])
                i += 1

        text = ' '.join(cleaned)

    # Étape 3: Vérifier le ratio de mots uniques
    words = text.split()
    if len(words) > 5:
        unique_words = set(w.lower().strip('.,!?') for w in words)
        ratio = len(unique_words) / len(words)

        # Si moins de 40% de mots uniques, c'est trop répétitif
        if ratio < 0.4:
            # Garder seulement les premiers mots uniques
            seen = set()
            result_words = []
            for word in words:
                key = word.lower().strip('.,!?')
                if key not in seen or len(result_words) < 5:
                    result_words.append(word)
                    seen.add(key)
                if len(result_words) >= max(8, len(unique_words) * 2):
                    break
            text = ' '.join(result_words)

    # Étape 4: Nettoyer la ponctuation finale
    text = text.strip()
    if text and text[-1] not in '.!?':
        text += '.'

    return text


def translate_to_bambara(french_text: str) -> str:
    """
    Traduit du français vers le Bambara avec un système amélioré.

    Processus:
    1. Prétraitement du texte français
    2. Division en phrases courtes
    3. Traduction phrase par phrase
    4. Post-traitement et nettoyage
    """
    if not TORCH_AVAILABLE:
        return french_text

    model, tokenizer = get_translator()
    if model is None:
        return french_text

    # Prétraitement
    preprocessed = preprocess_french_text(french_text)
    if not preprocessed:
        return french_text

    tokenizer.src_lang = "fra_Latn"
    forced_bos_token_id = tokenizer.convert_tokens_to_ids("bam_Latn")

    # Diviser en phrases
    sentences = split_into_sentences(preprocessed)

    if not sentences:
        # Fallback: traduire le texte complet
        sentences = [preprocessed]

    # Traduire chaque phrase
    translated_parts = []
    for sentence in sentences:
        if len(sentence.strip()) < 3:
            continue

        translation = translate_single_sentence(
            sentence, model, tokenizer, forced_bos_token_id
        )

        if translation:
            # Nettoyer chaque partie traduite
            cleaned = clean_bambara_text(translation)
            if cleaned and len(cleaned) > 2:
                translated_parts.append(cleaned)

    # Assembler le résultat
    if not translated_parts:
        return french_text

    result = ' '.join(translated_parts)

    # Nettoyage final
    result = clean_bambara_text(result)

    # Log pour debug (encodage sécurisé)
    try:
        print(f"[Bambara] Traduit: {len(french_text)} chars -> {len(result)} chars")
    except UnicodeEncodeError:
        print(f"[Bambara] Traduction effectuee")

    return result


def translate_to_french(bambara_text: str) -> str:
    """Traduit du Bambara vers le Français"""
    if not TORCH_AVAILABLE:
        return bambara_text  # Retourne le texte original si pas de torch

    model, tokenizer = get_translator()
    if model is None:
        return bambara_text

    tokenizer.src_lang = "bam_Latn"

    inputs = tokenizer(
        bambara_text,
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


def find_ffmpeg():
    """Trouve le chemin de ffmpeg sur le systeme"""
    # Chemins possibles pour ffmpeg sur Windows
    possible_paths = [
        'ffmpeg',  # Dans le PATH
        r'C:\Users\USER PC\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.0.1-full_build\bin\ffmpeg.exe',
    ]

    for ffmpeg_path in possible_paths:
        try:
            result = subprocess.run([ffmpeg_path, '-version'],
                                  capture_output=True, timeout=5)
            if result.returncode == 0:
                return ffmpeg_path
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue

    return None


def convert_wav_to_ogg(wav_path: str, ogg_path: str) -> bool:
    """Convertit un fichier WAV en OGG (Opus) pour WhatsApp mobile"""
    ffmpeg_path = find_ffmpeg()

    if ffmpeg_path:
        try:
            # Utiliser ffmpeg pour la conversion
            result = subprocess.run([
                ffmpeg_path, '-y', '-i', wav_path,
                '-c:a', 'libopus', '-b:a', '64k',
                '-vbr', 'on', '-compression_level', '10',
                ogg_path
            ], capture_output=True, text=True, timeout=30)

            if result.returncode == 0 and os.path.exists(ogg_path):
                # Supprimer le fichier WAV temporaire
                os.remove(wav_path)
                print("Conversion WAV -> OGG reussie avec ffmpeg")
                return True
            else:
                print(f"Erreur ffmpeg: {result.stderr}")
        except Exception as e:
            print(f"Erreur ffmpeg: {e}")

    # Fallback: essayer avec pydub
    print("Essai avec pydub...")
    try:
        from pydub import AudioSegment
        # Configurer le chemin ffmpeg pour pydub
        if ffmpeg_path and ffmpeg_path != 'ffmpeg':
            AudioSegment.converter = ffmpeg_path
            ffprobe_path = ffmpeg_path.replace('ffmpeg.exe', 'ffprobe.exe')
            AudioSegment.ffprobe = ffprobe_path

        audio = AudioSegment.from_wav(wav_path)
        audio.export(ogg_path, format="ogg", codec="libopus", bitrate="64k")
        os.remove(wav_path)
        print("Conversion WAV -> OGG reussie avec pydub")
        return True
    except Exception as e:
        print(f"Erreur pydub: {e}")

    return False


def synthesize_bambara_text(bambara_text: str) -> str | None:
    """Génère un fichier audio OGG (Opus) à partir de texte Bambara"""
    if not TORCH_AVAILABLE or not bambara_text:
        return None

    try:
        model, tokenizer = get_tts_model()
        if model is None:
            return None

        inputs = tokenizer(bambara_text, return_tensors="pt")

        with torch.no_grad():
            output = model(**inputs).waveform

        waveform = output.squeeze().cpu().numpy()
        waveform = waveform / np.max(np.abs(waveform))
        waveform = (waveform * 32767).astype(np.int16)

        file_id = uuid.uuid4()
        wav_filename = f"bm_{file_id}.wav"
        ogg_filename = f"bm_{file_id}.ogg"
        wav_filepath = os.path.join(settings.audio_output_dir, wav_filename)
        ogg_filepath = os.path.join(settings.audio_output_dir, ogg_filename)
        os.makedirs(settings.audio_output_dir, exist_ok=True)

        # Ecrire le WAV temporaire
        wav.write(wav_filepath, rate=model.config.sampling_rate, data=waveform)

        # Convertir en OGG pour WhatsApp mobile
        if convert_wav_to_ogg(wav_filepath, ogg_filepath):
            if os.path.exists(ogg_filepath) and os.path.getsize(ogg_filepath) > 0:
                return f"/static/audio/{ogg_filename}"

        # Fallback: retourner le WAV si conversion echoue
        if os.path.exists(wav_filepath) and os.path.getsize(wav_filepath) > 0:
            print("Fallback: utilisation du fichier WAV")
            return f"/static/audio/{wav_filename}"

    except Exception as e:
        print(f"Erreur TTS Bambara: {e}")

    return None


async def synthesize_bambara(french_text: str) -> tuple[str | None, str | None]:
    """Traduit du français vers le Bambara et génère l'audio"""
    if not TORCH_AVAILABLE or not french_text:
        return None, None

    try:
        bambara_text = translate_to_bambara(french_text)
        # Utiliser encode/decode pour éviter les erreurs d'encodage Windows
        try:
            print(f"Traduction: {french_text} -> {bambara_text}")
        except UnicodeEncodeError:
            print(f"Traduction effectuee (caracteres speciaux Bambara)")

        audio_url = synthesize_bambara_text(bambara_text)
        return audio_url, bambara_text

    except Exception as e:
        try:
            print(f"Erreur synthese Bambara: {e}")
        except UnicodeEncodeError:
            print("Erreur synthese Bambara (erreur encodage)")
        return None, None


def check_models_status() -> dict:
    """Vérifie le statut des modèles Hugging Face"""
    return {
        "torch_available": TORCH_AVAILABLE,
        "tts_loaded": _tts_model is not None,
        "translator_loaded": _translator_model is not None,
        "tts_model": settings.hf_tts_model,
        "translator_model": settings.hf_translator_model
    }
