"""
WOURI - ASR Bambara via Soloni (sherpa-onnx)
Modele: RobotsMali/soloni-114m-tdt-ctc-v0
NOTE: chemins sans caracteres speciaux (C:/soloni/) requis par le C++ ORT
"""
import os
import uuid
import subprocess
from typing import Optional
import numpy as np

# Chemins du modele (sans accents - requis par sherpa-onnx C++)
SOLONI_MODEL_PATH  = r"C:\soloni\soloni_nemo_ctc.onnx"
SOLONI_TOKENS_PATH = r"C:\soloni\tokens.txt"

SHERPA_AVAILABLE = False
sherpa_onnx = None

try:
    import sherpa_onnx as _sherpa
    sherpa_onnx = _sherpa
    SHERPA_AVAILABLE = True
    print(f"[ASR-SOLONI] sherpa-onnx {sherpa_onnx.__version__} disponible")
except ImportError:
    print("[ASR-SOLONI] sherpa-onnx non installe - ASR Bambara desactive")

# Singleton recognizer
_recognizer = None


def get_soloni_recognizer():
    """Charge le recognizer Soloni (lazy loading, singleton)"""
    global _recognizer

    if not SHERPA_AVAILABLE:
        return None

    if _recognizer is not None:
        return _recognizer

    if not os.path.exists(SOLONI_MODEL_PATH):
        print(f"[ASR-SOLONI] Modele non trouve: {SOLONI_MODEL_PATH}")
        print(f"[ASR-SOLONI] Lancer soloni_patch_meta.py pour preparer le modele")
        return None

    if not os.path.exists(SOLONI_TOKENS_PATH):
        print(f"[ASR-SOLONI] Tokens non trouves: {SOLONI_TOKENS_PATH}")
        return None

    try:
        print("[ASR-SOLONI] Chargement recognizer Soloni...")
        _recognizer = sherpa_onnx.OfflineRecognizer.from_nemo_ctc(
            model=SOLONI_MODEL_PATH,
            tokens=SOLONI_TOKENS_PATH,
            num_threads=2,
            sample_rate=16000,
            feature_dim=80,
            decoding_method='greedy_search',
            debug=False,
            provider='cpu'
        )
        print("[ASR-SOLONI] Recognizer charge!")
        return _recognizer
    except Exception as e:
        print(f"[ASR-SOLONI] Erreur chargement: {e}")
        return None


def transcribe_numpy(audio: np.ndarray, sample_rate: int = 16000) -> Optional[str]:
    """Transcrit un array numpy (float32, mono) en texte bambara"""
    recognizer = get_soloni_recognizer()
    if recognizer is None:
        return None

    try:
        audio = audio.astype(np.float32)
        if len(audio.shape) > 1:
            audio = audio[:, 0]  # mono

        if sample_rate != 16000:
            from scipy import signal
            audio = signal.resample(audio, int(len(audio) * 16000 / sample_rate)).astype(np.float32)

        stream = recognizer.create_stream()
        stream.accept_waveform(16000, audio)
        recognizer.decode_stream(stream)

        return stream.result.text.strip()

    except Exception as e:
        print(f"[ASR-SOLONI] Erreur inference: {e}")
        return None


def _convert_to_wav_16k(input_path: str, output_path: str) -> bool:
    """Convertit en WAV 16kHz mono via ffmpeg"""
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
        print("[ASR-SOLONI] FFmpeg non trouve")
        return False

    try:
        cmd = [
            ffmpeg_path, '-y', '-i', input_path,
            '-ar', '16000', '-ac', '1', '-c:a', 'pcm_s16le',
            output_path
        ]
        result = subprocess.run(cmd, capture_output=True, timeout=30)
        return result.returncode == 0 and os.path.exists(output_path)
    except Exception as e:
        print(f"[ASR-SOLONI] Erreur ffmpeg: {e}")
        return False


async def transcribe_bambara_bytes(audio_bytes: bytes, file_extension: str = "ogg") -> Optional[str]:
    """Point d'entree principal: bytes audio -> texte bambara"""
    from app.config import get_settings
    settings = get_settings()

    temp_dir = settings.audio_output_dir
    os.makedirs(temp_dir, exist_ok=True)

    temp_id = uuid.uuid4()
    temp_path = os.path.join(temp_dir, f"soloni_{temp_id}.{file_extension}")
    wav_path  = os.path.join(temp_dir, f"soloni_{temp_id}.wav")

    try:
        with open(temp_path, "wb") as f:
            f.write(audio_bytes)

        if not _convert_to_wav_16k(temp_path, wav_path):
            print("[ASR-SOLONI] Echec conversion WAV")
            return None

        # Charger le WAV
        audio, sr = None, None
        try:
            import soundfile as sf
            audio, sr = sf.read(wav_path, dtype='float32')
        except Exception:
            try:
                import torchaudio
                waveform, sr = torchaudio.load(wav_path)
                audio = waveform.squeeze().numpy()
            except Exception as e:
                print(f"[ASR-SOLONI] Impossible de charger l'audio: {e}")
                return None

        if audio is None:
            return None

        result = transcribe_numpy(audio, sr)
        print(f"[ASR-SOLONI] Transcription: '{result}'")
        return result

    finally:
        for path in [temp_path, wav_path]:
            if os.path.exists(path):
                try:
                    os.remove(path)
                except:
                    pass


def check_soloni_status() -> dict:
    return {
        "sherpa_available": SHERPA_AVAILABLE,
        "model_exists": os.path.exists(SOLONI_MODEL_PATH),
        "tokens_exists": os.path.exists(SOLONI_TOKENS_PATH),
        "recognizer_loaded": _recognizer is not None,
        "model_path": SOLONI_MODEL_PATH,
    }
