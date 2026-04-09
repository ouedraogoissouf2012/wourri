"""
WOURI - Traducteur DeepSeek avec ancres Bamadaba
Traduit Français → Bambara/Dioula avec :
  1. Extraction des mots-clés du texte français
  2. Lookup des équivalents bambara dans Bamadaba (ancres fiables)
  3. Prompt DeepSeek avec les ancres imposées (anti-hallucination)
  4. Validation par rétro-traduction BAM→FR (back-translation)

Pipeline:
  Texte FR
    ↓ [extract_anchors] → {maïs: kaba, planter: sɛnɛ, ...}
    ↓ [deepseek_with_anchors] → texte bambara
    ↓ [back_translate_nllb] → texte FR reconstruit
    ↓ [score_confidence] → score [0-1]
    ↓ Si score >= 0.4 → retourner texte bambara
      Sinon → fallback NLLB
"""
import logging
import httpx
from typing import Optional, Dict, Tuple

logger = logging.getLogger(__name__)

# Mots français à ignorer lors de l'extraction des ancres (stop words)
_FR_STOP_WORDS = {
    "le", "la", "les", "de", "du", "des", "un", "une", "et", "ou", "à", "au", "aux",
    "en", "par", "pour", "sur", "sous", "dans", "avec", "sans", "que", "qui", "ne",
    "pas", "plus", "très", "bien", "si", "car", "mais", "donc", "or", "ni", "il",
    "elle", "nous", "vous", "ils", "elles", "je", "tu", "on", "ce", "se", "sa", "son",
    "ses", "mes", "mon", "ma", "ton", "ta", "tes", "leur", "leurs", "est", "sont",
    "être", "avoir", "faire", "aller", "vouloir", "pouvoir", "devoir", "savoir",
    "c'est", "qu'il", "qu'elle", "d'un", "d'une", "l'", "j'", "m'", "s'",
    "bonjour", "merci", "oui", "non", "voici", "voilà"
}

# Mots à prioriser pour les ancres agricoles (bonus)
_AGRI_PRIORITY_WORDS = {
    "riz", "maïs", "mais", "mil", "sorgho", "arachide", "igname", "manioc",
    "haricot", "coton", "banane", "tomate", "oignon", "gombo",
    "planter", "semer", "récolter", "arroser", "cultiver", "labourer",
    "maladie", "insecte", "ravageur", "engrais", "fertilisant",
    "pluie", "saison", "sécheresse", "sol", "champ", "production",
    "poulet", "mouton", "vache", "chèvre"
}


def extract_anchor_candidates(french_text: str) -> list[str]:
    """Extrait les mots candidats pour les ancres (mots importants du texte FR)."""
    words = french_text.lower().replace(",", " ").replace(".", " ").replace("!", " ").replace("?", " ").split()
    candidates = []
    for w in words:
        w_clean = w.strip("'\"()-")
        if w_clean and w_clean not in _FR_STOP_WORDS and len(w_clean) > 2:
            candidates.append(w_clean)
    # Mettre les mots agricoles en premier
    candidates.sort(key=lambda w: (0 if w in _AGRI_PRIORITY_WORDS else 1, w))
    return candidates[:15]  # Max 15 mots-clés


def build_anchors(candidates: list[str], fr_to_bam_index: Dict) -> Dict[str, str]:
    """Construit le dictionnaire d'ancres {mot_fr: mot_bambara}.
    Utilise l'index FR→BAM du DictionaryRepository.
    """
    anchors = {}
    for word in candidates:
        # Chercher le mot directement
        entry = fr_to_bam_index.get(word)
        if entry and entry.translations:
            bambara_word = entry.translations[0]
            if bambara_word and len(bambara_word) > 1:
                anchors[word] = bambara_word
        # Chercher sans accent (tomate → tomate, récolter → recolter)
        if word not in anchors:
            word_noaccent = _strip_accents(word)
            if word_noaccent != word:
                entry = fr_to_bam_index.get(word_noaccent)
                if entry and entry.translations:
                    bambara_word = entry.translations[0]
                    if bambara_word and len(bambara_word) > 1:
                        anchors[word] = bambara_word
    return anchors


def _strip_accents(text: str) -> str:
    """Enlève les accents du français (récolter → recolter)."""
    import unicodedata
    return ''.join(
        c for c in unicodedata.normalize('NFD', text)
        if unicodedata.category(c) != 'Mn'
    )


def build_deepseek_translation_prompt(french_text: str, anchors: Dict[str, str]) -> str:
    """Construit le prompt pour DeepSeek avec les ancres comme garde-fous."""
    anchor_lines = "\n".join(
        f"  - {fr} → {bam}"
        for fr, bam in anchors.items()
    )

    if anchors:
        anchor_section = f"""
MOTS-CLÉS OBLIGATOIRES (utilise EXACTEMENT ces mots bambara dans ta traduction):
{anchor_lines}
"""
    else:
        anchor_section = ""

    return f"""Tu es un traducteur expert en bambara/dioula parlé, la langue des agriculteurs de Côte d'Ivoire et du Mali.
Traduis ce texte français en bambara/dioula PARLÉ, naturel, court.
{anchor_section}
RÈGLES STRICTES:
- Utilise le bambara/dioula parlé (pas le bambara littéraire ou scolaire)
- Phrases courtes, structure SOV (Sujet-Objet-Verbe)
- Si tu ne connais pas un mot exactement, utilise le mot français entre les mots bambara
- Réponds UNIQUEMENT avec la traduction, rien d'autre

Texte à traduire: "{french_text}"
Traduction bambara/dioula:"""


def score_back_translation(
    original_fr: str,
    back_translated_fr: str
) -> float:
    """Mesure la fidélité par overlap de mots-clés importants.

    Principe: si les mots importants du texte original se retrouvent
    dans la rétro-traduction, la traduction bambara est probablement correcte.

    Returns:
        Score entre 0.0 (aucune correspondance) et 1.0 (parfait)
    """
    if not back_translated_fr or not original_fr:
        return 0.0

    # Extraire les mots importants (sans stop words, sans accents)
    def get_key_words(text: str) -> set:
        words = _strip_accents(text.lower()).split()
        return {w for w in words if w not in _FR_STOP_WORDS and len(w) > 3}

    original_words = get_key_words(original_fr)
    back_words = get_key_words(back_translated_fr)

    if not original_words:
        return 0.5  # Texte trop court pour mesurer

    matches = original_words & back_words
    score = len(matches) / len(original_words)
    return min(1.0, score)


async def translate_fr_to_bambara_deepseek(
    french_text: str,
    deepseek_api_key: str,
    deepseek_base_url: str,
    deepseek_model: str,
    fr_to_bam_index: Optional[Dict] = None,
) -> Tuple[Optional[str], float]:
    """Traduit FR→Bambara via DeepSeek avec ancres Bamadaba.

    Args:
        french_text: Texte français à traduire
        deepseek_api_key: Clé API DeepSeek
        deepseek_base_url: URL de base DeepSeek
        deepseek_model: Modèle DeepSeek
        fr_to_bam_index: Index FR→BAM du DictionaryRepository (optionnel)

    Returns:
        Tuple (traduction_bambara, confidence_score)
        confidence_score: 0.0 si traduction impossible
    """
    if not deepseek_api_key:
        return None, 0.0

    # Construire les ancres depuis Bamadaba
    anchors = {}
    if fr_to_bam_index:
        candidates = extract_anchor_candidates(french_text)
        anchors = build_anchors(candidates, fr_to_bam_index)
        if anchors:
            logger.info(f"[DeepSeek Trad] Ancres: {anchors}")

    prompt = build_deepseek_translation_prompt(french_text, anchors)

    url = f"{deepseek_base_url}/chat/completions"
    headers = {
        "Authorization": f"Bearer {deepseek_api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": deepseek_model,
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.3,   # Bas pour traduction cohérente
        "max_tokens": 200,
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url, headers=headers, json=payload)

        if response.status_code != 200:
            logger.error(f"[DeepSeek Trad] Erreur API: {response.status_code}")
            return None, 0.0

        data = response.json()
        bambara_text = data["choices"][0]["message"]["content"].strip()

        # Nettoyer la réponse (DeepSeek peut ajouter des guillemets)
        if bambara_text.startswith('"') and bambara_text.endswith('"'):
            bambara_text = bambara_text[1:-1]

        logger.info(f"[DeepSeek Trad] FR: '{french_text[:50]}' → BAM: '{bambara_text[:60]}'")
        return bambara_text, 0.6  # Confiance de base sans back-translation

    except httpx.TimeoutException:
        logger.warning("[DeepSeek Trad] Timeout")
        return None, 0.0
    except Exception as e:
        logger.error(f"[DeepSeek Trad] Erreur: {e}")
        return None, 0.0


async def translate_fr_to_bambara_with_validation(
    french_text: str,
    deepseek_api_key: str,
    deepseek_base_url: str,
    deepseek_model: str,
    fr_to_bam_index: Optional[Dict] = None,
) -> Tuple[str, float, str]:
    """Traduit FR→Bambara avec validation par back-translation.

    Returns:
        Tuple (traduction_finale, confidence, méthode_utilisée)
    """
    bambara_result, base_conf = await translate_fr_to_bambara_deepseek(
        french_text, deepseek_api_key, deepseek_base_url, deepseek_model,
        fr_to_bam_index
    )

    if not bambara_result:
        return french_text, 0.0, "passthrough"

    # Back-translation: BAM→FR pour valider
    try:
        from app.services.translation import get_translation_service
        from app.services.translation.interfaces import Direction
        svc = get_translation_service()
        back_fr = svc.translate(bambara_result, Direction.BAM_TO_FR).text
        back_score = score_back_translation(french_text, back_fr)
        final_conf = (base_conf + back_score) / 2.0
        logger.info(f"[DeepSeek Trad] Back-trad: '{back_fr[:50]}' → score={back_score:.2f}, conf_finale={final_conf:.2f}")

        if final_conf >= 0.35:
            return bambara_result, final_conf, "deepseek+anchors+backval"
        else:
            logger.warning(f"[DeepSeek Trad] Score trop bas ({final_conf:.2f}) → fallback NLLB")
            return french_text, 0.0, "passthrough"
    except Exception as e:
        logger.error(f"[DeepSeek Trad] Back-translation échouée: {e}")
        # Retourner quand même la traduction DeepSeek sans validation
        return bambara_result, base_conf * 0.7, "deepseek+anchors"
