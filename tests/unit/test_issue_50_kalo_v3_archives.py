"""Contrats de la correction kalo de l'issue #50."""

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[2]
PARTIAL_DRAFT_PATH = (
    ROOT / "dictionnaires" / "archive" / "corpus_ivr_v3_draft.json"
)
FULL_DRAFT_PATH = (
    ROOT / "dictionnaires" / "archive" / "corpus_ivr_v3_full_draft.json"
)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    ("path", "response_field", "expected_entries", "min_kalo_count"),
    [
        (PARTIAL_DRAFT_PATH, "new_bam", 38, 16),
        (FULL_DRAFT_PATH, "reponse_bambara", 162, 59),
    ],
)
def test_v3_archives_use_validated_kalo_spelling(
    path: Path,
    response_field: str,
    expected_entries: int,
    min_kalo_count: int,
):
    """Contrat #50 : le draft v3 n'emploie JAMAIS la forme malienne `karo`,
    et emploie la forme dioula CI validée `kalo`.

    Le compte de `kalo` est vérifié comme un *plancher* (>=) et non un snapshot
    exact : chaque validation native (#51-#68) ajoute légitimement des `kalo`
    (mois `Zanviye kalo`, durées `kalo saba`...). Figer le compte exact rendrait
    ce test fragile et le ferait échouer à chaque promotion native correcte.
    Le contrat de qualité (`karo` interdit) reste, lui, strict.
    """
    draft = load_json(path)
    responses = " ".join(entry[response_field] for entry in draft["entries"])

    assert len(draft["entries"]) == expected_entries
    assert not re.search(r"\bkaro\b", responses, flags=re.IGNORECASE)
    assert (
        len(re.findall(r"\bkalo\b", responses, flags=re.IGNORECASE))
        >= min_kalo_count
    )


def test_partial_draft_documents_kalo_as_the_validated_spelling():
    corrections = load_json(PARTIAL_DRAFT_PATH)["corrections_appliquees"]

    assert "kalo→karo" not in corrections
    assert corrections["kalo_conserve"] == (
        "kalo est correct en dioula CI — correction v3 validée"
    )
