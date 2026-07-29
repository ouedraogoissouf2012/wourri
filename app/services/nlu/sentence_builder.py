"""
WOURI - NLU Constructeur de Phrases
Reconstruit une phrase française claire et complète à partir de l'intent et des concepts.

Principe: au lieu de traduire mot-à-mot, on RECONSTRUIT une phrase structurée
qui correspond au sens de ce que l'agriculteur a voulu dire.

Exemple:
  Intent: CONSEIL_PRODUCTION
  Concepts: CULTURE_MAIS, ROLE_PROPRIETAIRE, INTENSITE_FORT, SALUTATION
  → "Bonjour, je suis propriétaire d'un champ de maïs et je cherche des conseils pour avoir une grande production."

Cette phrase est ensuite envoyée à DeepSeek qui peut répondre précisément.
"""
from typing import Dict, Optional


# Labels français pour les cultures
CULTURE_LABELS = {
    "CULTURE_RIZ": "riz",
    "CULTURE_MAIS": "maïs",
    "CULTURE_MIL": "mil",
    "CULTURE_SORGHO": "sorgho",
    "CULTURE_ARACHIDE": "arachide",
    "CULTURE_IGNAME": "igname",
    "CULTURE_MANIOC": "manioc",
    "CULTURE_HARICOT": "haricot",
    "CULTURE_COTON": "coton",
    "CULTURE_SESAME": "sésame",
    "CULTURE_BANANE": "banane",
    "CULTURE_TOMATE": "tomate",
    "CULTURE_OIGNON": "oignon",
    "CULTURE_PATATE": "patate douce",
    "CULTURE_GOMBO": "gombo",
    "CULTURE_CACAO": "cacao",
    "CULTURE_CAFE": "café",
    "CULTURE_ANANAS": "ananas",
    "CULTURE_MANGUE": "mangue",
    "CULTURE_AGRUMES": "agrumes",
    "CULTURE_NERE": "néré",
    "CULTURE_ANACARDE": "anacarde",
    "CULTURE_PALMIER_HUILE": "palmier à huile",
}

# Labels français pour les animaux
ANIMAL_LABELS = {
    "ANIMAL_POULET": "poulets",
    "ANIMAL_BOVIN": "bovins",
    "ANIMAL_OVIN": "moutons",
    "ANIMAL_CAPRIN": "chèvres",
    "ANIMAL_PORC": "porcs",
    "ANIMAL_POISSON": "poissons (pisciculture)",
}

# Articles pour les cultures (pour "culture du/de la/de l'...")
CULTURE_ARTICLES = {
    "riz": "du",
    "maïs": "du",
    "mil": "du",
    "sorgho": "du",
    "arachide": "de l'",
    "igname": "de l'",
    "manioc": "du",
    "haricot": "du",
    "coton": "du",
    "sésame": "du",
    "banane": "de la",
    "tomate": "de la",
    "oignon": "de l'",
    "patate douce": "de la",
    "gombo": "du",
    "cacao": "du",
    "café": "du",
    "ananas": "de l'",
    "mangue": "de la",
    "agrumes": "des",
    "néré": "du",
    "anacarde": "de l'",
    "palmier à huile": "du",
}


def _get_article(culture_label: str) -> str:
    """Retourne l'article correct pour une culture."""
    return CULTURE_ARTICLES.get(culture_label, "du")


class SentenceBuilder:
    """Reconstruit une phrase française claire depuis l'intent et les concepts."""

    def build(
        self,
        intent: str,
        concepts: Dict[str, float],
        matched_data: Dict,
        out_of_scope_response: Optional[str] = None
    ) -> Optional[str]:
        """Construit la phrase française.

        Args:
            intent: Nom de l'intent (ex: "CONSEIL_PRODUCTION")
            concepts: Dict des concepts trouvés
            matched_data: Données supplémentaires du classificateur
            out_of_scope_response: Message hors-sujet (si intent == HORS_SUJET)

        Returns:
            Phrase française reconstruite, ou None si:
            - intent == HORS_SUJET (utiliser out_of_scope_response)
            - intent == SALUTATION_SEULE (pas de reconstruction nécessaire)
        """
        if intent == "HORS_SUJET":
            return None

        if intent == "SALUTATION_SEULE":
            return None

        # Récupérer l'entité principale (culture ou animal)
        culture_label = None
        animal_label = None

        if "culture_concept" in matched_data:
            culture_label = CULTURE_LABELS.get(matched_data["culture_concept"])

        if "animal_concept" in matched_data:
            animal_label = ANIMAL_LABELS.get(matched_data["animal_concept"])

        # Si pas d'entité dans matched_data, chercher dans concepts
        if not culture_label:
            for cn in concepts:
                if cn.startswith("CULTURE_") and cn in CULTURE_LABELS:
                    culture_label = CULTURE_LABELS[cn]
                    break
        if not animal_label and not culture_label:
            for cn in concepts:
                if cn.startswith("ANIMAL_") and cn in ANIMAL_LABELS:
                    animal_label = ANIMAL_LABELS[cn]
                    break

        entity = culture_label or animal_label or "ma culture"
        article = _get_article(culture_label) if culture_label else "de"
        entity_with_article = f"{article} {entity}" if article and entity != "ma culture" else entity

        # Extraire les métadonnées
        has_greeting = matched_data.get("has_greeting", False)
        has_role = matched_data.get("has_role", False)
        has_intensite = matched_data.get("has_intensite", False)
        has_insecte = matched_data.get("has_insecte", False)
        has_maladie = matched_data.get("has_maladie", False)
        has_secheresse = matched_data.get("has_secheresse", False)
        has_engrais = matched_data.get("has_engrais", False)
        has_arrosage = matched_data.get("has_arrosage", False)
        has_recolte = matched_data.get("has_recolte", False)
        has_plantation = matched_data.get("has_plantation", False)
        has_stockage = matched_data.get("has_stockage", False)
        has_vente = matched_data.get("has_vente", False)
        saison = matched_data.get("saison")

        sentence = self._build_sentence(
            intent, entity, entity_with_article, article,
            has_role, has_intensite, has_insecte, has_maladie,
            has_secheresse, has_engrais, has_arrosage, has_recolte,
            has_plantation, has_stockage, has_vente, saison
        )

        if sentence and has_greeting:
            # Mettre en minuscule la première lettre après "Bonjour, "
            sentence = f"Bonjour, {sentence[0].lower()}{sentence[1:]}"

        return sentence

    def _build_sentence(
        self, intent, entity, entity_with_article, article,
        has_role, has_intensite, has_insecte, has_maladie,
        has_secheresse, has_engrais, has_arrosage, has_recolte,
        has_plantation, has_stockage, has_vente, saison
    ) -> Optional[str]:
        """Construit la phrase selon l'intent."""

        if intent == "CONSEIL_PRODUCTION":
            if has_role and has_intensite:
                return (
                    f"Je suis propriétaire d'un champ {entity_with_article} "
                    f"et je cherche des conseils pour avoir une grande production."
                )
            elif has_role:
                return (
                    f"Je suis propriétaire d'un champ {entity_with_article} "
                    f"et je cherche des conseils pour améliorer ma production."
                )
            elif has_intensite:
                return (
                    f"Je cultive {entity_with_article} "
                    f"et je veux savoir comment maximiser ma récolte."
                )
            else:
                return (
                    f"Je cherche des conseils pour cultiver {entity_with_article} "
                    f"et avoir une bonne récolte."
                )

        elif intent == "QUESTION_SAISON_PLANTATION":
            if saison == "pluie":
                return (
                    f"Est-ce que c'est la bonne saison des pluies pour planter {entity_with_article} ?"
                )
            elif saison == "seche":
                return (
                    f"Peut-on planter {entity_with_article} pendant la saison sèche ?"
                )
            else:
                return (
                    f"Quelle est la meilleure saison pour planter {entity_with_article} dans ma région ?"
                )

        elif intent == "DIAGNOSTIC_PROBLEME":
            if has_insecte and has_maladie:
                return (
                    f"Mon {entity} est malade et attaqué par des insectes. "
                    f"Que dois-je faire pour le sauver ?"
                )
            elif has_insecte:
                return (
                    f"Des insectes attaquent mon {entity}. "
                    f"Quel traitement utiliser pour les éliminer ?"
                )
            elif has_secheresse:
                return (
                    f"Mon {entity} manque d'eau à cause de la sécheresse. "
                    f"Comment gérer l'irrigation ?"
                )
            elif has_maladie:
                return (
                    f"Mon {entity} est malade, les plantes ne poussent pas bien. "
                    f"Quels sont les symptômes possibles et les traitements ?"
                )
            else:
                return (
                    f"J'ai un problème avec mon {entity}. "
                    f"Que faire pour résoudre ce problème ?"
                )

        elif intent == "QUESTION_RECOLTE":
            if saison:
                return (
                    f"Quand et comment récolter {entity_with_article} "
                    f"{'pendant la saison des pluies' if saison == 'pluie' else 'en cette saison'} ?"
                )
            return f"Quand et comment récolter {entity_with_article} ?"

        elif intent == "QUESTION_IRRIGATION":
            if has_secheresse:
                return (
                    f"Mon {entity} manque d'eau. "
                    f"Comment arroser et irriguer pendant la saison sèche ?"
                )
            return (
                f"Comment arroser correctement mon {entity} "
                f"pour avoir une bonne récolte ?"
            )

        elif intent == "QUESTION_ENGRAIS":
            return (
                f"Quels engrais ou fertilisants utiliser pour mon {entity} "
                f"pour améliorer le rendement ?"
            )

        elif intent == "QUESTION_STOCKAGE":
            return (
                f"Comment conserver et stocker {entity_with_article} "
                f"après la récolte pour éviter les pertes ?"
            )

        elif intent == "QUESTION_VENTE":
            if article == "de":  # animal (labels au pluriel : porcs, moutons, chèvres…)
                return f"Comment et où vendre mes {entity} pour avoir le meilleur prix ?"
            return f"Comment et où vendre {entity_with_article} pour avoir le meilleur prix ?"

        elif intent == "QUESTION_ELEVAGE":
            if has_insecte or has_maladie:
                return (
                    f"Mes {entity} sont malades. "
                    f"Quels sont les symptômes et traitements possibles ?"
                )
            elif has_intensite:
                return (
                    f"Je fais de l'élevage de {entity} "
                    f"et je cherche des conseils pour augmenter ma production."
                )
            else:
                return (
                    f"Je cherche des conseils pour mon élevage de {entity}. "
                    f"Que dois-je savoir ?"
                )

        elif intent == "QUESTION_METEO_AGRICOLE":
            if entity != "ma culture":
                return (
                    f"Quelles conditions météo sont favorables pour cultiver "
                    f"{entity_with_article} dans ma région ?"
                )
            return (
                "Quelles sont les conditions météo actuelles "
                "et leur impact sur l'agriculture ?"
            )

        elif intent == "QUESTION_GENERALE":
            if entity == "ma culture":
                # Pas de culture précise → question du type "quoi cultiver sur ma terre ?"
                if has_plantation:
                    return "Quelles cultures puis-je planter dans ma région, et lesquelles sont les plus rentables ?"
                return "Je cherche des conseils agricoles. Quelle culture me recommandez-vous pour ma région ?"
            return f"J'ai une question sur la culture {entity_with_article}."

        return None
