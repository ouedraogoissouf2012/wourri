"""Pousse une tâche Bronze vers Convex /lqe/bronze-task (optionnel)."""
from __future__ import annotations

import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)


def push_bronze_task(
    *,
    intent: str | None,
    source: str | None,
    cultures: list | None,
    excerpt: str | None,
) -> dict[str, Any]:
    base = (os.getenv("CONVEX_BASE_URL") or os.getenv("CONVEX_SITE_URL") or "").rstrip("/")
    key = (
        os.getenv("CONVEX_CALLBACK_KEY")
        or os.getenv("X_CALLBACK_KEY")
        or ""
    ).strip()
    org = (os.getenv("WOURI_ORGANIZATION_ID") or "").strip()
    if not base or not key or not org:
        return {"ok": False, "skipped": "unconfigured"}
    url = f"{base}/lqe/bronze-task"
    body = {
        "organizationId": org,
        "language": "dyu",
        "intent": intent or "",
        "source": source or "",
        "excerpt": (excerpt or "")[:200],
        "cultures": cultures or [],
    }
    try:
        with httpx.Client(timeout=3.0) as client:
            r = client.post(
                url,
                json=body,
                headers={"X-Callback-Key": key, "Content-Type": "application/json"},
            )
        if r.status_code >= 400:
            logger.warning("[LQE] push Convex %s", r.status_code)
            return {"ok": False, "status": r.status_code}
        return {"ok": True}
    except Exception as exc:
        logger.warning("[LQE] push Convex échoué (%s)", exc)
        return {"ok": False, "error": str(exc)}
