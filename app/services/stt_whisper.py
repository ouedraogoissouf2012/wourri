"""
WOURI - Speech-to-Text avec Faster-Whisper
Utilise CTranslate2 pour des performances 4x plus rapides

NOTE: Necessite faster-whisper
Pour installer: pip install faster-whisper
"""
import os

# Désactiver les symlinks sur Windows (évite les erreurs de permission)
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
os.environ["HF_HUB_DISABLE_SYMLINKS"] = "1"

import uuid
import tempfile
import subprocess
from app.config import get_settings
from app.services._ffmpeg import get_ffmpeg

settings = get_settings()

# Chemin ffmpeg — résolu au premier appel via get_ffmpeg()
def find_ffmpeg():
    try:
        return get_ffmpeg()
    except RuntimeError:
        return None

_ffmpeg_executable = find_ffmpeg()
if _ffmpeg_executable:
    print(f"FFmpeg trouve: {_ffmpeg_executable}")
else:
    print("ATTENTION: FFmpeg non trouve - STT peut ne pas fonctionner")


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
        print("[STT] FFmpeg non disponible - utilisation du fichier original")
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
            print(f"[STT] Audio converti en WAV: {wav_path}")
            return wav_path
        else:
            print(f"[STT] Erreur conversion audio: {result.stderr.decode() if result.stderr else 'Unknown'}")
            return None

    except subprocess.TimeoutExpired:
        print("[STT] Timeout conversion audio")
        return None
    except Exception as e:
        print(f"[STT] Erreur conversion: {e}")
        return None

# Verifier si faster-whisper est disponible
WHISPER_AVAILABLE = False
WhisperModel = None

try:
    from faster_whisper import WhisperModel as _WhisperModel
    WhisperModel = _WhisperModel
    WHISPER_AVAILABLE = True
    print("faster-whisper disponible")
except ImportError:
    print("INFO: faster-whisper non installe - STT desactive")
    print("Pour activer: pip install faster-whisper")

# Cache du modele
_whisper_model = None
_model_name = "large-v3-turbo"  # Modèle ultra-rapide et précis (Oct 2024)
# Note: "large-v3-turbo" est 6-8x plus rapide que large-v3, précision équivalente à large-v2


def get_whisper_model(model_name: str = None):
    """Charge le modele Faster-Whisper (lazy loading)"""
    global _whisper_model, _model_name

    if not WHISPER_AVAILABLE:
        return None

    if model_name:
        _model_name = model_name

    if _whisper_model is None:
        print(f"Chargement du modele Faster-Whisper ({_model_name})...")
        print("(Premier chargement peut prendre 1-2 minutes pour telecharger le modele)")

        # Configuration optimisée pour CPU Windows
        # compute_type: int8 pour CPU (plus rapide et moins de RAM)
        # device: cpu pour compatibilité maximale
        _whisper_model = WhisperModel(
            _model_name,
            device="cpu",
            compute_type="int8",  # Quantification int8 pour vitesse CPU
            cpu_threads=4,        # Utiliser 4 threads CPU
            num_workers=1         # 1 worker pour la stabilité
        )
        print(f"Modele Faster-Whisper ({_model_name}) charge!")

    return _whisper_model


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
        print(f"Fichier audio non trouve: {audio_path}")
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
                print(f"[Whisper] Fichier converti en WAV")

        model = get_whisper_model()
        if model is None:
            return None

        # Prompt initial pour guider la reconnaissance
        # Ce prompt aide Whisper à mieux reconnaître les termes agricoles et villes ivoiriennes
        initial_prompt = (
            "Transcription français Côte d'Ivoire, contexte agricole. "
            "Villes: Ferkessédougou, Korhogo, Bouaké, Yamoussoukro, Abidjan, "
            "San-Pedro, Daloa, Divo, Man, Gagnoa, Bonoua, Soubré, Abengourou. "
            "Cultures: banane, manioc, maïs, riz, cacao, café, igname, arachide, "
            "palmier, hévéa, anacarde, coton, tomate, aubergine, piment, oignon, gombo. "
            "Termes agricoles: planter, cultiver, récolter, semer, période, saison, "
            "pluie, irrigation, engrais, pesticide, rendement, parcelle, tubercule."
        )

        # Transcrire avec Faster-Whisper
        print(f"[Faster-Whisper] Transcription avec modele {_model_name}")
        print(f"[Faster-Whisper] Fichier: {transcribe_path}")

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
            initial_prompt=initial_prompt,
            vad_filter=True,         # Filtrage VAD pour ignorer le silence
            vad_parameters={
                "min_silence_duration_ms": 500,  # Silence min 500ms
                "speech_pad_ms": 200             # Padding autour de la parole
            }
        )

        # Collecter tous les segments
        all_segments = []
        transcribed_texts = []

        for segment in segments:
            all_segments.append({
                "start": segment.start,
                "end": segment.end,
                "text": segment.text.strip()
            })
            transcribed_texts.append(segment.text.strip())

        transcribed_text = " ".join(transcribed_texts).strip()
        print(f"[Faster-Whisper] Résultat brut: '{transcribed_text}'")
        print(f"[Faster-Whisper] Langue détectée: {info.language} (prob: {info.language_probability:.2f})")
        print(f"[Faster-Whisper] Durée audio: {info.duration:.1f}s")

        # Corriger les termes agricoles mal transcrits (AVANT les villes)
        transcribed_text = correct_agricultural_terms(transcribed_text)
        print(f"[Faster-Whisper] Après correction agricole: '{transcribed_text}'")

        # Corriger les noms de villes mal transcrits
        transcribed_text = correct_city_names(transcribed_text)
        print(f"[Faster-Whisper] Après correction villes: '{transcribed_text}'")

        # Vérifier si le résultat semble être une hallucination
        if is_likely_hallucination(transcribed_text):
            print(f"[Faster-Whisper] Détection d'hallucination possible, texte ignoré")
            return None

        # Détecter si l'audio était probablement en Dioula
        likely_dioula = is_likely_dioula_input(transcribed_text, info.language_probability)
        if likely_dioula:
            print(f"[Faster-Whisper] ATTENTION: Audio probablement en Dioula, transcription peut être incorrecte")

        return {
            "text": transcribed_text,
            "language": info.language,
            "language_probability": info.language_probability,
            "likely_dioula_input": likely_dioula,
            "segments": all_segments
        }

    except Exception as e:
        print(f"Erreur transcription Faster-Whisper: {e}")
        import traceback
        traceback.print_exc()
        return None

    finally:
        # Nettoyer le fichier WAV temporaire
        if wav_path and os.path.exists(wav_path):
            try:
                os.remove(wav_path)
            except:
                pass


def correct_agricultural_terms(text: str) -> str:
    """
    Corrige les termes agricoles mal transcrits par Whisper.
    Whisper confond souvent les termes agricoles avec des mots plus courants.

    Args:
        text: Le texte transcrit

    Returns:
        Le texte avec les termes agricoles corrigés
    """
    if not text:
        return text

    # Dictionnaire de corrections pour termes agricoles
    # Clé: ce que Whisper transcrit (en minuscules)
    # Valeur: le terme correct
    agricultural_corrections = {
        # Période (très souvent mal transcrit)
        "pégole": "période",
        "pégo": "période",
        "pégol": "période",
        "pegole": "période",
        "pégole": "période",
        "pégolle": "période",

        # Banane (Paname = argot pour Paris!)
        "paname": "banane",
        "panama": "banane",
        "panane": "banane",
        "bannan": "banane",
        "banan": "banane",

        # Manioc
        "manioque": "manioc",
        "manioq": "manioc",
        "manyoc": "manioc",
        "maniac": "manioc",

        # Igname (très souvent mal transcrit!)
        "inyam": "igname",
        "ignam": "igname",
        "igniam": "igname",
        "yam": "igname",
        "signes d'igname": "igname",
        "signe d'igname": "igname",
        "signe igname": "igname",
        "signes igname": "igname",
        "des signes d'igname": "de l'igname",
        "cygne": "igname",

        # Cacao
        "kakao": "cacao",
        "cacau": "cacao",
        "cacaou": "cacao",

        # Café
        "caffé": "café",
        "caffet": "café",
        "caffer": "café",

        # Maïs
        "maïsse": "maïs",
        "maisse": "maïs",
        "mais": "maïs",
        "maize": "maïs",

        # Riz
        "rize": "riz",
        "rise": "riz",

        # Arachide
        "arachid": "arachide",
        "arachyde": "arachide",
        "arachidé": "arachide",

        # Palmier
        "palmié": "palmier",
        "palmyer": "palmier",

        # Hévéa (caoutchouc)
        "évéa": "hévéa",
        "hévéat": "hévéa",
        "heveya": "hévéa",

        # Anacarde (noix de cajou)
        "anacardé": "anacarde",
        "anakard": "anacarde",
        "anacart": "anacarde",

        # Coton
        "cotton": "coton",
        "cotont": "coton",

        # Planter
        "planté": "planter",
        "plantée": "planter",
        "plentée": "planter",

        # Récolte/Récolter
        "récolt": "récolte",
        "recolter": "récolter",
        "récoltée": "récolte",

        # Semer
        "semée": "semer",
        "semé": "semer",
        "semer": "semer",

        # Cultiver
        "cultivée": "cultiver",
        "cultivé": "cultiver",

        # Engrais
        "engraie": "engrais",
        "angrai": "engrais",
        "engraît": "engrais",

        # Irrigation
        "irrégation": "irrigation",
        "irriguation": "irrigation",

        # Saison
        "sèson": "saison",
        "séson": "saison",

        # Pluie
        "pluies": "pluie",
        "pluît": "pluie",

        # Sécheresse
        "sécherese": "sécheresse",
        "secheresse": "sécheresse",

        # Parcelle
        "parcel": "parcelle",
        "parselle": "parcelle",

        # Rendement
        "rendent": "rendement",
        "randement": "rendement",

        # Pesticide
        "pésticide": "pesticide",
        "pestissid": "pesticide",

        # Fongicide
        "fongissid": "fongicide",
        "fongicid": "fongicide",

        # Herbicide
        "erbicide": "herbicide",
        "herbissid": "herbicide",

        # Légumes
        "légum": "légumes",
        "legume": "légumes",

        # Tomate
        "tomat": "tomate",
        "tomatte": "tomate",

        # Aubergine
        "aubergin": "aubergine",
        "obergin": "aubergine",

        # Piment
        "piman": "piment",
        "pimant": "piment",

        # Oignon
        "oignont": "oignon",
        "ognon": "oignon",

        # Gombo
        "gombeau": "gombo",
        "gombos": "gombo",

        # Patate (douce)
        "patat": "patate",
        "patatte": "patate",

        # Haricot
        "aricot": "haricot",
        "haricots": "haricot",

        # Tubercule
        "tubercul": "tubercule",
        "tuberkul": "tubercule",
    }

    # Appliquer les corrections (insensible à la casse)
    result = text
    text_lower = text.lower()

    for wrong, correct in agricultural_corrections.items():
        if wrong in text_lower:
            import re
            pattern = re.compile(re.escape(wrong), re.IGNORECASE)
            result = pattern.sub(correct, result)
            print(f"[Faster-Whisper] Correction agricole: '{wrong}' -> '{correct}'")

    return result


def correct_city_names(text: str) -> str:
    """
    Corrige les noms de villes ivoiriennes mal transcrits par Whisper.
    Utilise une correspondance phonétique pour trouver la ville correcte.

    Args:
        text: Le texte transcrit

    Returns:
        Le texte avec les noms de villes corrigés
    """
    if not text:
        return text

    # Dictionnaire de corrections phonétiques
    # Clé: ce que Whisper peut transcrire (en minuscules)
    # Valeur: le nom correct de la ville
    city_corrections = {
        # Bonoua
        "bonnois": "Bonoua",
        "bonois": "Bonoua",
        "bono wa": "Bonoua",
        "bono oua": "Bonoua",
        "bonwa": "Bonoua",
        "bonouas": "Bonoua",
        "bono": "Bonoua",

        # Bouaké
        "bouaquer": "Bouaké",
        "bouake": "Bouaké",
        "bouaker": "Bouaké",
        "boua ké": "Bouaké",
        "bouakais": "Bouaké",

        # Yamoussoukro
        "yamoussoukros": "Yamoussoukro",
        "yamou soukro": "Yamoussoukro",
        "yamoussokro": "Yamoussoukro",
        "yamoussoukroi": "Yamoussoukro",

        # Korhogo
        "khorogo": "Korhogo",
        "korogho": "Korhogo",
        "korogau": "Korhogo",
        "korogo": "Korhogo",

        # San-Pedro / San Pedro
        "sain pedro": "San-Pedro",
        "saint pedro": "San-Pedro",
        "san pédro": "San-Pedro",
        "sampedro": "San-Pedro",

        # Abidjan
        "abijean": "Abidjan",
        "abidjean": "Abidjan",
        "abijan": "Abidjan",

        # Daloa
        "dalois": "Daloa",
        "da loa": "Daloa",

        # Man (très court, souvent confondu)
        "manne": "Man",
        "mann": "Man",
        "main": "Man",
        "mane": "Man",
        "mans": "Man",
        "ment": "Man",
        "mont": "Man",
        "mène": "Man",
        "mens": "Man",
        "mang": "Man",

        # Gagnoa
        "gagnois": "Gagnoa",
        "ganyoa": "Gagnoa",
        "gagnoua": "Gagnoa",

        # Divo
        "divaux": "Divo",
        "divos": "Divo",
        "divot": "Divo",

        # Abengourou
        "abenguru": "Abengourou",
        "abengouroux": "Abengourou",
        "abengrou": "Abengourou",

        # Soubré
        "soubres": "Soubré",
        "soubre": "Soubré",
        "soubrer": "Soubré",

        # Bouaflé
        "bouaflée": "Bouaflé",
        "bouafler": "Bouaflé",
        "boua flé": "Bouaflé",

        # Issia
        "issias": "Issia",
        "isiat": "Issia",

        # Ferkessédougou (nombreuses variantes phonétiques)
        "ferké": "Ferkessédougou",
        "ferkessedougou": "Ferkessédougou",
        "ferke": "Ferkessédougou",
        "ferké seingou": "Ferkessédougou",
        "ferké selon dougou": "Ferkessédougou",
        "ferkesse dougou": "Ferkessédougou",
        "fer ké": "Ferkessédougou",
        "ferk sédougou": "Ferkessédougou",
        "ferke sédougou": "Ferkessédougou",
        "ferkessédou": "Ferkessédougou",
        "ferkessedou": "Ferkessédougou",
        "ferke seindou": "Ferkessédougou",
        "ferkeu": "Ferkessédougou",
        "ferkes": "Ferkessédougou",
        "ferkès": "Ferkessédougou",
        "ferkéssédougou": "Ferkessédougou",
        "ferquessedougou": "Ferkessédougou",
        "fer kesse dougou": "Ferkessédougou",

        # Odienné
        "odiénné": "Odienné",
        "odienne": "Odienné",
        "odienner": "Odienné",

        # Séguéla
        "seguéla": "Séguéla",
        "seguela": "Séguéla",
        "seguelas": "Séguéla",

        # Bondoukou
        "bonduku": "Bondoukou",
        "bondukou": "Bondoukou",

        # Aboisso
        "aboiso": "Aboisso",
        "aboisos": "Aboisso",
        "abois so": "Aboisso",

        # Danané
        "dananer": "Danané",
        "danane": "Danané",
        "da nané": "Danané",

        # Duékoué
        "duékouer": "Duékoué",
        "duekoue": "Duékoué",
        "duekwe": "Duékoué",

        # Guiglo
        "guigleau": "Guiglo",
        "guiglos": "Guiglo",
        "gui glo": "Guiglo",

        # Tabou
        "tabous": "Tabou",
        "taboue": "Tabou",

        # Sassandra
        "sassandras": "Sassandra",
        "sassandrat": "Sassandra",

        # Grand-Bassam
        "grand bassam": "Grand-Bassam",
        "grandbassam": "Grand-Bassam",
        "grand-bassams": "Grand-Bassam",

        # Jacqueville
        "jackville": "Jacqueville",
        "jacquevilles": "Jacqueville",
        "jack ville": "Jacqueville",

        # Agboville
        "agbovilles": "Agboville",
        "agbo ville": "Agboville",

        # Dabou
        "dabous": "Dabou",
        "da bou": "Dabou",

        # Dimbokro
        "dimbokros": "Dimbokro",
        "dim bokro": "Dimbokro",
        "dimbocro": "Dimbokro",

        # Toumodi
        "toumodis": "Toumodi",
        "tou modi": "Toumodi",
        "toumaudit": "Toumodi",

        # Tiébissou
        "tiébissous": "Tiébissou",
        "tiebissou": "Tiébissou",
        "tié bissou": "Tiébissou",

        # Katiola
        "katiolas": "Katiola",
        "katio la": "Katiola",
        "cattiola": "Katiola",

        # Boundiali
        "boundialis": "Boundiali",
        "boundi ali": "Boundiali",
        "boundialy": "Boundiali",

        # Tengrela
        "tengrelas": "Tengrela",
        "tengré la": "Tengrela",
        "tangrela": "Tengrela",

        # Anyama
        "anyamas": "Anyama",
        "ani ama": "Anyama",
        "annyama": "Anyama",

        # Bingerville
        "bingervilles": "Bingerville",
        "binger ville": "Bingerville",
        "binguer ville": "Bingerville",
    }

    # Appliquer les corrections (insensible à la casse)
    result = text
    text_lower = text.lower()

    for wrong, correct in city_corrections.items():
        if wrong in text_lower:
            # Trouver la position et remplacer en préservant la casse environnante
            import re
            pattern = re.compile(re.escape(wrong), re.IGNORECASE)
            result = pattern.sub(correct, result)
            print(f"[Faster-Whisper] Correction ville: '{wrong}' -> '{correct}'")

    return result


def is_likely_hallucination(text: str) -> bool:
    """
    Détecte si un texte semble être une hallucination de Whisper.
    Les hallucinations sont des textes générés par le modèle qui ne correspondent pas
    à ce qui a été dit dans l'audio.

    Args:
        text: Le texte transcrit

    Returns:
        True si le texte semble être une hallucination
    """
    if not text:
        return True

    # Texte trop court (moins de 2 mots)
    words = text.split()
    if len(words) < 2:
        return True

    # Caractères non-latins (signe d'hallucination)
    non_latin_chars = sum(1 for c in text if ord(c) > 0x024F and not c.isspace())
    if non_latin_chars > len(text) * 0.2:  # Plus de 20% de caractères non-latins
        print(f"[Faster-Whisper] Trop de caractères non-latins détectés")
        return True

    # Phrases répétitives (signe d'hallucination)
    if len(text) > 50:
        # Vérifier les répétitions de mots
        if len(words) > 4:
            word_counts = {}
            for word in words:
                word_lower = word.lower()
                word_counts[word_lower] = word_counts.get(word_lower, 0) + 1

            # Si un mot apparaît plus de 50% du temps, c'est suspect
            max_count = max(word_counts.values())
            if max_count > len(words) * 0.5:
                print(f"[Faster-Whisper] Répétition excessive détectée")
                return True

    # Phrases génériques connues comme hallucinations de Whisper
    hallucination_patterns = [
        "sous-titres réalisés",
        "sous-titrage",
        "merci d'avoir regardé",
        "thank you for watching",
        "subscribe",
        "abonnez-vous",
        "like and subscribe",
        "www.",
        "http",
        "copyright",
        "tous droits réservés",
    ]

    text_lower = text.lower()
    for pattern in hallucination_patterns:
        if pattern in text_lower:
            print(f"[Faster-Whisper] Pattern d'hallucination détecté: {pattern}")
            return True

    return False


def is_likely_dioula_input(text: str, language_probability: float = 0.0) -> bool:
    """
    Détecte si l'audio original était probablement en Dioula/Bambara
    mais a été mal transcrit en français par Whisper.

    Indices:
    - Phrases incohérentes en français
    - Questions qui n'ont pas de sens
    - Probabilité de langue française basse
    - Mots répétés ou sons étranges

    Args:
        text: Le texte transcrit
        language_probability: Probabilité de la langue détectée par Whisper

    Returns:
        True si l'audio était probablement en Dioula
    """
    if not text:
        return False

    text_lower = text.lower()

    # Indices de transcription incorrecte (Dioula parlé -> français charabia)
    incoherent_patterns = [
        # Questions qui n'ont pas de sens en français
        "est-ce que tu parles plus là",
        "tu parles plus là",
        "parles plus là",
        "est-ce que tu parles",
        # Phrases répétitives typiques des mauvaises transcriptions
        "dis-moi dis-moi",
        "oui oui oui",
        "non non non",
        # Sons/mots qui ressemblent au Dioula mal interprétés
        "ala", "allah", "wala", "walahi",
        "n'golo", "ngolo",
        "fola", "fo la",
        # Onomatopées fréquentes
        "hein hein",
        "eh eh",
        "mmh mmh",
    ]

    for pattern in incoherent_patterns:
        if pattern in text_lower:
            print(f"[STT] Détection Dioula probable: pattern '{pattern}' trouvé")
            return True

    # Si la probabilité de langue est basse (<70%), c'est suspect
    if 0 < language_probability < 0.7:
        print(f"[STT] Détection Dioula probable: probabilité langue faible ({language_probability:.2f})")
        return True

    return False


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

    # DEBUG: Sauvegarder une copie pour analyse
    debug_dir = os.getenv("WOURRI_DEBUG_AUDIO_DIR", os.path.join(tempfile.gettempdir(), "wourri_debug_audio"))
    if not os.path.exists(debug_dir):
        os.makedirs(debug_dir)
    debug_path = os.path.join(debug_dir, f"audio_{uuid.uuid4()}{ext}")

    try:
        with open(temp_path, "wb") as f:
            f.write(audio_bytes)

        # DEBUG: Copier pour analyse
        with open(debug_path, "wb") as f:
            f.write(audio_bytes)
        print(f"[STT DEBUG] Audio sauvegarde: {debug_path} ({len(audio_bytes)} bytes)")

        result = transcribe_audio(temp_path, language)

        # DEBUG: Log le resultat
        if result:
            print(f"[STT DEBUG] Resultat transcription: '{result['text']}'")
        else:
            print(f"[STT DEBUG] Transcription echouee (None)")

        return result

    finally:
        # Nettoyer le fichier temporaire
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except:
                pass


def check_whisper_status() -> dict:
    """Verifie le statut de Faster-Whisper"""
    return {
        "whisper_available": WHISPER_AVAILABLE,
        "model_loaded": _whisper_model is not None,
        "model_name": _model_name,
        "engine": "faster-whisper (CTranslate2)",
        "supported_languages": ["fr", "en", "bam", "wo", "ff"]  # Langues principales
    }
