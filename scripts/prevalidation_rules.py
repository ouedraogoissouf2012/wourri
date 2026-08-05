"""Noyau AUTOMATISABLE de la prévalidation dioula CI (méthode Codex).

Ce module regroupe, sous forme de tables Python versionnées et de fonctions
pures et déterministes, le sous-ensemble de la spécification de prévalidation
qui peut être appliqué sans jugement humain :

  * §3.1 — substitutions lexicales CONDITIONNELLES (au sens, pas au mot) ;
  * §3.2 — normalisations orthographiques par table EXPLICITE (jamais de regex
           générale sur les voyelles) ;
  * §3.3 — rejets sémantiques (faux-amis) : SIGNALÉS, jamais remplacés ;
  * §4.7 — glossaire fermé des mois ;
  * §6   — score de PRÉPARATION à la validation (`calculate_confidence`) ;
  * §7.3 — schéma JSON de la proposition + validateur autonome.

Principe directeur de la spec (§ règle finale) :

    L'IA propose. Le script contrôle. Le natif tranche.

Concrètement, dans ce module :
  * la NORMALISATION ORTHOGRAPHIQUE de §3.2 est déterministe → appliquée ;
  * la SUBSTITUTION LEXICALE de §3.1 n'est appliquée QUE si le sens français
    de référence lève l'ambiguïté (marché → lɔgɔ) ; sinon → à confirmer ;
  * TOUT le reste (faux-amis, choix de synonyme, ravageur, naturalité orale…)
    reste au natif : SIGNALÉ dans les alertes ou dans `termes_a_confirmer`,
    JAMAIS résolu automatiquement.

Aucune dépendance externe : le validateur JSON (§7.3) est implémenté ici même
pour ne pas imposer `jsonschema` au projet.

Encodage : ce module manipule des caractères dioula (ɛ ɔ ɲ ŋ). Toute écriture
console doit se faire avec PYTHONIOENCODING=utf-8.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

# Version des tables. À incrémenter à chaque évolution des données de règles,
# indépendamment du code, pour tracer quelles règles ont produit une proposition.
RULES_VERSION = "1.0.0"


# ---------------------------------------------------------------------------
# §3.1 — Substitutions lexicales CONDITIONNELLES (au SENS français, pas au mot)
# ---------------------------------------------------------------------------
#
# NUANCE CRITIQUE (spec §3.1, note) :
#   `sugu` et `kosɛbɛ` NE sont PAS bannis de façon absolue. Le lexique dioula
#   CI (Mandenkan) les atteste : sugu = sorte/espèce, kosɛbɛ = beaucoup/très.
#   La règle WOURI est CONDITIONNELLE au SENS français de référence :
#     - « marché » → lɔgɔ (donc on ne remplace sugu QUE si le FR dit « marché ») ;
#     - « beaucoup / très » → caman (préférence éditoriale WOURI).
#   Un mot sans condition levée par le français ne doit PAS être substitué :
#   il part dans `termes_a_confirmer`.
#
# Structure de chaque règle :
#   rule_id            : identifiant stable (traçabilité `regles_appliquees`).
#   source_form        : forme dioula détectée (frontière de mot).
#   wouri_form         : forme WOURI de remplacement.
#   french_triggers    : lemmes français (minuscules, sans accents) dont la
#                        présence dans la référence FR lève l'ambiguïté de sens.
#                        Tuple vide => sens toujours déterminable (ex. mois),
#                        la substitution s'applique sans condition FR.
#   conditional        : True => n'appliquer QUE si un trigger FR est présent ;
#                        sinon la forme part dans `termes_a_confirmer`.
#   note               : explication humaine (affichée au natif).


@dataclass(frozen=True)
class LexicalSubstitution:
    rule_id: str
    source_form: str
    wouri_form: str
    french_triggers: tuple[str, ...]
    conditional: bool
    note: str


LEXICAL_SUBSTITUTIONS: tuple[LexicalSubstitution, ...] = (
    LexicalSubstitution(
        rule_id="LEX-MARKET-001",
        source_form="sugu",
        wouri_form="lɔgɔ",
        french_triggers=("marche", "marches"),  # « marché » sans accents
        conditional=True,
        note=(
            "sugu → lɔgɔ UNIQUEMENT quand le sens français est « marché ». "
            "sugu reste valide au sens « sorte/espèce » (Mandenkan CI) : "
            "ne pas substituer sans condition."
        ),
    ),
    LexicalSubstitution(
        rule_id="LEX-QUANTITY-001",
        source_form="kosɛbɛ",
        wouri_form="caman",
        french_triggers=("beaucoup", "tres", "enormement", "abondamment"),
        conditional=True,
        note=(
            "kosɛbɛ → caman : préférence éditoriale WOURI pour « beaucoup/très ». "
            "kosɛbɛ n'est pas fautif (attesté « beaucoup ») : substitution "
            "seulement si le français exprime la quantité/intensité."
        ),
    ),
    LexicalSubstitution(
        rule_id="LEX-MONTH-001",
        source_form="karo",
        wouri_form="kalo",
        french_triggers=(),  # « mois » : sens toujours univoque en dioula.
        conditional=False,
        note="karo → kalo (mois). Forme CI validée (PR #84).",
    ),
    LexicalSubstitution(
        rule_id="LEX-TIME-001",
        source_form="waati",
        wouri_form="tuma",
        french_triggers=(),
        conditional=False,
        note="waati → tuma (moment/temps). Validation native #51.",
    ),
    LexicalSubstitution(
        rule_id="LEX-TIME-002",
        source_form="wagati",
        wouri_form="tuma",
        french_triggers=(),
        conditional=False,
        note="wagati → tuma (moment/temps).",
    ),
    LexicalSubstitution(
        rule_id="LEX-AGENT-001",
        source_form="sɛnnɛkɛla",
        wouri_form="sɛnɛbaga",
        french_triggers=(),
        conditional=False,
        note="sɛnnɛkɛla → sɛnɛbaga (cultivateur/agent). Validation native.",
    ),
)


# ---------------------------------------------------------------------------
# §3.2 — Normalisations orthographiques : TABLE EXPLICITE (jamais de regex)
# ---------------------------------------------------------------------------
#
# CONTRAINTE ABSOLUE (spec §3.2 + §9) :
#   On corrige UNIQUEMENT les mots EXACTS listés ici. Aucune regex générale de
#   dédoublement de voyelles : une telle regex écraserait des longueurs
#   vocaliques linguistiques légitimes (naani=4, duuru=5, bɛɛ=tous, joona…).
#   `apply_orthographic_map` respecte la casse du token source.
#
# Clé  : forme fautive telle qu'observée (déjà en minuscules pour l'appariement).
# Valeur:
#   rule_id : identifiant de règle orthographique (traçabilité).
#   target  : forme canonique.

ORTHOGRAPHIC_MAP: dict[str, dict[str, str]] = {
    "foroo": {"rule_id": "ORTH-FIELD-001", "target": "foro"},
    "dugukoloo": {"rule_id": "ORTH-SOIL-001", "target": "dugukolo"},
    "sanjiii": {"rule_id": "ORTH-RAIN-001", "target": "sanji"},
    "mɛɛɛ": {"rule_id": "ORTH-MONTH-MAY-001", "target": "Mɛ"},
    "sɛtanburuuu": {"rule_id": "ORTH-MONTH-SEP-001", "target": "Sɛtanburu"},
    "marisiii": {"rule_id": "ORTH-MONTH-MAR-001", "target": "Marisi"},
    "desanburuuu": {"rule_id": "ORTH-MONTH-DEC-001", "target": "Desanburu"},
    "awiriliiii": {"rule_id": "ORTH-MONTH-APR-001", "target": "Awirili"},
}


# ---------------------------------------------------------------------------
# §3.3 — Rejets sémantiques (faux-amis) : SIGNALER, JAMAIS remplacer auto
# ---------------------------------------------------------------------------
#
# Ces formes ont un sens attesté DIFFÉRENT de celui parfois visé. Le script ne
# fait que les SIGNALER (dans les alertes / `termes_a_confirmer`). Le natif
# tranche. On distingue deux niveaux d'action :
#   "reject"  : faux-ami avéré (le sens visé est faux) → alerte forte.
#   "flag"    : à faire confirmer / trop général → alerte de vérification.
#
# Structure :
#   form          : forme dioula concernée.
#   wrong_sense   : sens erroné observé (contexte du signalement).
#   attested_sense: sens réellement attesté (pour l'alerte).
#   action        : "reject" | "flag".


@dataclass(frozen=True)
class SemanticRejection:
    form: str
    wrong_sense: str
    attested_sense: str
    action: str  # "reject" | "flag"


SEMANTIC_REJECTIONS: tuple[SemanticRejection, ...] = (
    SemanticRejection("bɔrɔ", "pourrir", "sac", "reject"),
    SemanticRejection("tulu", "butte", "huile", "reject"),
    SemanticRejection("dunbu", "butte", "à tester (tugun/tunkun)", "flag"),
    SemanticRejection("kulun", "insecte/cochenille", "pirogue", "reject"),
    SemanticRejection("hɛrɛ", "outil tranchant", "paix/bonheur", "reject"),
    SemanticRejection("sira", "feuille/tige", "route/chemin", "reject"),
    SemanticRejection("kɔnɔnin", "ombre/stockage", "oiseau", "reject"),
    SemanticRejection("dɔlɔ", "huilerie", "boisson de céréales", "reject"),
    SemanticRejection("jira", "variété végétale", "montrer", "reject"),
    SemanticRejection("kɔlɔ", "commerçant", "sens à valider", "flag"),
    SemanticRejection("bolo", "tige/bouture/plant", "trop général", "flag"),
    SemanticRejection("jɛ", "avoir besoin de", "pas de remplacement auto", "flag"),
    SemanticRejection("fura", "feuille", "accepter seulement si organe = feuille", "flag"),
    SemanticRejection("cɛn", "gâter/pourrir", "à confirmer par contexte", "flag"),
    SemanticRejection("toli", "pourrir", "à confirmer selon sujet", "flag"),
)


# ---------------------------------------------------------------------------
# §4.7 — Glossaire fermé des mois
# ---------------------------------------------------------------------------
#
# Mois VALIDÉS (français sans accents → forme dioula CI canonique). Les mois
# absents de cette table ne sont JAMAIS déduits du français : ils partent en
# `termes_a_confirmer` (spec §4.7).

MONTHS_GLOSSARY: dict[str, str] = {
    "janvier": "Zanviye",
    "mars": "Marisi",
    "avril": "Awirili",
    "mai": "Mɛ",
    "septembre": "Sɛtanburu",
    "decembre": "Desanburu",
}


# ---------------------------------------------------------------------------
# Sigles / loanwords à préserver tels quels (§4.6). Pas de translittération.
# ---------------------------------------------------------------------------

PRESERVED_TOKENS: frozenset[str] = frozenset(
    {"NPK", "ANADER", "TMS", "IITA", "gari"}
)

# Placeholders météo à préserver intacts (ex. {{METEO_PLUIE_J3}}).
_PLACEHOLDER_RE = re.compile(r"\{\{[A-Z0-9_]+\}\}")


# ---------------------------------------------------------------------------
# Outils de tokenisation dioula
# ---------------------------------------------------------------------------
#
# Un « mot » dioula = suite de lettres latines + caractères spéciaux (ɛ ɔ ɲ ŋ)
# + chiffres (pour NPK 15-15-15, on garde les tokens alphanumériques séparés).
_WORD_RE = re.compile(r"[A-Za-zɛɔɲŋ]+")


def _strip_accents(text: str) -> str:
    """Retire les accents FR pour l'appariement des triggers/mois.

    On NE touche PAS aux caractères dioula (ɛ ɔ ɲ ŋ) : ce sont des lettres à
    part entière, pas des variantes accentuées de a/e/o. On décompose donc en
    NFD puis on ne supprime que les diacritiques combinants des lettres
    latines de base — les caractères dioula restent tels quels car ils sont
    hors décomposition NFD pour ce besoin.
    """
    decomposed = unicodedata.normalize("NFD", text)
    return "".join(
        ch for ch in decomposed if unicodedata.category(ch) != "Mn"
    )


def _match_case(source_token: str, replacement: str) -> str:
    """Aligne la casse initiale du remplacement sur le token source.

    Si le token source commence par une majuscule (ex. « Mɛɛɛ »), on met la
    première lettre du remplacement en majuscule ; sinon, on laisse la forme
    telle que définie dans la table (qui porte déjà la casse canonique, ex.
    « Marisi » comme nom de mois).
    """
    if source_token[:1].isupper():
        return replacement[:1].upper() + replacement[1:]
    return replacement


# ---------------------------------------------------------------------------
# §3.2 — application de la normalisation orthographique (table uniquement)
# ---------------------------------------------------------------------------


@dataclass
class OrthographicResult:
    text: str
    applied_rules: list[str] = field(default_factory=list)


def apply_orthographic_map(text: str) -> OrthographicResult:
    """Applique la table §3.2 aux MOTS EXACTS uniquement (aucune regex).

    Chaque token du texte est comparé (en minuscules) aux clés de
    ORTHOGRAPHIC_MAP. Seuls les tokens correspondant EXACTEMENT à une clé sont
    remplacés. Aucun autre mot n'est touché — en particulier les voyelles
    longues linguistiques légitimes (naani, duuru, bɛɛ…) sont préservées.

    Retourne le texte corrigé et la liste des `rule_id:src→target` appliqués.
    """
    applied: list[str] = []

    def _replace(match: re.Match[str]) -> str:
        token = match.group(0)
        entry = ORTHOGRAPHIC_MAP.get(token.lower())
        if entry is None:
            return token
        target = _match_case(token, entry["target"])
        applied.append(f"{entry['rule_id']}:{token}→{target}")
        return target

    corrected = _WORD_RE.sub(_replace, text)
    return OrthographicResult(text=corrected, applied_rules=applied)


# ---------------------------------------------------------------------------
# §3.1 — application des substitutions lexicales CONDITIONNELLES
# ---------------------------------------------------------------------------


@dataclass
class LexicalResult:
    text: str
    applied_rules: list[str] = field(default_factory=list)
    to_confirm: list[str] = field(default_factory=list)


def _word_boundary_pattern(form: str) -> re.Pattern[str]:
    """Frontière de mot tenant compte des lettres dioula (ɛ ɔ ɲ ŋ)."""
    return re.compile(
        rf"(?<![a-zɛɔɲŋ]){re.escape(form)}(?![a-zɛɔɲŋ])",
        re.IGNORECASE,
    )


def apply_lexical_substitutions(
    text: str, french_reference: str
) -> LexicalResult:
    """Applique §3.1 en respectant la CONDITION de sens français.

    - Règle NON conditionnelle (mois, temps, agent) : appliquée dès que la
      forme source est présente (sens univoque en dioula).
    - Règle CONDITIONNELLE (sugu→lɔgɔ, kosɛbɛ→caman) : appliquée UNIQUEMENT
      si un des `french_triggers` apparaît dans la référence française. Sinon,
      la forme est SIGNALÉE dans `to_confirm` et laissée intacte (le natif
      tranche le sens).
    """
    applied: list[str] = []
    to_confirm: list[str] = []
    fr_norm = _strip_accents(french_reference.lower())
    result_text = text

    for rule in LEXICAL_SUBSTITUTIONS:
        pattern = _word_boundary_pattern(rule.source_form)
        if not pattern.search(result_text):
            continue

        if rule.conditional:
            triggered = any(
                re.search(rf"(?<![a-z]){re.escape(t)}(?![a-z])", fr_norm)
                for t in rule.french_triggers
            )
            if not triggered:
                to_confirm.append(
                    f"{rule.source_form} : sens ambigu — {rule.note} "
                    f"(aucun déclencheur français détecté)"
                )
                continue

        result_text = pattern.sub(rule.wouri_form, result_text)
        applied.append(
            f"{rule.rule_id}:{rule.source_form}→{rule.wouri_form}"
        )

    return LexicalResult(
        text=result_text, applied_rules=applied, to_confirm=to_confirm
    )


# ---------------------------------------------------------------------------
# §3.3 — détection des faux-amis (signalement seulement)
# ---------------------------------------------------------------------------


def detect_semantic_alerts(text: str) -> list[dict[str, str]]:
    """Détecte les faux-amis présents dans le texte (§3.3).

    Ne modifie JAMAIS le texte. Retourne une liste d'alertes structurées à
    présenter au natif. `action` = "reject" (faux-ami avéré) ou "flag".
    """
    alerts: list[dict[str, str]] = []
    for rej in SEMANTIC_REJECTIONS:
        if _word_boundary_pattern(rej.form).search(text):
            alerts.append(
                {
                    "form": rej.form,
                    "wrong_sense": rej.wrong_sense,
                    "attested_sense": rej.attested_sense,
                    "action": rej.action,
                }
            )
    return alerts


# ---------------------------------------------------------------------------
# §6 — Score de PRÉPARATION à la validation (PAS une probabilité scientifique)
# ---------------------------------------------------------------------------
#
# IMPORTANT (spec §6) : `calculate_confidence` ne renvoie PAS une probabilité
# d'exactitude. C'est un « score de préparation à la validation » : à quel
# point une proposition est prête à être soumise au natif. Il ne remplace
# jamais la validation native (qui reste TOUJOURS requise).

# Poids (spec §6). Somme = 1.0.
_WEIGHTS = {
    "S": 0.25,  # fidélité sémantique au français
    "G": 0.20,  # conformité glossaire WOURI
    "E": 0.15,  # preuves lexicales (2 sources CI)
    "Y": 0.15,  # syntaxe (SOV, impératif)
    "O": 0.10,  # orthographe canonique
    "A": 0.15,  # justesse agronomique
}

# Plafond global obligatoire : le script ne PROPOSE jamais mieux que 0.89.
HARD_CAP = 0.89

# Plafonds spécifiques (spec §6). Le plus contraignant présent l'emporte.
CAP_UNCONFIRMED_TECHNICAL = 0.74  # terme technique majeur non confirmé
CAP_SOURCE_CONTRADICTION = 0.64  # contradiction entre 2 sources
CAP_UNVERIFIED_AGRONOMY = 0.59  # conseil agronomique non vérifié
CAP_PESTICIDE_NO_DOSAGE = 0.49  # pesticide/mélange sans dosage
CAP_POSSIBLE_CONTRESENS = 0.39  # contresens possible


@dataclass(frozen=True)
class ConfidenceCaps:
    """Drapeaux déclenchant les plafonds spécifiques de §6."""

    unconfirmed_technical_term: bool = False
    source_contradiction: bool = False
    unverified_agronomy: bool = False
    pesticide_without_dosage: bool = False
    possible_contresens: bool = False


def calculate_confidence(
    S: float,
    G: float,
    Y: float,
    O: float,
    A: float,
    *,
    E: float = 0.0,
    caps: ConfidenceCaps | None = None,
) -> float:
    """Calcule le score de préparation à la validation (§6).

    Formule : 0.25*S + 0.20*G + 0.15*E + 0.15*Y + 0.10*O + 0.15*A.

    Chaque sous-score est dans [0, 1] (échelons typiques 0/0.25/0.5/0.75/1).
    `E` (preuves lexicales) est optionnel avec valeur par défaut 0.0 car il
    dépend de la disponibilité de 2 sources CI, souvent inconnue au stade
    automatique — le laisser bas est prudent (score plus bas = plus de
    vérification native).

    PLAFONDS (spec §6) :
      - `HARD_CAP` = 0.89 appliqué TOUJOURS ;
      - puis les plafonds spécifiques actifs via `caps`, le plus bas gagne.

    Le résultat n'est JAMAIS > 0.89. Il ne dispense JAMAIS de la validation
    native.
    """
    for name, value in (("S", S), ("G", G), ("E", E), ("Y", Y), ("O", O), ("A", A)):
        if not 0.0 <= value <= 1.0:
            raise ValueError(f"Sous-score {name}={value} hors de [0, 1].")

    raw = (
        _WEIGHTS["S"] * S
        + _WEIGHTS["G"] * G
        + _WEIGHTS["E"] * E
        + _WEIGHTS["Y"] * Y
        + _WEIGHTS["O"] * O
        + _WEIGHTS["A"] * A
    )

    ceiling = HARD_CAP
    if caps is not None:
        if caps.unconfirmed_technical_term:
            ceiling = min(ceiling, CAP_UNCONFIRMED_TECHNICAL)
        if caps.source_contradiction:
            ceiling = min(ceiling, CAP_SOURCE_CONTRADICTION)
        if caps.unverified_agronomy:
            ceiling = min(ceiling, CAP_UNVERIFIED_AGRONOMY)
        if caps.pesticide_without_dosage:
            ceiling = min(ceiling, CAP_PESTICIDE_NO_DOSAGE)
        if caps.possible_contresens:
            ceiling = min(ceiling, CAP_POSSIBLE_CONTRESENS)

    return round(min(raw, ceiling), 4)


# ---------------------------------------------------------------------------
# §7.3 — Schéma JSON de la proposition + validateur autonome
# ---------------------------------------------------------------------------
#
# Schéma décrit en JSON-Schema-like (draft-07 subset). Le validateur
# `validate_proposition` est implémenté ici pour éviter la dépendance
# `jsonschema`. Il couvre : type d'objet, propriétés requises, absence de clés
# additionnelles, types, bornes numériques, `const`, `minItems`, non-vacuité
# des chaînes.

PROPOSITION_SCHEMA: dict = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "PrevalidationProposition",
    "type": "object",
    "additionalProperties": False,
    "required": [
        "entry_id",
        "french_reference",
        "proposition_dioula_ci",
        "regles_appliquees",
        "termes_a_confirmer",
        "confiance",
        "necessite_validation_native",
        "note_pour_le_natif",
    ],
    "properties": {
        "entry_id": {"type": "string", "minLength": 1},
        "french_reference": {"type": "string", "minLength": 1},
        "proposition_dioula_ci": {"type": "string", "minLength": 1},
        "regles_appliquees": {
            "type": "array",
            "items": {"type": "string", "minLength": 1},
        },
        "termes_a_confirmer": {
            "type": "array",
            "items": {"type": "string", "minLength": 1},
        },
        "confiance": {"type": "number", "minimum": 0.0, "maximum": 0.89},
        "necessite_validation_native": {"type": "boolean", "const": True},
        "note_pour_le_natif": {"type": "string", "minLength": 1},
    },
}


class SchemaValidationError(ValueError):
    """Erreur de validation d'une proposition contre PROPOSITION_SCHEMA."""


def _validate_type(value: object, json_type: str, path: str) -> None:
    ok = {
        "object": lambda v: isinstance(v, dict),
        "array": lambda v: isinstance(v, list),
        "string": lambda v: isinstance(v, str),
        # bool est sous-type de int en Python : exclure explicitement les bools
        # des nombres, et n'accepter que les bools pour "boolean".
        "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
        "boolean": lambda v: isinstance(v, bool),
    }[json_type]
    if not ok(value):
        raise SchemaValidationError(
            f"{path}: type attendu '{json_type}', reçu {type(value).__name__}."
        )


def _validate_against(value: object, schema: dict, path: str) -> None:
    json_type = schema.get("type")
    if json_type:
        _validate_type(value, json_type, path)

    if json_type == "object":
        assert isinstance(value, dict)
        required = schema.get("required", [])
        for key in required:
            if key not in value:
                raise SchemaValidationError(f"{path}: propriété requise '{key}' absente.")
        if schema.get("additionalProperties") is False:
            allowed = set(schema.get("properties", {}))
            extra = set(value) - allowed
            if extra:
                raise SchemaValidationError(
                    f"{path}: propriétés non autorisées {sorted(extra)}."
                )
        for key, subschema in schema.get("properties", {}).items():
            if key in value:
                _validate_against(value[key], subschema, f"{path}.{key}")

    elif json_type == "array":
        assert isinstance(value, list)
        min_items = schema.get("minItems")
        if min_items is not None and len(value) < min_items:
            raise SchemaValidationError(
                f"{path}: minItems={min_items}, reçu {len(value)}."
            )
        item_schema = schema.get("items")
        if item_schema:
            for i, item in enumerate(value):
                _validate_against(item, item_schema, f"{path}[{i}]")

    elif json_type == "string":
        assert isinstance(value, str)
        min_length = schema.get("minLength")
        if min_length is not None and len(value) < min_length:
            raise SchemaValidationError(
                f"{path}: minLength={min_length}, longueur {len(value)}."
            )

    elif json_type == "number":
        assert isinstance(value, (int, float))
        minimum = schema.get("minimum")
        maximum = schema.get("maximum")
        if minimum is not None and value < minimum:
            raise SchemaValidationError(f"{path}: minimum={minimum}, reçu {value}.")
        if maximum is not None and value > maximum:
            raise SchemaValidationError(f"{path}: maximum={maximum}, reçu {value}.")

    if "const" in schema and value != schema["const"]:
        raise SchemaValidationError(
            f"{path}: valeur attendue const={schema['const']!r}, reçu {value!r}."
        )


def validate_proposition(proposition: dict) -> None:
    """Valide une proposition (§7) contre PROPOSITION_SCHEMA.

    Lève `SchemaValidationError` si la proposition est invalide. Ne renvoie
    rien en cas de succès (comme `jsonschema.validate`).
    """
    _validate_against(proposition, PROPOSITION_SCHEMA, "$")
