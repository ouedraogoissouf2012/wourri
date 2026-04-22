"""
Anonymisation des PII utilisateurs (numéros WhatsApp, user_ids).

Utilise SHA-256 avec salt pour la pseudonymisation GDPR (Art. 4(5)) :
- déterministe (même user_id → même hash → traçabilité support client)
- irréversible sans le salt (pseudonymisation reconnue par le GDPR)
- préfixé par 'usr_' pour lisibilité dans les logs

Usage :
    from app.core.pii_utils import anonymize_user_id

    logger.info(f"[Chat] user={anonymize_user_id(user_id)}")
    # → [Chat] user=usr_a3f8e2c9d4b2a7e1

Le salt est lu depuis la variable d'environnement PII_SALT. S'il est
absent, un warn est émis au premier appel. En production, définir un
salt aléatoire stable dans .env.
"""
import hashlib
import logging
import os

logger = logging.getLogger(__name__)

_PII_SALT: str = os.getenv("PII_SALT", "")
_SALT_WARNED: bool = False


def anonymize_user_id(user_id: str | None) -> str:
    """Retourne un identifiant anonymisé stable pour un user_id.

    Même input → même output (déterministe). Irréversible sans le salt.

    Args:
        user_id: numéro WhatsApp ou identifiant utilisateur brut.
                 Si None ou vide : retourne 'usr_anon'.

    Returns:
        Chaîne de la forme 'usr_XXXXXXXXXXXXXXXX' (prefix + 16 chars hex).
    """
    global _SALT_WARNED
    if not user_id:
        return "usr_anon"

    if not _PII_SALT and not _SALT_WARNED:
        logger.warning(
            "[PII] PII_SALT non configuré dans .env — anonymisation sans salt "
            "(mode dev). En production, définir PII_SALT avec une valeur aléatoire "
            "stable (ex: `python -c \"import secrets; print(secrets.token_hex(32))\"`)."
        )
        _SALT_WARNED = True

    to_hash = (_PII_SALT + user_id).encode("utf-8")
    digest = hashlib.sha256(to_hash).hexdigest()
    return f"usr_{digest[:16]}"
