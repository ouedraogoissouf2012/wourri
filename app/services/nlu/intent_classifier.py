"""
WOURI - NLU Classificateur d'Intentions
Détermine l'intention d'un message bambara à partir des concepts extraits.

Logique de scoring:
- Concepts requis (required_any): au moins 1 doit être présent (+10 pts chacun)
- Concepts requis all (required_at_least_one_of): au moins 1 de cette liste (+15 pts)
- Concepts optionnels (optional): présence renforce le score (+3 pts chacun)
- Boost de priorité (priority_boost_if): si ces concepts sont présents → +8 pts
- Priorité de base de l'intent (priority): tiebreaker

L'intent avec le score le plus élevé gagne.
Score minimum pour déclencher un intent: 10 pts (= 1 concept requis trouvé).
"""
from typing import Dict, Tuple


class IntentClassifier:
    """Classifie l'intention à partir des concepts extraits."""

    def __init__(self, intents_config: list):
        # Ordonner les intents par priorité décroissante
        self._intents = sorted(
            intents_config,
            key=lambda x: x.get("priority", 0),
            reverse=True
        )

    def classify(
        self,
        concepts: Dict[str, float]
    ) -> Tuple[str, float, Dict]:
        """Classifie l'intention.

        Args:
            concepts: Dict {concept_name: confidence} retourné par ConceptExtractor

        Returns:
            Tuple (intent_name, confidence, matched_data)
            - intent_name: nom de l'intent (ex: "CONSEIL_PRODUCTION")
            - confidence: score normalisé entre 0 et 1
            - matched_data: infos utiles pour le SentenceBuilder
              {
                'culture_concept': 'CULTURE_MAIS',  # si trouvé
                'animal_concept': 'ANIMAL_POULET',  # si trouvé
                'problems': ['PROBLEME_MALADIE'],   # liste des problèmes
                'has_greeting': True/False,
                'has_role': True/False,
                'has_intensite': True/False,
                'saison': 'pluie'|'seche'|'general'|None
              }
        """
        concept_keys = set(concepts.keys())

        # ---- Cas simples immédiats ----

        # Aucun concept du tout
        if not concept_keys:
            return "HORS_SUJET", 1.0, {}

        # Salutation seule (pas de concept agricole)
        has_agri = self._has_agricultural(concept_keys)
        if not has_agri:
            if "SALUTATION" in concept_keys:
                return "SALUTATION_SEULE", 1.0, {"has_greeting": True}
            return "HORS_SUJET", 1.0, {}

        # ---- Scoring de tous les intents ----
        best_intent = "QUESTION_GENERALE"
        best_score = 0.0
        best_data = {}

        for intent_cfg in self._intents:
            intent_name = intent_cfg["name"]

            # Sauter HORS_SUJET et SALUTATION_SEULE (gérés au-dessus)
            if intent_name in ("HORS_SUJET", "SALUTATION_SEULE"):
                continue

            score = 0.0
            matched_data = {}

            # ---- required_any: au moins 1 concept parmi la liste ----
            required_any = intent_cfg.get("required_any", [])
            if required_any:
                matched_req = self._match_concept_list(required_any, concept_keys)
                if not matched_req:
                    continue  # Intent non applicable
                score += 10.0 * len(matched_req)
                # Enregistrer culture/animal principal
                self._update_entity_data(matched_req, matched_data)

            # ---- required_at_least_one_of: exactement ce type de concept ----
            required_atleast = intent_cfg.get("required_at_least_one_of", [])
            if required_atleast:
                matched_atleast = self._match_concept_list(required_atleast, concept_keys)
                if not matched_atleast:
                    continue  # Condition non remplie
                score += 15.0
                matched_data["problems"] = matched_atleast

            # ---- optional: bonus pour chaque concept optionnel présent ----
            for opt in intent_cfg.get("optional", []):
                matched_opt = self._match_concept_list([opt], concept_keys)
                score += 3.0 * len(matched_opt)

            # ---- priority_boost_if: bonus si ces concepts sont présents ----
            boost_concepts = intent_cfg.get("priority_boost_if", [])
            if boost_concepts:
                matched_boost = self._match_concept_list(boost_concepts, concept_keys)
                if matched_boost:
                    score += 8.0

            # ---- Priorité de base (tiebreaker) ----
            score += intent_cfg.get("priority", 0) * 0.5

            if score > best_score:
                best_score = score
                best_intent = intent_name
                best_data = matched_data

        # ---- Compléter matched_data avec les métadonnées utiles ----
        best_data["has_greeting"] = "SALUTATION" in concept_keys
        best_data["has_role"] = (
            "ROLE_PROPRIETAIRE" in concept_keys or
            "ROLE_AGRICULTEUR" in concept_keys
        )
        best_data["has_intensite"] = "INTENSITE_FORT" in concept_keys
        best_data["has_insecte"] = "PROBLEME_INSECTE" in concept_keys
        best_data["has_maladie"] = "PROBLEME_MALADIE" in concept_keys
        best_data["has_secheresse"] = "PROBLEME_SECHERESSE" in concept_keys
        best_data["has_engrais"] = "ENGRAIS_FERTILISANT" in concept_keys
        best_data["has_arrosage"] = "ACTION_ARROSER" in concept_keys
        best_data["has_recolte"] = "ACTION_RECOLTER" in concept_keys
        best_data["has_plantation"] = "ACTION_PLANTER" in concept_keys
        best_data["has_stockage"] = "ACTION_STOCKER" in concept_keys
        best_data["has_vente"] = "ACTION_VENDRE" in concept_keys

        if "TEMPS_SAISON_PLUIE" in concept_keys:
            best_data["saison"] = "pluie"
        elif "TEMPS_SAISON_SECHE" in concept_keys:
            best_data["saison"] = "seche"
        elif "TEMPS_SAISON_GENERAL" in concept_keys:
            best_data["saison"] = "general"
        else:
            best_data["saison"] = None

        # Normaliser la confiance (score max théorique ≈ 40)
        confidence = min(1.0, best_score / 25.0)
        return best_intent, confidence, best_data

    # ---- Méthodes privées ----

    def _has_agricultural(self, concept_keys: set) -> bool:
        """Vérifie si au moins un concept agricole est présent."""
        agri_prefixes = (
            "CULTURE_", "ANIMAL_", "ACTION_PLANTER", "ACTION_RECOLTER",
            "ACTION_ARROSER", "ACTION_LABOURER", "ACTION_TRAITER",
            "ACTION_CHERCHER_CONSEIL", "ACTION_STOCKER", "ACTION_VENDRE",
            "PROBLEME_", "TEMPS_SAISON", "ENGRAIS_", "ROLE_"
        )
        return any(
            any(k.startswith(p) for p in agri_prefixes)
            for k in concept_keys
        )

    def _match_concept_list(
        self, pattern_list: list, concept_keys: set
    ) -> list:
        """Trouve tous les concepts qui correspondent à la liste (supporte wildcards '*')."""
        matched = []
        for pattern in pattern_list:
            if pattern.endswith("*"):
                prefix = pattern[:-1]
                for k in concept_keys:
                    if k.startswith(prefix) and k not in matched:
                        matched.append(k)
            elif pattern in concept_keys:
                if pattern not in matched:
                    matched.append(pattern)
        return matched

    def _update_entity_data(self, matched_concepts: list, data: dict):
        """Met à jour culture_concept et animal_concept dans matched_data."""
        for cn in matched_concepts:
            if cn.startswith("CULTURE_") and "culture_concept" not in data:
                data["culture_concept"] = cn
            elif cn.startswith("ANIMAL_") and "animal_concept" not in data:
                data["animal_concept"] = cn
