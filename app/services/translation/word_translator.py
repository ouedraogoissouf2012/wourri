"""
WOURI - Traduction par dictionnaire (mots + patterns)
Strategie 1 : la plus rapide et precise, limitee au vocabulaire connu.
"""
import logging
import re
from typing import Optional
from .interfaces import ITranslator, TranslationResult, Direction
from .dictionary_repository import DictionaryRepository

logger = logging.getLogger(__name__)


# Annotations grammaticales Bamadaba à exclure des traductions
_GRAMMAR_TAGS = {
    "1sg", "2sg", "3sg", "1pl", "2pl", "3pl",
    "1sg.emph", "2sg.emph", "3sg.emph", "1sg emph", "2sg emph", "3sg emph",
    "ipfv", "ipfv.aff", "ipfv aff", "pfv", "pfv.aff", "pfv aff",
    "sbjv", "qual", "qual.aff", "qual aff", "cop", "refl",
    "poss", "fut", "neg", "emph", "inf", "tr", "intr",
    # Tags Bamadaba supplémentaires (vus dans les logs démo investisseurs)
    "nom", "verbe", "adverbe", "adjectif", "conjonction", "interjection",
    "particule", "déterminant", "pronom", "préposition",
    "mâle", "femelle",  # tags biologiques Bamadaba, pas des traductions utiles
}

# Patterns de texte technique Bamadaba à penaliser fortement
# ATTENTION: ces patterns sont testés avec re.IGNORECASE sauf _GRAMMAR_PATTERNS_CASESENSITIVE
_GRAMMAR_PATTERNS_CASESENSITIVE = [
    r'^[A-Z0-9.]+$',                    # IPFV.AFF, 1SG, etc. (DOIT rester case-sensitive)
]
_GRAMMAR_PATTERNS = [
    r'pfs:',                              # pfs: sens de futur
    r'auxiliaire',                         # auxiliaire du présent
    r'marqueur',                          # marqueur predicatif, marqueur de relation
    r'reliant',                           # reliant le verbe
    r'postposition',                       # postposition
    r'sens de futur',                     # sens de futur
    r'pronom.*personne',                  # pronom de la première personne
    r'^marque\b',                         # marque d'agent, marque du possesseur
    r'copule',                            # copule
    r'connectif',                         # connectif
    r'suffixe',                           # suffixe verbal
    r'préfixe',                           # préfixe verbal
    r'particule\s+(verbale|de|du)',       # particule verbale, particule de...
    r'aspect\s+(accompli|inaccompli)',    # aspect accompli/inaccompli
    r'(^|\s)v\.\s',                       # v. (abréviation pour verbe)
    r'(^|\s)n\.\s',                       # n. (abréviation pour nom)
    r'(^|\s)adj\.\s',                     # adj. (abréviation pour adjectif)
]

# Mots agricoles à privilégier (WOURI est un assistant agricole)
_AGRI_KEYWORDS = {
    "riz", "maïs", "mil", "arachide", "arachides", "champ", "cultiver",
    "récolte", "récolter", "semer", "planter", "arroser", "eau", "pluie",
    "terre", "sol", "grain", "graine", "engrais", "saison", "sécheresse",
    "irriguer", "irrigation", "bétail", "élevage", "pêche", "poisson",
    "manioc", "igname", "banane", "mangue", "karité", "coton", "sorgho",
    "légume", "fruit", "arbre", "forêt", "bois", "herbe", "feuille",
    "racine", "fleur", "maladie", "insecte", "traitement", "engrais",
}


def _is_grammar_annotation(t: str) -> bool:
    """Verifie si un texte est une annotation grammaticale Bamadaba."""
    t_lower = t.lower().strip()
    if t_lower in _GRAMMAR_TAGS:
        return True
    # Patterns case-sensitive (ALL CAPS abbreviations)
    for pat in _GRAMMAR_PATTERNS_CASESENSITIVE:
        if re.search(pat, t):
            return True
    # Patterns case-insensitive
    for pat in _GRAMMAR_PATTERNS:
        if re.search(pat, t, re.IGNORECASE):
            return True
    return False


def pick_best_translation(translations: list[str]) -> str:
    """Choisit la meilleure traduction parmi les candidates.
    Filtre les annotations grammaticales Bamadaba.
    Prefere les traductions courtes, naturelles, en français courant.
    Bonus pour le vocabulaire agricole (contexte WOURI).
    """
    if not translations:
        return ""
    if len(translations) == 1:
        t = translations[0]
        if _is_grammar_annotation(t):
            return ""
        return t.replace('.', ' ') if '.' in t and not t.endswith('.') else t

    scored = []
    for t in translations:
        score = 0
        t_lower = t.lower().strip()

        # Exclure completement les tags grammaticaux
        if t_lower in _GRAMMAR_TAGS:
            score -= 500
        # Penaliser les abbreviations grammaticales ALL CAPS (1SG, 3PL, REFL)
        for pat in _GRAMMAR_PATTERNS_CASESENSITIVE:
            if re.search(pat, t):
                score -= 200
                break
        # Penaliser les descriptions techniques Bamadaba
        for pat in _GRAMMAR_PATTERNS:
            if re.search(pat, t, re.IGNORECASE):
                score -= 200
                break
        # Penaliser les traductions avec points (peigne.de.tisserand)
        if '.' in t and not t.endswith('.'):
            score -= 50
        # Preferer les traductions courtes (1-2 mots, pas trop longs)
        word_count = len(t_lower.split())
        if word_count == 1 and 2 <= len(t) <= 20:
            score += 15
        elif word_count == 2 and len(t) <= 25:
            score += 10
        elif 2 <= len(t) <= 30:
            score += 5
        # Preferer les traductions en minuscules (mots communs)
        if t and t[0].islower():
            score += 5
        # Bonus agricole (WOURI est un assistant pour agriculteurs)
        if t_lower in _AGRI_KEYWORDS:
            score += 30
        # Penaliser les traductions entre parentheses
        if t.startswith('('):
            score -= 20
        # Penaliser les mots avec slash (etre/faire, etc.)
        if '/' in t:
            score -= 5
        # Penaliser les longues descriptions/definitions
        if len(t) > 40:
            score -= 30
        # Penaliser "devant --" style (references internes Bamadaba)
        if '--' in t:
            score -= 100
        scored.append((score, t))

    scored.sort(key=lambda x: x[0], reverse=True)
    best = scored[0][1]

    # Si le meilleur est aussi une annotation, retourner vide
    if scored[0][0] <= -200:
        # Chercher s'il y a au moins un candidat acceptable
        for s, t in scored:
            if s > -200:
                best = t
                break
        else:
            return ""

    # Nettoyer: enlever les points composites (homme.etonnant -> homme etonnant)
    if '.' in best and not best.endswith('.'):
        best = best.replace('.', ' ')

    return best


class WordTranslator(ITranslator):
    """Traduction mot-a-mot + patterns grammaticaux via le dictionnaire"""

    def __init__(self, repository: DictionaryRepository):
        self._repo = repository

    @property
    def name(self) -> str:
        return "dictionnaire"

    @property
    def priority(self) -> int:
        return 1

    def can_handle(self, text: str, direction: Direction) -> bool:
        words = text.lower().strip().split()
        if not words:
            return False
        matched = sum(1 for w in words if self._repo.lookup_word(w, direction))
        return matched >= len(words) * 0.3

    def translate(self, text: str, direction: Direction) -> Optional[TranslationResult]:
        text_lower = text.lower().strip()
        original_words = text_lower.split()
        total = len(original_words)

        if total == 0:
            return None

        # 1. Chercher une phrase complète. Le repository applique la même
        # normalisation au chargement et au lookup.
        phrase_result = self._repo.lookup_phrase(text_lower, direction)
        if phrase_result:
            return TranslationResult(
                text=phrase_result,
                source_text=text,
                direction=direction,
                strategy_used=self.name,
                confidence=1.0,
                words_matched=total,
                words_total=total,
            )

        # Pour FR->BAM : NE PAS faire de mot-à-mot (produit du charabia).
        # Seules les phrases exactes et patterns sont fiables.
        # Le mot-à-mot FR->BAM ignore la syntaxe bambara (SOV, postpositions).
        # Déléguer les phrases non reconnues à NLLB.
        if direction == Direction.FR_TO_BAM:
            return self._translate_fr_to_bam_strict(text_lower, original_words, total, direction)

        # Pour BAM->FR : mot-à-mot + patterns (fonctionne bien)
        return self._translate_bam_to_fr(text_lower, original_words, total, direction)

    def _translate_fr_to_bam_strict(self, text_lower: str, original_words: list[str],
                                     total: int, direction: Direction) -> Optional[TranslationResult]:
        """Traduction FR->BAM stricte : patterns uniquement, pas de mot-à-mot.
        Le mot-à-mot français->bambara produit du charabia car la syntaxe
        bambara (SOV, postpositions) est très différente du français (SVO).
        """
        patterns = self._repo.get_patterns(direction)
        # Nettoyer la ponctuation des mots pour le matching (sinon "riz." ≠ "riz")
        words = [w.strip('.,!?;:') for w in original_words]
        words = [w for w in words if w]  # enlever les mots vides après nettoyage
        total = len(words) if words else total
        translated_by_pattern = [False] * len(words)
        translated_words = list(words)

        # Appliquer les patterns (du plus long au plus court)
        sorted_patterns = sorted(patterns.items(), key=lambda x: len(x[0]), reverse=True)
        for pattern, replacement in sorted_patterns:
            pattern_words = pattern.split()
            pattern_len = len(pattern_words)
            for start in range(len(words) - pattern_len + 1):
                if any(translated_by_pattern[start:start + pattern_len]):
                    continue
                segment = " ".join(words[start:start + pattern_len])
                if segment == pattern:
                    translated_words[start] = replacement
                    for j in range(start + 1, start + pattern_len):
                        translated_words[j] = ""
                        translated_by_pattern[j] = True
                    translated_by_pattern[start] = True

        patterns_matched = sum(1 for x in translated_by_pattern if x)
        coverage = patterns_matched / max(total, 1)

        # Exiger une couverture élevée (>= 70%) pour FR->BAM par patterns
        # Sinon laisser NLLB gérer (il comprend la syntaxe)
        if coverage < 0.7:
            return None

        # Construire le résultat (mots non matchés restent en français)
        final_parts = [w for w in translated_words if w]
        final_text = " ".join(final_parts).strip()

        return TranslationResult(
            text=final_text,
            source_text=" ".join(original_words),
            direction=direction,
            strategy_used=self.name,
            confidence=min(coverage, 1.0),
            words_matched=patterns_matched,
            words_total=total,
        )

    def _translate_bam_to_fr(self, text_lower: str, original_words: list[str],
                              total: int, direction: Direction) -> Optional[TranslationResult]:
        """Traduction BAM->FR : mot-à-mot + patterns (fonctionne bien)."""
        # 2. Appliquer les patterns (du plus long au plus court)
        patterns = self._repo.get_patterns(direction)
        words = text_lower.split()
        translated_by_pattern = [False] * len(words)
        translated_words = list(words)

        sorted_patterns = sorted(patterns.items(), key=lambda x: len(x[0]), reverse=True)
        for pattern, replacement in sorted_patterns:
            pattern_words = pattern.split()
            pattern_len = len(pattern_words)
            for start in range(len(words) - pattern_len + 1):
                if any(translated_by_pattern[start:start + pattern_len]):
                    continue
                segment = " ".join(words[start:start + pattern_len])
                if segment == pattern:
                    translated_words[start] = replacement
                    for j in range(start + 1, start + pattern_len):
                        translated_words[j] = ""
                        translated_by_pattern[j] = True
                    translated_by_pattern[start] = True

        # 3. Traduire les mots restants (non couverts par patterns)
        final_parts = []
        dict_matched = 0
        grammar_filtered = 0  # Compteur de mots dont la traduction était un tag grammatical
        patterns_matched = sum(1 for x in translated_by_pattern if x)

        i = 0
        while i < len(translated_words):
            word = translated_words[i]

            if word == "":
                i += 1
                continue

            if translated_by_pattern[i]:
                final_parts.append(word)
                i += 1
                continue

            # Essayer groupes de 3, 2, 1 mots dans le dictionnaire
            found = False
            for n in [3, 2, 1]:
                if i + n <= len(translated_words):
                    if any(translated_by_pattern[i:i + n]):
                        continue
                    phrase = " ".join(words[i:i + n])
                    entry = self._repo.lookup_word(phrase, direction)
                    if entry and entry.translations:
                        best = pick_best_translation(entry.translations)
                        if best:
                            final_parts.append(best)
                            dict_matched += n
                        else:
                            # pick_best_translation a retourné "" = toutes les traductions
                            # étaient des tags grammaticaux. Ne pas insérer le mot bambara brut.
                            grammar_filtered += n
                        i += n
                        found = True
                        break

            if not found:
                final_parts.append(word)
                i += 1

        final_text = " ".join(final_parts).strip()

        # Capitaliser la premiere lettre
        if final_text:
            final_text = final_text[0].upper() + final_text[1:]

        # Les mots filtrés par grammar ne comptent PAS comme traduits
        total_matched = dict_matched + patterns_matched
        confidence = total_matched / max(total, 1)

        # Si trop de mots étaient des tags grammaticaux, le dictionnaire
        # ne comprend pas vraiment cette phrase -> déléguer à NLLB
        if grammar_filtered >= 2 and grammar_filtered >= total * 0.3:
            logger.info(f"[dictionnaire] BAM->FR: {grammar_filtered}/{total} mots = tags grammaticaux, delegation NLLB")
            return None

        if confidence < 0.4:
            return None

        return TranslationResult(
            text=final_text,
            source_text=" ".join(original_words),
            direction=direction,
            strategy_used=self.name,
            confidence=min(confidence, 1.0),
            words_matched=total_matched,
            words_total=total,
        )
