from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.data.language_registry import is_known
from app.routers.session import current_user, require_role
from app.services import assignments
from app.services.nlu_catalog import NluConceptCatalog
from app.services.pg_catalog import PgCorpusCatalog

# Deux catalogues alimentent LE MEME mecanisme d'assignation (ADR-0047) :
# le corpus (phrases a traduire) et les concepts NLU (mots a donner). En ajouter
# un troisieme = une entree ici, aucun ecran ni `if`-langue a toucher.
_CATALOGUES = {
    "corpus": (PgCorpusCatalog, "contenu"),
    "nlu": (NluConceptCatalog, "mot_cle"),
}


def _catalogue(nom: str):
    """(instance, kind attendu) — 400 si le nom est inconnu."""
    choix = _CATALOGUES.get((nom or "corpus").strip().lower())
    if choix is None:
        raise HTTPException(status_code=400, detail="unknown_catalogue")
    cls, kind = choix
    return cls(), kind


router = APIRouter(prefix="/assignments")


class AssignBody(BaseModel):
    target_language: str = Field(min_length=1)
    concept_ids: list[str] = Field(min_length=1)
    # « corpus » (phrases a traduire) ou « nlu » (mots d'un concept). Defaut : corpus,
    # pour que les appels existants gardent exactement leur sens (ADR-0047).
    catalogue: str = "corpus"


@router.get("")
def get_my_assignments(user: dict = Depends(current_user)):
    """Assignations OUVERTES de la langue de session (isolation par langue)."""
    lang = user["lang"]
    rows = assignments.list_open(language=lang)
    return {"language": lang, "assignments": rows, "count": len(rows)}


@router.post("")
def post_assign(body: AssignBody, user: dict = Depends(require_role("admin"))):
    lang = body.target_language.strip().lower()
    if not is_known(lang):
        raise HTTPException(status_code=400, detail="unknown_language")
    catalog, kind = _catalogue(body.catalogue)
    return assignments.assign_batch(
        body.concept_ids, target_language=lang, assigned_by=user["u"],
        catalog=catalog, kind=kind,
    )


@router.get("/missing")
def get_missing(language: str, catalogue: str = "corpus",
                _: dict = Depends(require_role("admin"))):
    """Concepts non encore assignes, pour le catalogue demande (ADR-0047).

    `catalogue=nlu` liste les concepts NLU sans mot valide : c'est ce qui permet
    d'ouvrir une langue nouvelle, ou TOUS les concepts sont vides."""
    lang = language.strip().lower()
    if not is_known(lang):
        raise HTTPException(status_code=400, detail="unknown_language")
    catalog, kind = _catalogue(catalogue)
    rows = assignments.missing_to_assign(catalog, language=lang)
    return {"language": lang, "catalogue": catalogue, "kind": kind,
            "concepts": rows, "count": len(rows)}
