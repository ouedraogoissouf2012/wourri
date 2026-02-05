"""
WOURI - ASR (Automatic Speech Recognition) pour langues ivoiriennes
Utilise Facebook MMS-1B-ALL pour la reconnaissance vocale
VERSION: Utilise torchaudio.load() directement
"""
import os
import uuid
import subprocess
from typing import Optional

from app.config import get_settings

settings = get_settings()

# Verifier les dependances
TORCH_AVAILABLE = False
TORCHAUDIO_AVAILABLE = False
torch = None
torchaudio = None

try:
    import torch as _torch
    torch = _torch
    TORCH_AVAILABLE = True
    print(f"[ASR] torch {torch.__version__} disponible")
except ImportError:
    print("[ASR] torch non installe - ASR desactive")

try:
    import torchaudio as _torchaudio
    torchaudio = _torchaudio
    TORCHAUDIO_AVAILABLE = True
    print(f"[ASR] torchaudio {torchaudio.__version__} disponible")
except ImportError:
    print("[ASR] torchaudio non installe")

# Langues ivoiriennes supportees pour ASR
IVORIAN_ASR_LANGUAGES = {
    "bam": ("Bambara/Dioula", "bam"),
    "ati": ("Attie", "ati"),
    "dyi": ("Senoufo Djimini", "dyi"),
    "myk": ("Senoufo Mamara", "myk"),
    "gud": ("Dida Yocoboue", "gud"),
    "adj": ("Adioukrou", "adj"),
    "dnj": ("Dan/Yacouba", "dnj"),
    "wob": ("Wobe", "wob"),
}

# Cache du modele ASR
_asr_model = None
_asr_processor = None
_current_language = None


def get_asr_model(language_code: str = "bam"):
    """Charge le modele ASR MMS (lazy loading)"""
    global _asr_model, _asr_processor, _current_language

    if not TORCH_AVAILABLE:
        print("[ASR] torch non disponible")
        return None, None

    # Recharger si la langue change
    if _asr_model is None or _current_language != language_code:
        print(f"[ASR] Chargement du modele ASR pour {language_code}...")

        try:
            from transformers import Wav2Vec2ForCTC, Wav2Vec2Processor

            model_id = "facebook/mms-1b-all"

            _asr_processor = Wav2Vec2Processor.from_pretrained(model_id)
            _asr_model = Wav2Vec2ForCTC.from_pretrained(model_id)

            # Configurer la langue cible
            _asr_processor.tokenizer.set_target_lang(language_code)
            _asr_model.load_adapter(language_code)

            _current_language = language_code
            print(f"[ASR] Modele charge pour {IVORIAN_ASR_LANGUAGES.get(language_code, (language_code,))[0]}!")

        except Exception as e:
            print(f"[ASR] Erreur chargement modele: {e}")
            import traceback
            traceback.print_exc()
            return None, None

    return _asr_model, _asr_processor


def convert_to_wav_16k(input_path: str, output_path: str) -> bool:
    """Convertit un fichier audio en WAV 16kHz mono avec ffmpeg"""
    ffmpeg_paths = [
        'ffmpeg',
        r'C:\Users\USER PC\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.0.1-full_build\bin\ffmpeg.exe',
    ]

    ffmpeg_path = None
    for path in ffmpeg_paths:
        try:
            result = subprocess.run([path, '-version'], capture_output=True, timeout=5)
            if result.returncode == 0:
                ffmpeg_path = path
                break
        except:
            continue

    if not ffmpeg_path:
        print("[ASR] FFmpeg non trouve")
        return False

    try:
        cmd = [
            ffmpeg_path, '-y', '-i', input_path,
            '-ar', '16000',
            '-ac', '1',
            '-c:a', 'pcm_s16le',
            output_path
        ]
        result = subprocess.run(cmd, capture_output=True, timeout=30)
        if result.returncode == 0 and os.path.exists(output_path):
            print(f"[ASR] Converti en WAV 16kHz: {output_path}")
            return True
        else:
            stderr = result.stderr.decode() if result.stderr else 'Unknown error'
            print(f"[ASR] Erreur ffmpeg: {stderr[:200]}")
            return False
    except Exception as e:
        print(f"[ASR] Erreur conversion: {e}")
        return False


def load_audio_wav(audio_path: str):
    """Charge un fichier WAV et retourne le waveform numpy array"""
    try:
        # Methode 1: Utiliser torchaudio si disponible
        if TORCHAUDIO_AVAILABLE:
            print(f"[ASR] Chargement avec torchaudio: {audio_path}")
            waveform, sample_rate = torchaudio.load(audio_path)
            # Convertir en numpy
            waveform = waveform.squeeze().numpy()
            return waveform, sample_rate
    except Exception as e:
        print(f"[ASR] Erreur torchaudio: {e}")

    # Methode 2: Utiliser soundfile comme fallback
    try:
        import soundfile as sf
        print(f"[ASR] Chargement avec soundfile: {audio_path}")
        waveform, sample_rate = sf.read(audio_path, dtype='float32')
        return waveform, sample_rate
    except Exception as e:
        print(f"[ASR] Erreur soundfile: {e}")

    # Methode 3: Utiliser scipy comme dernier recours
    try:
        from scipy.io import wavfile
        print(f"[ASR] Chargement avec scipy: {audio_path}")
        sample_rate, waveform = wavfile.read(audio_path)
        waveform = waveform.astype('float32') / 32768.0  # Normaliser
        return waveform, sample_rate
    except Exception as e:
        print(f"[ASR] Erreur scipy: {e}")

    return None, None


def transcribe_audio(audio_path: str, language_code: str = "bam") -> Optional[str]:
    """Transcrit un fichier audio WAV en texte"""
    if not TORCH_AVAILABLE:
        print("[ASR] torch non disponible")
        return None

    if language_code not in IVORIAN_ASR_LANGUAGES:
        print(f"[ASR] Langue {language_code} non supportee")
        return None

    if not os.path.exists(audio_path):
        print(f"[ASR] Fichier non trouve: {audio_path}")
        return None

    try:
        # Charger le modele
        model, processor = get_asr_model(language_code)
        if model is None or processor is None:
            print("[ASR] Modele non charge")
            return None

        # Charger l'audio
        waveform, sample_rate = load_audio_wav(audio_path)
        if waveform is None:
            print("[ASR] Impossible de charger l'audio")
            return None

        print(f"[ASR] Audio: {len(waveform)} samples, {sample_rate}Hz")

        # Resampler si necessaire (MMS requiert 16kHz)
        if sample_rate != 16000:
            from scipy import signal
            import numpy as np
            num_samples = int(len(waveform) * 16000 / sample_rate)
            waveform = signal.resample(waveform, num_samples).astype(np.float32)
            print(f"[ASR] Resample {sample_rate}Hz -> 16000Hz")

        # Preparer les inputs pour le modele
        inputs = processor(
            waveform,
            sampling_rate=16000,
            return_tensors="pt"
        )

        # Inference
        print("[ASR] Inference...")
        with torch.no_grad():
            logits = model(**inputs).logits

        # Decoder
        predicted_ids = torch.argmax(logits, dim=-1)[0]
        transcription = processor.decode(predicted_ids)

        print(f"[ASR] Transcription: '{transcription}'")
        return transcription.strip()

    except Exception as e:
        print(f"[ASR] Erreur transcription: {e}")
        import traceback
        traceback.print_exc()
        return None


async def transcribe_audio_bytes(audio_bytes: bytes, language_code: str = "bam",
                                  file_extension: str = "ogg") -> Optional[str]:
    """Transcrit des bytes audio en texte"""
    if not TORCH_AVAILABLE:
        print("[ASR] torch non disponible")
        return None

    # Creer dossier temporaire
    temp_dir = settings.audio_output_dir
    os.makedirs(temp_dir, exist_ok=True)

    temp_id = uuid.uuid4()
    temp_path = os.path.join(temp_dir, f"asr_{temp_id}.{file_extension}")
    wav_path = os.path.join(temp_dir, f"asr_{temp_id}.wav")

    try:
        # Sauvegarder le fichier audio
        with open(temp_path, "wb") as f:
            f.write(audio_bytes)
        print(f"[ASR] Audio sauvegarde: {temp_path} ({len(audio_bytes)} bytes)")

        # Toujours convertir en WAV 16kHz avec ffmpeg
        if not convert_to_wav_16k(temp_path, wav_path):
            print("[ASR] Echec conversion WAV")
            return None

        # Transcrire le WAV
        result = transcribe_audio(wav_path, language_code)
        return result

    finally:
        # Nettoyer
        for path in [temp_path, wav_path]:
            if os.path.exists(path):
                try:
                    os.remove(path)
                except:
                    pass


def get_supported_asr_languages() -> dict:
    """Retourne la liste des langues ASR supportees"""
    return {code: name for code, (name, _) in IVORIAN_ASR_LANGUAGES.items()}


def check_asr_status() -> dict:
    """Verifie le statut du service ASR"""
    return {
        "torch_available": TORCH_AVAILABLE,
        "torchaudio_available": TORCHAUDIO_AVAILABLE,
        "model_loaded": _asr_model is not None,
        "current_language": _current_language,
        "supported_languages": list(IVORIAN_ASR_LANGUAGES.keys())
    }
