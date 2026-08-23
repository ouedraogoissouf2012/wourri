"""Route admin de la couverture (ADR-0034 P1)."""
from fastapi import APIRouter, Depends

from app.routers.session import require_role
from app.services.coverage import coverage_matrix
from app.services.pg_catalog import PgCorpusCatalog

router = APIRouter(prefix="/coverage")


@router.get("")
def get_coverage(_: dict = Depends(require_role("admin"))) -> dict:
    rows = coverage_matrix(PgCorpusCatalog())
    return {
        "languages": [
            {
                "code": r.code,
                "name": r.name,
                "total": r.total,
                "covered": r.covered,
                "missing": r.missing,
                "up_to_date": r.up_to_date,
            }
            for r in rows
        ]
    }
