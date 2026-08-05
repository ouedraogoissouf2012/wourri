"""Construit les JSON de pré-validation par culture (issues #56 à #68).

Pour chaque culture :
  1. VERSION A  : extraite du draft v3 `corpus_ivr_v3_full_draft.json`
                  (entrées dont l'id commence par le préfixe de la culture ;
                   champs reponse_fr -> french, reponse_bambara -> version_a).
  2. VERSION B  : extraite du diff de l'ancienne PR (fichiers .diff mis en cache),
                  appariée par id ; new_bam -> version_b. Absente => mono-version.
  3. ALERTE     : détection des mots maliens bannis et incohérences (voyelles
                  triplées) sur A et B, basée sur GRAMMAIRE_DIOULA_REGLES §12bis.
  4. REPÈRE     : termes attestés (mots bannis -> forme CI + terme culture).
  5. Écrit data/issue_<N>_<culture>_validation_draft.json (schéma issue_55_mil).

Ce script LIT le draft et les diffs mais ne les MODIFIE jamais. Il n'écrit que
dans data/issue_<N>_<culture>_validation_draft.json (brouillons de validation).
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DRAFT_PATH = PROJECT_ROOT / "dictionnaires" / "archive" / "corpus_ivr_v3_full_draft.json"
DATA_DIR = PROJECT_ROOT / "data"

# Noyau de prévalidation (méthode Codex) : tables de règles + scoring + schéma.
# Le module vit dans le même dossier scripts/ (hors package).
sys.path.insert(0, str(Path(__file__).resolve().parent))
import prevalidation_rules as prev  # noqa: E402

# Emplacement des diffs PR mis en cache (voir étape de cache gh pr diff).
import os

SCRATCH = Path(
    os.environ.get(
        "WOURRI_PRDIFF_DIR",
        "C:/Users/USERPC~1/AppData/Local/Temp/claude/"
        "c--Users-USER-PC-Documents-propre---moi-wourri/"
        "bf786dd5-8f02-427a-93e8-55954140545f/scratchpad/prdiffs",
    )
)

# Base d'audit commune (GRAMMAIRE_DIOULA_REGLES §12bis).
#
# Formes MALIENNES ABSOLUMENT bannies : aucun sens alternatif attesté en dioula
# CI, donc toujours à corriger (cf. spec §3.1 + tests #56-#68 BANNED_TERMS).
MOTS_MALIENS_BANNIS = {
    "karo": "→ kalo (mois) — PR #84",
    "waati": "→ tuma (moment/temps) — validation native #51",
}
CORRECTIONS_CI = {
    "karo": "kalo",
    "waati": "tuma",
}

# Formes CONDITIONNELLES (spec §3.1) : PAS bannies absolument. sugu (sorte/
# espèce) et kosɛbɛ (beaucoup) sont attestés en dioula CI ; la substitution ne
# vaut que si le SENS français l'exige (marché → lɔgɔ). sɛnnɛkɛla reste une
# préférence éditoriale traitée par le module de règles. Ces formes ne sont
# JAMAIS comptées comme « mot malien banni » — elles sont rappelées dans le
# repère et gérées, au cas par cas, par la proposition pré-remplie.
FORMES_CONDITIONNELLES = {
    "sugu": "→ lɔgɔ SEULEMENT si sens « marché » (sinon sugu = sorte/espèce, valide)",
    "kosɛbɛ": "→ caman (préférence WOURI « beaucoup ») ; kosɛbɛ non fautif",
    "sɛnnɛkɛla": "→ sɛnɛbaga (cultivateur/agent)",
}

# Métadonnées par culture. term/note d'après GRAMMAIRE_DIOULA_REGLES §12.
# pr : ancienne PR d'où extraire VERSION B (None => VERSION A seule attendue,
#      mais la VERSION B est quand même appariée si présente dans PR #82).
CULTURES = {
    "coton": {
        "issue": 56,
        "prefix": "coton_",
        "label": "coton",
        "term": "kɔrɔni",
        "term_note": "coton = kɔrɔni (attesté An Ka Taa). Vérifiez son emploi dans chaque phrase.",
        "prs": [75],
    },
    "banane": {
        "issue": 57,
        "prefix": "banane_",
        "label": "banane",
        "term": "bàrànda / namasa",
        "term_note": "banane = barandaa (CI) / namasa (Mali). Vérifiez la forme retenue dans chaque phrase.",
        "prs": [76],
    },
    "tomate": {
        "issue": 58,
        "prefix": "tomate_",
        "label": "tomate",
        "term": "tamati / ntomati",
        "term_note": "tomate = tamati / ntomati (variante CI). Vérifiez son emploi dans chaque phrase.",
        "prs": [77],
    },
    "haricot": {
        "issue": 59,
        "prefix": "haricot_",
        "label": "haricot",
        "term": "soso",
        "term_note": "haricot/niébé = soso (CI). Vérifiez son emploi dans chaque phrase.",
        "prs": [78],
    },
    "gombo": {
        "issue": 60,
        "prefix": "gombo_",
        "label": "gombo",
        "term": "gan",
        "term_note": "gombo = gan (attesté An Ka Taa). Vérifiez son emploi dans chaque phrase.",
        "prs": [79],
    },
    "oignon": {
        "issue": 61,
        "prefix": "oignon_",
        "label": "oignon",
        "term": "jaba",
        "term_note": "oignon = jaba (attesté An Ka Taa). Vérifiez son emploi dans chaque phrase.",
        "prs": [80],
    },
    "patate": {
        "issue": 62,
        "prefix": "patate_",
        "label": "patate",
        "term": "woso",
        "term_note": "patate douce = woso (An Ka Taa + Bamadaba). Vérifiez son emploi dans chaque phrase.",
        "prs": [81, 82],
    },
    "sesame": {
        "issue": 63,
        "prefix": "sesame_",
        "label": "sésame",
        "term": "bɛnɛ",
        "term_note": "sésame = bɛnɛ (attesté An Ka Taa). Vérifiez son emploi dans chaque phrase.",
        "prs": [82],
    },
    "cafe": {
        "issue": 64,
        "prefix": "cafe_",
        "label": "café",
        "term": "kafe",
        "term_note": "café = kafe (loanword). Vérifiez son emploi dans chaque phrase.",
        "prs": [82],
    },
    "ananas": {
        "issue": 65,
        "prefix": "ananas_",
        "label": "ananas",
        "term": "ananas",
        "term_note": "ananas = ananas (loanword). Vérifiez son emploi dans chaque phrase.",
        "prs": [82],
    },
    "mangue": {
        "issue": 66,
        "prefix": "mangue_",
        "label": "mangue",
        "term": "mangoro",
        "term_note": "mangue = mangoro / maŋoro (attesté An Ka Taa). Vérifiez son emploi dans chaque phrase.",
        "prs": [82],
    },
    "nere": {
        "issue": 67,
        "prefix": "nere_",
        "label": "néré",
        "term": "nɛrɛ",
        "term_note": "néré = nɛrɛ (attesté). Vérifiez son emploi dans chaque phrase.",
        "prs": [82],
    },
    "agrumes": {
        "issue": 68,
        "prefix": "agrumes_",
        "label": "agrumes",
        "term": "lemuru",
        "term_note": "agrumes = lemuru / lenburu (citron/agrume). Vérifiez son emploi dans chaque phrase.",
        "prs": [82],
    },
}

# Regex d'un objet {..."id":..., ..."new_bam":...} reconstruit depuis un diff.
_OBJECT_RE = re.compile(
    r'"id"\s*:\s*"(?P<id>[^"]+)".*?"new_bam"\s*:\s*"(?P<new_bam>(?:[^"\\]|\\.)*)"',
    re.DOTALL,
)


def parse_pr_diff(diff_path: Path) -> dict[str, str]:
    """Extrait {id: new_bam} des lignes AJOUTÉES (+) d'un diff PR.

    On ne conserve que le contenu ajouté (nouvelles entrées proposées), en
    retirant le préfixe de diff. Les lignes de contexte / supprimées sont
    ignorées pour ne pas capturer d'anciennes valeurs.
    """
    added_lines: list[str] = []
    for raw in diff_path.read_text(encoding="utf-8").splitlines():
        if raw.startswith("+") and not raw.startswith("+++"):
            added_lines.append(raw[1:])
    blob = "\n".join(added_lines)
    result: dict[str, str] = {}
    for match in _OBJECT_RE.finditer(blob):
        entry_id = match.group("id")
        new_bam = json.loads(f'"{match.group("new_bam")}"')  # dé-échappe \u, \", etc.
        result[entry_id] = new_bam
    return result


def collect_version_b(prs: list[int], prefix: str) -> dict[str, tuple[str, int]]:
    """Réunit {id: (new_bam, pr_number)} pour les ids de cette culture.

    En cas d'id présent dans plusieurs PR, la PR listée en premier prime.
    """
    collected: dict[str, tuple[str, int]] = {}
    for pr in prs:
        diff_path = SCRATCH / f"pr_{pr}.diff"
        if not diff_path.is_file():
            raise FileNotFoundError(f"Diff PR manquant : {diff_path}")
        for entry_id, new_bam in parse_pr_diff(diff_path).items():
            if not entry_id.startswith(prefix):
                continue
            collected.setdefault(entry_id, (new_bam, pr))
    return collected


# Détecteurs d'audit -------------------------------------------------------

# Voyelle doublée OU triplée (ex : foroo, sanjiii, Mɛɛɛ, dugukoloo).
_DOUBLE_VOWEL_RE = re.compile(r"([aeiouɛɔ])\1", re.IGNORECASE)
# Voyelle triplée (3+) : toujours erronée (ex : sanjiii, sɛtanburuuu, Mɛɛɛ).
_TRIPLE_VOWEL_RE = re.compile(r"([aeiouɛɔ])\1{2,}", re.IGNORECASE)

# Formes à voyelle doublée ATTESTÉES en dioula CI (ne PAS signaler).
# Nombres (§11) et vocabulaire courant de GRAMMAIRE_DIOULA_REGLES.
LEGIT_DOUBLE_VOWEL = {
    "naani",    # 4
    "duuru",    # 5
    "wɔɔrɔ",    # 6
    "seegin",   # 8 (variante de seginni)
    "bɛɛ",      # tous / tout
    "joona",    # vite
    "dɔɔni",    # un peu
    "tɔɔ",      # reste
    "kɔɔri",    # coton (fibre), variante
    "kɔɔ",      # dos / derrière
    "sɔɔrɔ",    # obtenir (variante de sɔrɔ)
    "neem",     # variante attestée
}


def find_banned_words(text: str) -> list[str]:
    """Retourne les mots maliens bannis trouvés (par frontière de mot)."""
    found = []
    lowered = text.lower()
    for banned in CORRECTIONS_CI:
        if re.search(rf"(?<![a-zɛɔɲŋ]){re.escape(banned)}(?![a-zɛɔɲŋ])", lowered):
            found.append(banned)
    return found


def find_tripled_vowels(text: str) -> list[str]:
    """Retourne les mots à voyelle doublée/triplée NON standard.

    - Une voyelle triplée (3+) est toujours signalée (ex : sanjiii, Mɛɛɛ).
    - Une voyelle doublée n'est signalée que si le mot n'est PAS dans la liste
      des formes attestées (nombres naani/duuru/wɔɔrɔ, joona, bɛɛ...). Cela
      évite les faux positifs sur du vocabulaire dioula CI légitime.
    """
    suspects = []
    for token in re.findall(r"[A-Za-zɛɔɲŋ]+", text):
        if _TRIPLE_VOWEL_RE.search(token):
            suspects.append(token)
        elif _DOUBLE_VOWEL_RE.search(token) and token.lower() not in LEGIT_DOUBLE_VOWEL:
            suspects.append(token)
    # dédoublonne en conservant l'ordre
    seen = set()
    ordered = []
    for s in suspects:
        low = s.lower()
        if low not in seen:
            seen.add(low)
            ordered.append(s)
    return ordered


def build_alerte(version_a: str, version_b: str | None) -> str:
    """Construit le texte d'alerte d'audit (mots maliens + voyelles triplées)."""
    parts: list[str] = []

    banned_a = find_banned_words(version_a)
    banned_b = find_banned_words(version_b) if version_b else []
    if banned_a or banned_b:
        segs = []
        for word in sorted(set(banned_a + banned_b)):
            where = []
            if word in banned_a:
                where.append("A")
            if word in banned_b:
                where.append("B")
            segs.append(
                f"« {word} » ({'/'.join(where)}) {MOTS_MALIENS_BANNIS[word]}"
            )
        parts.append("ALERTE MOT MALIEN : " + " ; ".join(segs) + ".")

    triples_a = find_tripled_vowels(version_a)
    triples_b = find_tripled_vowels(version_b) if version_b else []
    if triples_a or triples_b:
        segs = []
        if triples_a:
            segs.append("A : " + ", ".join(f"« {t} »" for t in triples_a))
        if triples_b:
            segs.append("B : " + ", ".join(f"« {t} »" for t in triples_b))
        parts.append(
            "Voyelles doublées/triplées non standard (orthographe à corriger) — "
            + " ; ".join(segs)
            + "."
        )

    if not parts:
        parts.append(
            "Aucun mot malien banni ni voyelle triplée détecté automatiquement. "
            "Vérifier manuellement l'ordre SOV, le sens des verbes et l'orthographe "
            "des loanwords."
        )
    else:
        parts.append(
            "Vérifier aussi l'ordre SOV (verbe en fin), le sens des verbes et "
            "l'impératif pluriel « Aw ye … »."
        )
    return " ".join(parts)


def build_repere(term_note: str, version_a: str, version_b: str | None) -> str:
    """Construit le repère vérifié (terme culture + rappels formes CI bannies)."""
    reminders = [term_note]
    banned = set(find_banned_words(version_a))
    if version_b:
        banned |= set(find_banned_words(version_b))
    if banned:
        forms = "; ".join(f"{b} (Mali) → {CORRECTIONS_CI[b]} (CI)" for b in sorted(banned))
        reminders.append(f"Formes CI à imposer : {forms}.")
    reminders.append(
        "Rappels : marché = lɔgɔ (PAS sugu) ; moment = tuma (PAS waati) ; "
        "beaucoup = caman (PAS kosɛbɛ) ; mois = kalo (PAS karo) ; "
        "agent = sɛnɛbaga (PAS sɛnnɛkɛla)."
    )
    return " ".join(reminders)


# --- Proposition pré-remplie (spec §7) ------------------------------------
#
# best_version : meilleure version dioula disponible (B si présente, sinon A).
#   La spec §7 attend UNE proposition ; on part de la version la plus récente
#   proposée (B = ancienne PR) quand elle existe, à défaut de A.
#
# La proposition n'applique QUE des corrections DÉTERMINISTES :
#   1. normalisation orthographique de la table §3.2 (mots exacts) ;
#   2. substitution lexicale §3.1 UNIQUEMENT si le sens français lève
#      l'ambiguïté (sinon la forme part dans termes_a_confirmer).
# Tout le reste (faux-amis §3.3, choix de synonyme, ravageur, naturalité…)
# reste au natif : signalé, jamais résolu (spec §9).


def build_proposition(
    entry_id: str,
    french: str,
    version_a: str,
    version_b: str | None,
    crop_term: str,
) -> dict:
    """Produit la PROPOSITION pré-remplie au format §7 pour une entrée.

    Retourne un dict conforme à `prev.PROPOSITION_SCHEMA`. Ne modifie pas les
    données sources. `necessite_validation_native` est TOUJOURS True.
    """
    best_version = version_b if version_b else version_a
    source_label = "VERSION B" if version_b else "VERSION A"

    regles_appliquees: list[str] = []
    termes_a_confirmer: list[str] = []

    # 1) Normalisation orthographique déterministe (table §3.2 uniquement).
    ortho = prev.apply_orthographic_map(best_version)
    regles_appliquees.extend(ortho.applied_rules)

    # 2) Substitution lexicale conditionnelle (§3.1), sur le texte normalisé.
    lex = prev.apply_lexical_substitutions(ortho.text, french_reference=french)
    regles_appliquees.extend(lex.applied_rules)
    termes_a_confirmer.extend(lex.to_confirm)

    proposition_text = lex.text

    # 3) Faux-amis (§3.3) : SIGNALER, jamais remplacer.
    semantic_alerts = prev.detect_semantic_alerts(proposition_text)
    for alert in semantic_alerts:
        verb = "rejeter" if alert["action"] == "reject" else "à confirmer"
        termes_a_confirmer.append(
            f"« {alert['form']} » : {verb} — sens attesté = "
            f"{alert['attested_sense']} (usage visé : {alert['wrong_sense']})"
        )

    # 4) Choix de terme de culture (§9 : choix de synonyme non automatisable).
    termes_a_confirmer.append(
        f"Terme de culture « {crop_term} » : confirmer l'emploi dans la phrase."
    )

    # --- Scoring (§6) : score de PRÉPARATION, pas une probabilité. ---------
    # Sous-scores heuristiques et PRUDENTS (score bas = plus de vérification) :
    #   O (orthographe) : 1.0 si aucune correction orthographique restait à
    #     faire n'est détectée après normalisation ; sinon 0.75.
    #   S, G, Y : neutres-hauts (0.75) — le texte vient de propositions déjà
    #     éditées, mais rien n'est vérifié nativement.
    #   E (preuves lexicales) : 0.5 par défaut (2 sources CI non garanties).
    #   A (agronomie) : 1.0 si aucune reco agronomique chiffrée détectée
    #     (spec §6), sinon on plafonne via caps (non vérifié).
    has_agronomy = _mentions_agronomy(french) or _mentions_agronomy(best_version)
    caps = prev.ConfidenceCaps(
        unconfirmed_technical_term=bool(termes_a_confirmer),
        unverified_agronomy=has_agronomy,
        pesticide_without_dosage=_pesticide_without_dosage(french, best_version),
        possible_contresens=any(
            a["action"] == "reject" for a in semantic_alerts
        ),
    )
    confiance = prev.calculate_confidence(
        S=0.75,
        G=0.75,
        Y=0.75,
        O=1.0 if not ortho.applied_rules else 0.75,
        A=1.0 if not has_agronomy else 0.75,
        E=0.5,
        caps=caps,
    )

    # --- Note concrète pour le natif (§7) ---------------------------------
    note = _build_native_note(
        source_label, semantic_alerts, lex.to_confirm, crop_term
    )

    proposition = {
        "entry_id": entry_id,
        "french_reference": french,
        "proposition_dioula_ci": proposition_text,
        "regles_appliquees": _dedupe_ordered(regles_appliquees),
        "termes_a_confirmer": _dedupe_ordered(termes_a_confirmer),
        "confiance": confiance,
        "necessite_validation_native": True,
        "note_pour_le_natif": note,
    }
    # Garde-fou : chaque proposition produite est validée contre le schéma §7.3.
    prev.validate_proposition(proposition)
    return proposition


# Détecteurs agronomiques prudents (déclenchent des plafonds §6, pas des rejets).
_AGRONOMY_RE = re.compile(
    r"\b(npk|engrais|nɔgɔ|dose|cm|centim|kg|litre|traitement|pesticide|"
    r"herbicide|fongicide|insecticide|urée|uree)\b",
    re.IGNORECASE,
)
_PESTICIDE_RE = re.compile(
    r"\b(pesticide|herbicide|fongicide|insecticide|traitement)\b", re.IGNORECASE
)
_DOSAGE_RE = re.compile(r"\d")  # présence d'un chiffre = dosage plausible.


def _dedupe_ordered(values: list[str]) -> list[str]:
    """Déduplique une liste en conservant l'ordre d'apparition."""
    seen: set[str] = set()
    ordered: list[str] = []
    for v in values:
        if v not in seen:
            seen.add(v)
            ordered.append(v)
    return ordered


def _mentions_agronomy(text: str) -> bool:
    return bool(_AGRONOMY_RE.search(text))


def _pesticide_without_dosage(french: str, dioula: str) -> bool:
    """True si un produit phyto est mentionné sans aucun chiffre de dosage."""
    joined = f"{french} {dioula}"
    return bool(_PESTICIDE_RE.search(joined)) and not _DOSAGE_RE.search(joined)


def _build_native_note(
    source_label: str,
    semantic_alerts: list[dict[str, str]],
    lexical_to_confirm: list[str],
    crop_term: str,
) -> str:
    """Rédige une décision CONCRÈTE demandée au natif (spec §7)."""
    decisions: list[str] = []
    for alert in semantic_alerts:
        if alert["action"] == "reject":
            decisions.append(
                f"Remplacer « {alert['form']} » (= {alert['attested_sense']}, "
                f"faux-ami) par le bon terme pour « {alert['wrong_sense']} »"
            )
        else:
            decisions.append(
                f"Confirmer le sens de « {alert['form']} » "
                f"({alert['attested_sense']})"
            )
    if lexical_to_confirm:
        decisions.append(
            "Trancher le sens des formes conditionnelles signalées "
            "(sugu/kosɛbɛ) selon le contexte"
        )
    decisions.append(
        f"Confirmer que « {crop_term} » est la bonne forme dans cette phrase"
    )
    return (
        f"Base : {source_label} après normalisation orthographique déterministe. "
        f"Décisions à trancher : {' ; '.join(decisions)}. "
        "Vérifier l'ordre SOV (verbe en fin), l'impératif pluriel « Aw ye … » "
        "et la naturalité orale avant intégration."
    )


def main() -> None:
    draft = json.loads(DRAFT_PATH.read_text(encoding="utf-8"))
    draft_entries = {e["id"]: e for e in draft["entries"]}

    for culture, meta in CULTURES.items():
        prefix = meta["prefix"]
        entries = [
            draft_entries[eid]
            for eid in draft_entries
            if eid.startswith(prefix)
        ]
        # ordre stable et lisible : par id
        entries.sort(key=lambda e: e["id"])
        if not entries:
            raise ValueError(f"Aucune entrée draft pour préfixe {prefix}.")

        version_b_map = collect_version_b(meta["prs"], prefix)

        items = []
        alert_words = set()
        for entry in entries:
            eid = entry["id"]
            version_a = entry["reponse_bambara"]
            french = entry["reponse_fr"]
            intent = entry.get("intent", "")
            vb = version_b_map.get(eid)
            version_b = vb[0] if vb else None
            version_b_pr = f"PR #{vb[1]}" if vb else None

            alerte = build_alerte(version_a, version_b)
            repere = build_repere(meta["term_note"], version_a, version_b)

            alert_words |= set(find_banned_words(version_a))
            if version_b:
                alert_words |= set(find_banned_words(version_b))

            item = {
                "id": eid,
                "culture": entry.get("cultures", [None])[0] if entry.get("cultures") else None,
                "intent": intent,
                "french": french,
                "version_a": version_a,
                "alerte_audit": alerte,
                "repere_verifie": repere,
                "proposition": build_proposition(
                    eid, french, version_a, version_b, meta["term"]
                ),
            }
            if version_b:
                item["version_b"] = version_b
                item["version_b_pr"] = version_b_pr
            items.append(item)

        n_with_b = sum(1 for it in items if it.get("version_b"))
        out = {
            "schema_version": "1.0",
            "issue": meta["issue"],
            "date": "2026-08-04",
            "status": "pending_native_validation",
            "culture": f"CULTURE_{culture.upper()}",
            "crop_label": meta["label"],
            "crop_term": meta["term"],
            "crop_term_note": meta["term_note"],
            "field_prefix_base": culture.upper(),
            "footer_label": (
                f"Wourri - Issue #{meta['issue']} - Brouillon, ne pas intégrer "
                "avant validation native"
            ),
            "item_count": len(items),
            "version_b_source_prs": meta["prs"],
            "warning": (
                f"Ce formulaire présente {len(items)} entrées {meta['label']}. "
                "La VERSION A (brouillon consolidé du draft v3)"
                + (
                    " et la VERSION B (ancienne PR proposée) sont des propositions"
                    if n_with_b
                    else " est une proposition"
                )
                + " non validées, absentes du corpus IVR de production. Le "
                "validateur natif dioula CI tranche entrée par entrée."
            ),
            "audit_basis": {
                "mots_maliens_bannis": MOTS_MALIENS_BANNIS,
                "reference": "data/GRAMMAIRE_DIOULA_REGLES.md §12bis",
            },
            "items": items,
        }

        out_path = DATA_DIR / f"issue_{meta['issue']}_{culture}_validation_draft.json"
        out_path.write_text(
            json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(
            f"{culture:8s} #{meta['issue']}  entrées={len(items):2d}  "
            f"versionB={n_with_b:2d}  bannis={sorted(alert_words)}"
        )


if __name__ == "__main__":
    main()
