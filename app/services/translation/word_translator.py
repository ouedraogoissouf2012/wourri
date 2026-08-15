"""
WOURI - Traduction par dictionnaire (mots + patterns)
Strategie 1 : la plus rapide et precise, limitee au vocabulaire connu.
"""
import logging
from typing import Optional
from .interfaces import ITranslator, TranslationResult, Direction
from .dictionary_repository import DictionaryRepository
from .translation_scoring import pick_best_translation

logger = logging.getLogger(__name__)


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

    @staticmethod
    def _apply_patterns(words: list[str], patterns: dict) -> tuple[list[str], list[bool]]:
        """Applique les patterns (du plus long au plus court) sur `words`.

        Un pattern multi-mots consomme sa fenêtre : le 1er mot reçoit la
        traduction, les suivants sont vidés (""). Un token déjà couvert par un
        pattern n'est jamais réécrit. Factorise la logique commune à FR->BAM et
        BAM->FR ; l'appelant fournit `words` déjà prétraité selon la direction.

        @returns (translated_words, translated_by_pattern)
        """
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
        return translated_words, translated_by_pattern

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
        translated_words, translated_by_pattern = self._apply_patterns(words, patterns)

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
        translated_words, translated_by_pattern = self._apply_patterns(words, patterns)

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
