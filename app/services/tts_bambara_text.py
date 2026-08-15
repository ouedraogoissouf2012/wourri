"""
WOURI - Pipeline de traitement texte pour le TTS Bambara.

Extrait de tts_bambara.py (modularisation 2026-08) : fonctions PURES de
normalisation/nettoyage texte, sans aucune dépendance torch. Regroupe la
protection des noms de villes, le prétraitement français, le découpage en
phrases, les corrections NLLB et le nettoyage anti-répétition. Testable en
isolation sans charger les ~2GB de modèle TTS.

La god-function historique `clean_bambara_text` est décomposée en 4 étapes
nommées (helpers privés) ; l'orchestrateur préserve exactement le comportement
d'origine, y compris la garde "moins de 2 mots -> texte renvoyé tel quel".
"""
import re
from app.data.constants import IVORIAN_CITY_NAMES


# Noms de villes ivoiriennes à ne PAS traduire (NLLB les déforme)
IVORIAN_CITIES = IVORIAN_CITY_NAMES

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


def _strip_consecutive_dups(words: list[str]) -> str:
    """Étape 1 de clean_bambara_text : supprime les mots consécutifs identiques
    (comparaison insensible à la casse et à la ponctuation). `words` contient au
    moins 2 éléments (garanti par l'appelant)."""
    cleaned_words = [words[0]]
    for i in range(1, len(words)):
        current = words[i].lower().strip('.,!?')
        previous = words[i-1].lower().strip('.,!?')
        if current != previous:
            cleaned_words.append(words[i])
    return ' '.join(cleaned_words)


def _strip_ngram_repetitions(text: str) -> str:
    """Étape 2 de clean_bambara_text : supprime les répétitions de tri-grams
    puis de bi-grams (ex: 'ka bo ka bo ka bo' -> 'ka bo')."""
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
    return text


def _enforce_unique_ratio(text: str) -> str:
    """Étape 3 de clean_bambara_text : si moins de 40% de mots uniques (texte
    trop répétitif), tronque en gardant les premiers mots uniques."""
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
    return text


def _ensure_terminal_punct(text: str) -> str:
    """Étape 4 de clean_bambara_text : garantit une ponctuation finale."""
    text = text.strip()
    if text and text[-1] not in '.!?':
        text += '.'
    return text


def clean_bambara_text(text: str) -> str:
    """
    Post-traitement avancé du texte Bambara.
    Corrige les erreurs NLLB, nettoie les répétitions et améliore la fluidité.

    Pipeline : fix NLLB (0) -> dédup mots consécutifs (1) -> dédup n-grams (2)
    -> contrôle du ratio de mots uniques (3) -> ponctuation finale (4).
    """
    if not text:
        return text

    # Étape 0: Corriger les erreurs NLLB connues
    text = fix_nllb_errors(text)

    # Étape 1: Supprimer les répétitions de mots consécutifs.
    # Garde historique : un texte de moins de 2 mots est renvoyé TEL QUEL, sans
    # même la ponctuation finale de l'étape 4 (comportement préservé).
    words = text.split()
    if len(words) < 2:
        return text
    text = _strip_consecutive_dups(words)

    # Étape 2: Détecter les patterns répétitifs (bi-grams, tri-grams)
    text = _strip_ngram_repetitions(text)

    # Étape 3: Vérifier le ratio de mots uniques
    text = _enforce_unique_ratio(text)

    # Étape 4: Nettoyer la ponctuation finale
    return _ensure_terminal_punct(text)
