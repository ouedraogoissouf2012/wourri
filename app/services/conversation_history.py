"""
WOURI - Service d'historique de conversation
Garde le contexte des conversations par utilisateur
"""
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Optional

# Historique en mémoire: {user_id: [{"role": "user/assistant", "content": "...", "timestamp": ...}]}
_conversation_history: dict[str, list[dict]] = defaultdict(list)

# Configuration
MAX_HISTORY_LENGTH = 10  # Nombre maximum de messages par utilisateur
HISTORY_EXPIRY_HOURS = 24  # Expiration de l'historique en heures


def add_message(user_id: str, role: str, content: str) -> None:
    """
    Ajoute un message à l'historique d'un utilisateur

    Args:
        user_id: Identifiant unique de l'utilisateur (ex: numéro WhatsApp)
        role: "user" ou "assistant"
        content: Contenu du message
    """
    if not user_id:
        return

    # Nettoyer les vieux messages d'abord
    _cleanup_old_messages(user_id)

    _conversation_history[user_id].append({
        "role": role,
        "content": content,
        "timestamp": datetime.now()
    })

    # Garder seulement les derniers messages
    if len(_conversation_history[user_id]) > MAX_HISTORY_LENGTH:
        _conversation_history[user_id] = _conversation_history[user_id][-MAX_HISTORY_LENGTH:]


def get_history(user_id: str, max_messages: int = 6) -> list[dict]:
    """
    Récupère l'historique de conversation d'un utilisateur

    Args:
        user_id: Identifiant unique de l'utilisateur
        max_messages: Nombre maximum de messages à retourner

    Returns:
        Liste de messages [{"role": "user/assistant", "content": "..."}]
    """
    if not user_id or user_id not in _conversation_history:
        return []

    # Nettoyer les vieux messages
    _cleanup_old_messages(user_id)

    # Retourner les derniers messages (sans timestamp pour l'API)
    history = _conversation_history[user_id][-max_messages:]
    return [{"role": msg["role"], "content": msg["content"]} for msg in history]


def get_history_for_deepseek(user_id: str, max_messages: int = 6) -> list[dict]:
    """
    Récupère l'historique formaté pour l'API DeepSeek

    Args:
        user_id: Identifiant unique de l'utilisateur
        max_messages: Nombre maximum de messages à retourner

    Returns:
        Liste de messages pour DeepSeek [{"role": "user/assistant", "content": "..."}]
    """
    return get_history(user_id, max_messages)


def clear_history(user_id: str) -> None:
    """
    Efface l'historique d'un utilisateur

    Args:
        user_id: Identifiant unique de l'utilisateur
    """
    if user_id in _conversation_history:
        del _conversation_history[user_id]


def _cleanup_old_messages(user_id: str) -> None:
    """
    Supprime les messages expirés d'un utilisateur
    """
    if user_id not in _conversation_history:
        return

    expiry_time = datetime.now() - timedelta(hours=HISTORY_EXPIRY_HOURS)
    _conversation_history[user_id] = [
        msg for msg in _conversation_history[user_id]
        if msg.get("timestamp", datetime.now()) > expiry_time
    ]


def get_conversation_summary(user_id: str) -> Optional[str]:
    """
    Génère un résumé du contexte de conversation pour le prompt système

    Args:
        user_id: Identifiant unique de l'utilisateur

    Returns:
        Résumé textuel ou None si pas d'historique
    """
    history = get_history(user_id, max_messages=4)

    if not history:
        return None

    summary_parts = []
    for msg in history:
        role_label = "Agriculteur" if msg["role"] == "user" else "WOURI"
        summary_parts.append(f"{role_label}: {msg['content'][:100]}...")

    return "Historique récent:\n" + "\n".join(summary_parts)


def get_stats() -> dict:
    """
    Retourne des statistiques sur l'historique
    """
    total_users = len(_conversation_history)
    total_messages = sum(len(msgs) for msgs in _conversation_history.values())

    return {
        "active_users": total_users,
        "total_messages": total_messages,
        "max_history_per_user": MAX_HISTORY_LENGTH,
        "expiry_hours": HISTORY_EXPIRY_HOURS
    }
