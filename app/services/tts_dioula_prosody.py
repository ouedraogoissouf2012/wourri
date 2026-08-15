"""
WOURI - Prosodie / segmentation pour le TTS Dioula.

Extrait de tts_dioula.py (modularisation 2026-08) : segmentation PURE du texte
en segments + pauses, et choix du speaking_rate. Aucune dépendance torch/numpy
(uniquement `re`) → testable en isolation sans charger le modèle TTS (~3.8 GB).

Ces fonctions pilotent le rendu prosodique de MMS-TTS-DYU (VITS) : découpage
hiérarchique (ponctuation forte → virgule → marqueurs discursifs bambara →
découpage forcé) et débit adapté au type de phrase.
"""
import re


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
