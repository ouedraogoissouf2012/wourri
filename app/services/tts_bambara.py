"""
WOURI - TTS Bambara (Hugging Face)
100% GRATUIT - facebook/mms-tts-bam

NOTE: Necessite torch, transformers, scipy (environ 2GB)
Pour installer: pip install torch transformers scipy pydub

Traduction déléguée au TranslationService (Strategy Pattern):
  1. Dictionnaire (11k+ mots Bamadaba + phrases manuelles)
  2. NLLB-200 (fallback IA)
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

# Cache des modèles TTS
_tts_model = None
_tts_tokenizer = None


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


# Noms de villes ivoiriennes à ne PAS traduire (NLLB les déforme)
IVORIAN_CITIES = [
    "Man", "Korhogo", "Bouaké", "Yamoussoukro", "Abidjan", "San-Pedro",
    "Daloa", "Divo", "Gagnoa", "Bonoua", "Soubré", "Abengourou",
    "Ferkessédougou", "Odienné", "Séguéla", "Bondoukou", "Aboisso",
    "Danané", "Duékoué", "Guiglo", "Tabou", "Sassandra", "Grand-Bassam",
    "Jacqueville", "Agboville", "Dabou", "Dimbokro", "Toumodi",
    "Tiébissou", "Katiola", "Boundiali", "Tengrela", "Anyama", "Bingerville"
]

# Placeholder pour protéger les villes pendant la traduction
CITY_PLACEHOLDER = "VILLE_PROTEGEE_{}"


def protect_city_names(text: str) -> tuple[str, dict]:
    """
    Remplace les noms de villes par des placeholders avant la traduction.
    Retourne le texte modifié et un dictionnaire de correspondance.
    """
    city_map = {}
    result = text

    for i, city in enumerate(IVORIAN_CITIES):
        # Recherche insensible à la casse
        pattern = re.compile(re.escape(city), re.IGNORECASE)
        if pattern.search(result):
            placeholder = CITY_PLACEHOLDER.format(i)
            city_map[placeholder] = city
            result = pattern.sub(placeholder, result)

    return result, city_map


def restore_city_names(text: str, city_map: dict) -> str:
    """
    Restaure les noms de villes après la traduction.
    """
    result = text
    for placeholder, city in city_map.items():
        result = result.replace(placeholder, city)
    return result


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


# Corrections NLLB connues : le modèle confond certains mots bambara
# Format : {mauvais_mot: bon_mot}
_NLLB_FR_TO_BAM_FIXES = {
    # NLLB traduit "riz" comme "wari" (argent) au lieu de "malo" (riz)
    "wari sɛnɛ": "malo sɛnɛ",    # "planter de l'argent" → "planter du riz"
    "wari sene": "malo sene",
    "i ka wari sɛnɛ": "i ka malo sɛnɛ",  # "planter ton argent" → "planter ton riz"
    "i ka wari": "i ka malo",       # "ton argent" → "ton riz" (dans contexte agricole)
    "ka wari sɛnɛ": "ka malo sɛnɛ",
    # Corrections de mots agricoles courants mal traduits par NLLB
    "shɛfan tobi": "foro labɛn",   # "cuire des œufs" → "préparer le champ"
}


def fix_nllb_errors(text: str) -> str:
    """Corrige les erreurs connues de NLLB dans la traduction FR→BAM."""
    if not text:
        return text
    result = text
    for wrong, correct in _NLLB_FR_TO_BAM_FIXES.items():
        if wrong in result:
            result = result.replace(wrong, correct)
    return result


def clean_bambara_text(text: str) -> str:
    """
    Post-traitement avancé du texte Bambara.
    Corrige les erreurs NLLB, nettoie les répétitions et améliore la fluidité.
    """
    if not text:
        return text

    # Étape 0: Corriger les erreurs NLLB connues
    text = fix_nllb_errors(text)

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


# Salutations bambara à injecter quand le contexte le demande
_BAMBARA_GREETINGS = {
    "bonjour": "Nba, i ni ce!",
    "bonsoir": "Nba, i ni su!",
    "salut": "Nba, i ni ce!",
    "merci": "Nba, i ni ce!",
}


def _detect_and_strip_greeting(text: str) -> tuple[str, str]:
    """Détecte une salutation française au début du texte.
    Retourne (salutation_bambara, texte_sans_salutation).
    Si pas de salutation, retourne ("", texte_original).
    """
    text_stripped = text.strip()
    text_lower = text_stripped.lower()
    for fr_greet, bam_greet in _BAMBARA_GREETINGS.items():
        if text_lower.startswith(fr_greet):
            # Enlever la salutation du texte pour ne pas la traduire par NLLB
            rest = text_stripped[len(fr_greet):].lstrip(" ,!.;:")
            if rest:
                return bam_greet, rest
            else:
                return bam_greet, ""
    return "", text_stripped


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

    # 0. Détecter et extraire la salutation (sera ajoutée en bambara pur)
    greeting_bam, remaining_text = _detect_and_strip_greeting(french_text)
    if not remaining_text:
        # Si le texte n'est qu'une salutation
        return greeting_bam if greeting_bam else french_text

    # Protéger les noms de villes
    protected_text, city_map = protect_city_names(remaining_text)
    if city_map:
        print(f"[Traduction] Villes protégées: {list(city_map.values())}")

    # Prétraitement
    preprocessed = preprocess_french_text(protected_text)
    if not preprocessed:
        return french_text

    # Découper en phrases courtes pour une meilleure traduction
    sentences = split_into_sentences(preprocessed)
    if not sentences:
        sentences = [preprocessed]

    from app.services.translation import get_translation_service
    from app.services.translation.interfaces import Direction
    service = get_translation_service()

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

    # Préfixer avec la salutation bambara (dictionnaire pur, jamais NLLB)
    if greeting_bam:
        result = f"{greeting_bam} {result}"

    try:
        print(f"[Bambara] Traduit: {len(french_text)} chars -> {len(result)} chars")
    except UnicodeEncodeError:
        print("[Bambara] Traduction effectuee")

    return result


# Préfixes de salutations bambara collées par l'ASR (sans espaces)
# L'ASR MMS-1B-ALL transcrit souvent "i ni sɔgɔma" comme "inisɔgɔma" ou "inisɔgɔ ma"
_BAM_GREETING_PREFIXES = [
    # Avec diacritiques - collées
    "inisɔgɔma", "inisɔgɔ ma",  # i ni sɔgɔma (bonjour matin)
    "anisɔgɔma", "anisɔgɔ ma",  # a ni sɔgɔma
    "inice", "anice",            # i ni ce / a ni ce (bonjour)
    "iniwula", "ini wula",       # i ni wula (bonsoir)
    "inisu", "ini su",           # i ni su (bonne nuit)
    "inibaara", "ini baara",     # i ni baara (merci pour ton travail)
    # Sans diacritiques - collées (ASR peut omettre les ɔ)
    "inisogoma", "inisogo ma",   # i ni sogoma
    "anisogoma", "anisogo ma",   # a ni sogoma
    # Avec espaces (salutation pas collée mais en variante ASR)
    "i ni sɔgɔma", "a ni sɔgɔma",
    "i ni sogoma", "a ni sogoma",
    "ani sɔgɔma", "ani sogoma",  # "ani" = variante ASR de "a ni" / "i ni"
    "an ni sɔgɔma", "an ni sogoma",  # "an ni" = variante NeMo TDT (bonjour matin)
    "i ni ce", "a ni ce", "ani ce",
    "i ni wula", "a ni wula",
    "i ni su", "a ni su",
]

# Mapping préfixe collé -> salutation française propre
_BAM_GREETING_TO_FR = {
    # Collées
    "inisɔgɔma": "Bonjour, ", "inisɔgɔ ma": "Bonjour, ",
    "anisɔgɔma": "Bonjour, ", "anisɔgɔ ma": "Bonjour, ",
    "inisogoma": "Bonjour, ", "inisogo ma": "Bonjour, ",
    "anisogoma": "Bonjour, ", "anisogo ma": "Bonjour, ",
    "inice": "Bonjour, ", "anice": "Bonjour, ",
    "iniwula": "Bonsoir, ", "ini wula": "Bonsoir, ",
    "inisu": "Bonne nuit, ", "ini su": "Bonne nuit, ",
    "inibaara": "Merci, ", "ini baara": "Merci, ",
    # Avec espaces
    "i ni sɔgɔma": "Bonjour, ", "a ni sɔgɔma": "Bonjour, ",
    "i ni sogoma": "Bonjour, ", "a ni sogoma": "Bonjour, ",
    "ani sɔgɔma": "Bonjour, ", "ani sogoma": "Bonjour, ",
    "an ni sɔgɔma": "Bonjour, ", "an ni sogoma": "Bonjour, ",
    "i ni ce": "Bonjour, ", "a ni ce": "Bonjour, ", "ani ce": "Bonjour, ",
    "i ni wula": "Bonsoir, ", "a ni wula": "Bonsoir, ",
    "i ni su": "Bonne nuit, ", "a ni su": "Bonne nuit, ",
}


def _split_bam_greeting(text: str) -> tuple[str, str]:
    """Détecte et sépare une salutation bambara collée au début du texte ASR.
    Retourne (salutation_fr, reste_du_texte).
    Ex: 'inisɔgɔ ma ne bɛ fɛ ka malo sɛnɛ' -> ('Bonjour, ', 'ne bɛ fɛ ka malo sɛnɛ')
    """
    text_lower = text.lower().strip()
    # Trier par longueur décroissante pour matcher le préfixe le plus long d'abord
    for prefix in sorted(_BAM_GREETING_PREFIXES, key=len, reverse=True):
        if text_lower.startswith(prefix):
            rest = text_lower[len(prefix):].lstrip(" ,!.;:")
            if rest:
                fr_greeting = _BAM_GREETING_TO_FR.get(prefix, "Bonjour, ")
                return fr_greeting, rest
            else:
                fr_greeting = _BAM_GREETING_TO_FR.get(prefix, "Bonjour")
                return fr_greeting.rstrip(", "), ""
    return "", text


def translate_to_french(bambara_text: str) -> str:
    """
    Traduit du Bambara vers le Français.
    1. Détecte les salutations collées par l'ASR (inisɔgɔma -> Bonjour)
    2. Délègue au TranslationService (dictionnaire 11k+ mots + NLLB fallback)
    """
    if not bambara_text or not bambara_text.strip():
        return bambara_text

    # Détecter et séparer une salutation collée par l'ASR
    greeting_fr, remaining = _split_bam_greeting(bambara_text)

    from app.services.translation import get_translation_service
    service = get_translation_service()

    if remaining:
        result = service.translate_to_french(remaining)
    else:
        # Texte = juste une salutation
        return greeting_fr if greeting_fr else bambara_text

    # Capitaliser la première lettre
    if result and result[0].islower():
        result = result[0].upper() + result[1:]

    # Préfixer avec la salutation française
    if greeting_fr:
        result = f"{greeting_fr}{result}"

    return result


from app.services._ffmpeg import get_ffmpeg as find_ffmpeg, wav_to_ogg_normalized


def convert_wav_to_ogg(wav_path: str, ogg_path: str) -> bool:
    """Convertit un fichier WAV en OGG Opus avec normalisation loudnorm EBU R128.
    Délègue à _ffmpeg.wav_to_ogg_normalized (source unique, loudnorm si disponible).
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
    translator_loaded = False
    try:
        from app.services.translation import get_translation_service
        service = get_translation_service()
        stats = service.get_stats()
        translator_loaded = stats["dictionnaire"]["total_mots"] > 0
    except Exception:
        pass

    return {
        "torch_available": TORCH_AVAILABLE,
        "tts_loaded": _tts_model is not None,
        "translator_loaded": translator_loaded,
        "tts_model": settings.hf_tts_model,
        "translator_model": settings.hf_translator_model
    }
