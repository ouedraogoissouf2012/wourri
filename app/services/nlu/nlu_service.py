"""
WOURI - Service NLU (Orchestrateur)
Coordonne l'extraction de concepts, la classification d'intention
et la reconstruction de phrase française.

Usage:
    from app.services.nlu import get_nlu_service
    nlu = get_nlu_service()
    result = nlu.process("an ni sɔgɔma n ye kabaforo-la tigi ye n b'a fɛ conseil sɔrɔ")
    if result.french_sentence:
        # Envoyer result.french_sentence à DeepSeek au lieu de la traduction brute
        pass
    elif result.is_out_of_scope:
        # Répondre avec message hors-sujet
        pass
"""
import json
import logging
import os
from dataclasses import dataclass, field
from typing import Dict, Optional

logger = logging.getLogger(__name__)

from .concept_extractor import ConceptExtractor
from .intent_classifier import IntentClassifier
from .sentence_builder import SentenceBuilder


@dataclass
class NLUResult:
    """Résultat complet du traitement NLU."""
    bambara_text: str                    # Texte original (transcription ASR)
    concepts: Dict[str, float]           # Concepts détectés {nom: confiance}
    intent: str                          # Intent classifié
    confidence: float                    # Confiance de la classification [0, 1]
    french_sentence: Optional[str]       # Phrase française reconstruite (ou None)
    has_greeting: bool                   # Salutation détectée
    is_out_of_scope: bool                # Message hors sujet agricole
    is_greeting_only: bool               # Juste une salutation, pas de question
    out_of_scope_message_fr: str = ""    # Message hors-sujet en français

    def __str__(self) -> str:
        concepts_str = ", ".join(self.concepts.keys()) if self.concepts else "aucun"
        return (
            f"NLU[intent={self.intent}, conf={self.confidence:.2f}, "
            f"concepts={concepts_str}, "
            f"sentence='{self.french_sentence or 'None'}']"
        )


class NLUService:
    """Service NLU principal — singleton."""

    def __init__(
        self,
        concepts_path: Optional[str] = None,
        min_confidence: Optional[float] = None,
        config: Optional[dict] = None,
    ):
        """Charge la configuration NLU depuis le fichier JSON.

        Args:
            concepts_path: Chemin vers dictionnaires/nlu_concepts.json
            min_confidence: seuil de confiance minimum pour utiliser la phrase
                reconstruite. Injectable (tests, DIP) ; si `None`, lu depuis
                `settings.nlu_min_confidence` (issue #297 — externalisation du
                hardcode historique 0.2, valeur par défaut inchangée).
            config: configuration déjà assemblée, à la place d'un fichier
                (NLU baoulé : concepts baoulé + intents du dioula, ADR-0045).
        """
        if config is None:
            if not concepts_path or not os.path.exists(concepts_path):
                raise FileNotFoundError(f"[NLU] Fichier concepts non trouvé: {concepts_path}")
            with open(concepts_path, "r", encoding="utf-8") as f:
                config = json.load(f)

        if min_confidence is None:
            from app.config import settings

            min_confidence = settings.nlu_min_confidence
        self._min_confidence = float(min_confidence)

        self._config = config

        self._extractor = ConceptExtractor(self._config)
        self._classifier = IntentClassifier(self._config.get("intents", []))
        self._builder = SentenceBuilder()
        self._out_of_scope = self._config.get("out_of_scope_response", {})

        logger.info(
            f"[NLU] Chargé: {len(self._config.get('concepts', {}))} concepts, "
            f"{len(self._config.get('intents', []))} intents"
        )

    def process(self, bambara_text: str) -> NLUResult:
        """Traite un texte bambara et retourne le résultat NLU complet.

        Étapes:
        1. Extraction des concepts du texte bambara
        2. Classification de l'intention
        3. Reconstruction de la phrase française (si confiance suffisante)

        Args:
            bambara_text: Transcription ASR bambara/dioula

        Returns:
            NLUResult avec french_sentence si le NLU a trouvé un sens clair,
            None sinon (fallback vers traduction normale).
        """
        if not bambara_text or not bambara_text.strip():
            return NLUResult(
                bambara_text=bambara_text or "",
                concepts={},
                intent="HORS_SUJET",
                confidence=0.0,
                french_sentence=None,
                has_greeting=False,
                is_out_of_scope=True,
                is_greeting_only=False,
                out_of_scope_message_fr=self._out_of_scope.get("fr", "")
            )

        # ---- Étape 1: Extraction des concepts ----
        extraction = self._extractor.extraire(bambara_text)
        concepts = extraction.concepts
        logger.info(f"[NLU] Concepts: {list(concepts.keys())}")

        # ---- Étape 2: Classification de l'intention ----
        # Sur tous les concepts, homographes douteux compris (ADR-0041) : la règle
        # des homographes choisit la culture, elle ne change pas l'intent.
        intent, confidence, matched_data = self._classifier.classify(extraction.concepts_intent)
        logger.info(f"[NLU] Intent: {intent} (confiance={confidence:.2f})")

        # ---- Étape 3: Reconstruction de la phrase française ----
        french_sentence = None
        is_out_of_scope = (intent == "HORS_SUJET")
        is_greeting_only = (intent == "SALUTATION_SEULE")

        if not is_out_of_scope and not is_greeting_only:
            if confidence >= self._min_confidence:
                french_sentence = self._builder.build(
                    intent=intent,
                    concepts=concepts,
                    matched_data=matched_data,
                    out_of_scope_response=self._out_of_scope.get("fr")
                )
                if french_sentence:
                    logger.info(f"[NLU] Phrase reconstruite: '{french_sentence}'")

        return NLUResult(
            bambara_text=bambara_text,
            concepts=concepts,
            intent=intent,
            confidence=confidence,
            french_sentence=french_sentence,
            has_greeting=matched_data.get("has_greeting", False),
            is_out_of_scope=is_out_of_scope,
            is_greeting_only=is_greeting_only,
            out_of_scope_message_fr=self._out_of_scope.get("fr", "")
        )

    def get_out_of_scope_response(self, lang: str = "fr") -> str:
        """Retourne le message hors-sujet dans la langue demandée."""
        return self._out_of_scope.get(lang, self._out_of_scope.get("fr", ""))

    def get_stats(self) -> dict:
        """Statistiques sur le service NLU."""
        concepts = self._config.get("concepts", {})
        intents = self._config.get("intents", [])
        total_keywords = sum(
            len(c.get("keywords", [])) for c in concepts.values()
        )
        return {
            "version": self._config.get("version", "?"),
            "total_concepts": len(concepts),
            "total_intents": len(intents),
            "total_keywords": total_keywords,
            "min_confidence_threshold": self._min_confidence,
        }


# ---- Singleton ----
_nlu_service: Optional[NLUService] = None


def get_nlu_service() -> Optional[NLUService]:
    """Retourne l'instance NLU (lazy loading, singleton).
    Retourne None si le fichier de concepts n'existe pas.
    """
    global _nlu_service
    if _nlu_service is not None:
        return _nlu_service

    # Chercher le fichier nlu_concepts.json relatif à ce module
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)
    ))))
    concepts_path = os.path.join(base_dir, "dictionnaires", "nlu_concepts.json")

    if not os.path.exists(concepts_path):
        logger.warning(f"[NLU] Fichier non trouvé: {concepts_path} — NLU désactivé")
        return None

    try:
        _nlu_service = NLUService(concepts_path)
        return _nlu_service
    except Exception as e:
        logger.error(f"[NLU] Erreur chargement: {e}")
        return None


# ---- NLU baoulé (ADR-0045) ----
_nlu_service_bci: Optional[NLUService] = None


def _dictionnaires_dir() -> str:
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
        "dictionnaires",
    )


def build_bci_config(bci: dict, base: dict) -> dict:
    """Config du NLU baoulé : concepts et mots-clés baoulé, intents du dioula.

    Les intents ne sont jamais recopiés dans nlu_concepts_bci.json : une seule
    définition, celle de nlu_concepts.json, sert les deux langues.
    """
    return {
        "version": bci.get("version", "?"),
        "concepts": bci.get("concepts", {}),
        "intents": base.get("intents", []),
        "out_of_scope_response": base.get("out_of_scope_response", {}),
    }


def get_nlu_service_bci() -> Optional[NLUService]:
    """NLU baoulé (singleton, lazy) ; None si dictionnaires/nlu_concepts_bci.json est absent."""
    global _nlu_service_bci
    if _nlu_service_bci is not None:
        return _nlu_service_bci
    bci_path = os.path.join(_dictionnaires_dir(), "nlu_concepts_bci.json")
    base_path = os.path.join(_dictionnaires_dir(), "nlu_concepts.json")
    if not os.path.exists(bci_path):
        logger.warning(f"[NLU-BCI] Fichier non trouvé: {bci_path} — NLU baoulé désactivé")
        return None
    try:
        with open(bci_path, "r", encoding="utf-8") as f:
            bci = json.load(f)
        with open(base_path, "r", encoding="utf-8") as f:
            base = json.load(f)
        _nlu_service_bci = NLUService(config=build_bci_config(bci, base), min_confidence=0.0)
        return _nlu_service_bci
    except Exception as e:
        logger.error(f"[NLU-BCI] Erreur chargement: {e}")
        return None
