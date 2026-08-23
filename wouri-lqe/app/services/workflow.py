"""Machine a etats de l'atelier sur Postgres (ADR-0034 P4) — une table `productions`.

bronze -> admin_accepted -> production. La promotion ne cree jamais de ligne : elle
flippe le statut. `production` n'est atteignable QUE par promote (/corpus/promote,
role `promote`), jamais par decide (/tasks/decision, role `review`).
"""
from __future__ import annotations

from app.services import productions_repo as repo

# decide (role review) ne peut PAS promouvoir : 'production' n'est pas une decision.
DECISIONS = {"admin_accepted", "admin_rejected"}
# seul un item accepte par l'admin est promouvable.
ALLOWED_FROM = {"admin_accepted"}
# une decision (review) ne s'applique JAMAIS a une production deja publiee (terminale
# cote review) : sinon le role review pourrait defaire une promotion (role promote).
DECIDABLE_FROM = {"bronze", "admin_accepted", "admin_rejected"}


def list_tasks(*, language: str, status: str | None = None) -> list[dict]:
    return repo.list_by(language=language, status=status)


def decide(item_id: str, status: str, *, language: str) -> dict:
    if status not in DECISIONS:
        return {"ok": False, "reason": "bad_decision"}
    row = repo.get(item_id=item_id, language=language)
    if row is None:
        return {"ok": False, "reason": "not_found"}
    if not repo.set_status(
        item_id=item_id, language=language, status=status, allowed_from=DECIDABLE_FROM
    ):
        return {"ok": False, "reason": "locked", "status": row["status"]}
    return {"ok": True, "id": str(item_id), "status": status}


def promote(item_id: str, *, language: str, actor: str) -> dict:
    return repo.promote(
        item_id=item_id, language=language, actor=actor, allowed_from=ALLOWED_FROM
    )


def list_corpus(*, language: str) -> list[dict]:
    return repo.list_by(language=language, status="production")
