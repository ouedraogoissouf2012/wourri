"""
WOURI - ModelRegistry thread-safe.

Gere le chargement et le cache de tous les modeles ML en singleton.
Remplace les variables globales eparpillees dans chaque service.

Usage :
    from app.services.model_registry import registry

    model = registry.get("nemo_soloni", loader=_load_nemo_model)
    registry.unload("nemo_soloni")  # libere la memoire
"""
import logging
import threading
from typing import Any, Callable

logger = logging.getLogger(__name__)


class ModelRegistry:
    """Cache thread-safe pour les modeles ML.

    Garanties :
    - Un seul thread charge un modele a la fois (Lock par cle)
    - Pas de double-chargement si deux requetes arrivent simultanement
    - Possibilite de decharger un modele pour liberer la RAM
    """

    def __init__(self) -> None:
        self._models: dict[str, Any] = {}
        self._lock = threading.Lock()
        self._key_locks: dict[str, threading.Lock] = {}

    def _get_key_lock(self, key: str) -> threading.Lock:
        """Retourne un Lock dedie a une cle (cree si absent)."""
        with self._lock:
            if key not in self._key_locks:
                self._key_locks[key] = threading.Lock()
            return self._key_locks[key]

    def get(self, key: str, loader: Callable[[], Any]) -> Any:
        """Retourne le modele cache, ou le charge via loader() si absent.

        Thread-safe : si deux threads appellent get() simultanement pour
        la meme cle, un seul execute loader(), l'autre attend.
        """
        # Fast path : deja charge
        if key in self._models:
            return self._models[key]

        # Slow path : charger avec verrou par cle
        key_lock = self._get_key_lock(key)
        with key_lock:
            # Double-check apres acquisition du verrou
            if key in self._models:
                return self._models[key]

            logger.info("[Registry] Chargement du modele '%s'...", key)
            try:
                model = loader()
                self._models[key] = model
                logger.info("[Registry] Modele '%s' charge avec succes", key)
                return model
            except Exception:
                logger.exception("[Registry] Echec chargement du modele '%s'", key)
                raise

    def is_loaded(self, key: str) -> bool:
        """Verifie si un modele est en cache."""
        return key in self._models

    def unload(self, key: str) -> bool:
        """Decharge un modele du cache pour liberer la memoire.

        Retourne True si le modele a ete decharge, False s'il n'existait pas.
        """
        key_lock = self._get_key_lock(key)
        with key_lock:
            if key in self._models:
                del self._models[key]
                logger.info("[Registry] Modele '%s' decharge", key)
                return True
            return False

    def list_loaded(self) -> list[str]:
        """Liste les cles des modeles actuellement en cache."""
        return list(self._models.keys())

    def unload_all(self) -> None:
        """Decharge tous les modeles."""
        with self._lock:
            keys = list(self._models.keys())
            self._models.clear()
            logger.info("[Registry] Tous les modeles decharges: %s", keys)


# Instance globale unique
registry = ModelRegistry()
