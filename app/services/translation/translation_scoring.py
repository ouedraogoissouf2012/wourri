"""
WOURI - Scoring et filtrage des candidats de traduction (dictionnaire Bamadaba).

Extrait de word_translator.py (modularisation 2026-08) : ce module regroupe la
sélection/qualité des candidats de traduction — filtrage des annotations
grammaticales Bamadaba et scoring heuristique du meilleur candidat. C'est un
concern pur (aucune dépendance au repository ni au contrat ITranslator), donc
testable en isolation sans instancier WordTranslator.
"""
import re


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
