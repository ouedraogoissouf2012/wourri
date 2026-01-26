"""
WOURI - ASR (Automatic Speech Recognition) pour langues ivoiriennes
Utilise Facebook MMS-1B-ALL pour la reconnaissance vocale

Langues supportees:
- bam: Bambara/Dioula
- ati: Attie
- dyi: Senoufo Djimini
- myk: Senoufo Mamara
- gud: Dida Yocoboue
- adj: Adioukrou
- dnj: Dan/Yacouba
- wob: Wobe
"""
import os
import uuid
import subprocess
from typing import Optional, Tuple
from app.config import get_settings

settings = get_settings()

# Verifier si torch est disponible
TORCH_AVAILABLE = False
torch = None
torchaudio = None

try:
    import torch as _torch
    torch = _torch
    TORCH_AVAILABLE = True
except ImportError:
    print("INFO: torch non installe - ASR desactive")

try:
    import torchaudio as _torchaudio
    torchaudio = _torchaudio
except ImportError:
    print("INFO: torchaudio non installe - ASR desactive")
    TORCH_AVAILABLE = False

# Langues ivoiriennes supportees pour ASR
# Format: code -> (nom, code_mms)
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
        return None, None

    # Recharger si la langue change
    if _asr_model is None or _current_language != language_code:
        print(f"Chargement du modele ASR pour {language_code}...")

        from transformers import Wav2Vec2ForCTC, AutoProcessor

        model_id = "facebook/mms-1b-all"

        _asr_processor = AutoProcessor.from_pretrained(model_id)
        _asr_model = Wav2Vec2ForCTC.from_pretrained(model_id)

        # Configurer la langue cible
        _asr_processor.tokenizer.set_target_lang(language_code)
        _asr_model.load_adapter(language_code)

        _current_language = language_code
        print(f"Modele ASR charge pour {IVORIAN_ASR_LANGUAGES.get(language_code, (language_code,))[0]}!")

    return _asr_model, _asr_processor


def transcribe_audio(audio_path: str, language_code: str = "bam") -> Optional[str]:
    """
    Transcrit un fichier audio en texte

    Args:
        audio_path: Chemin vers le fichier audio (WAV, OGG, MP3, etc.)
        language_code: Code de la langue (bam, ati, dyi, myk, gud, adj, dnj, wob)

    Returns:
        Texte transcrit ou None si erreur
    """
    if not TORCH_AVAILABLE or not torchaudio:
        print("ASR non disponible: torch ou torchaudio manquant")
        return None

    if language_code not in IVORIAN_ASR_LANGUAGES:
        print(f"Langue {language_code} non supportee pour ASR")
        return None

    if not os.path.exists(audio_path):
        print(f"Fichier audio non trouve: {audio_path}")
        return None

    try:
        model, processor = get_asr_model(language_code)
        if model is None:
            return None

        # Charger l'audio
        waveform, sample_rate = torchaudio.load(audio_path)

        # Convertir en mono si stereo
        if waveform.shape[0] > 1:
            waveform = torch.mean(waveform, dim=0, keepdim=True)

        # Resampler a 16kHz si necessaire (requis par MMS)
        if sample_rate != 16000:
            resampler = torchaudio.transforms.Resample(sample_rate, 16000)
            waveform = resampler(waveform)

        # Preparer les inputs
        inputs = processor(
            waveform.squeeze().numpy(),
            sampling_rate=16000,
            return_tensors="pt"
        )

        # Inference
        with torch.no_grad():
            outputs = model(**inputs).logits

        # Decoder
        ids = torch.argmax(outputs, dim=-1)[0]
        transcription = processor.decode(ids)

        return transcription.strip()

    except Exception as e:
        print(f"Erreur ASR: {e}")
        return None


async def transcribe_audio_bytes(audio_bytes: bytes, language_code: str = "bam",
                                  file_extension: str = "ogg") -> Optional[str]:
    """
    Transcrit des bytes audio en texte

    Args:
        audio_bytes: Contenu audio en bytes
        language_code: Code de la langue
        file_extension: Extension du fichier (ogg, wav, mp3)

    Returns:
        Texte transcrit ou None si erreur
    """
    if not TORCH_AVAILABLE:
        return None

    # Sauvegarder temporairement le fichier
    temp_dir = settings.audio_output_dir
    os.makedirs(temp_dir, exist_ok=True)

    temp_filename = f"asr_temp_{uuid.uuid4()}.{file_extension}"
    temp_path = os.path.join(temp_dir, temp_filename)

    try:
        # Ecrire le fichier temporaire
        with open(temp_path, "wb") as f:
            f.write(audio_bytes)

        # Transcrire
        result = transcribe_audio(temp_path, language_code)

        return result

    finally:
        # Nettoyer le fichier temporaire
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except:
                pass


def get_supported_asr_languages() -> dict:
    """Retourne la liste des langues ASR supportees"""
    return {code: name for code, (name, _) in IVORIAN_ASR_LANGUAGES.items()}


def check_asr_status() -> dict:
    """Verifie le statut du service ASR"""
    return {
        "torch_available": TORCH_AVAILABLE,
        "torchaudio_available": torchaudio is not None,
        "model_loaded": _asr_model is not None,
        "current_language": _current_language,
        "supported_languages": list(IVORIAN_ASR_LANGUAGES.keys())
    }
