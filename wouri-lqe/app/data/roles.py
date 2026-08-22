"""Rôles — capacités, aucune langue nommée ici."""
ALL_ROLES = ("ingest", "review", "promote", "admin")
SPEAKER_ROLES = ("ingest", "review", "promote")


def normalize_roles(raw) -> list[str]:
    if not raw:
        return []
    out = []
    for r in raw:
        k = str(r).strip().lower()
        if k in ALL_ROLES and k not in out:
            out.append(k)
    return out


def has_role(roles, needed: str) -> bool:
    rs = list(roles or [])
    if "admin" in rs:
        return True
    return needed in rs
