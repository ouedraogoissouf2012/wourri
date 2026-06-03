"""
WOURI - Endpoint /api/health/memory (issue #42 T5).

Retourne la consommation mémoire (RSS) du process en cours et la liste
des modèles ML chargés via `ModelRegistry`. Utile pour :

- Profiler la RAM par modèle (T1)
- Vérifier l'effet des flags ENABLE_WHISPER / ENABLE_MMS_DYU / preload_*
- Diagnostic Windows mkl_malloc crashes
- Monitoring observabilité (à scraper ultérieurement par Prometheus)

Exemple de réponse :
    GET /api/health/memory
    {
        "process": { "rss_mb": 4611.9, "vms_mb": 7436.4 },
        "models_loaded": ["nemo_soloni", "tts_bambara", "tts_dioula"],
        "models_count": 3,
        "feature_flags": {
            "enable_whisper": false,
            "enable_mms_dyu": true,
            "enable_mms_bam": true,
            "preload_tts_dioula": true,
            "preload_tts_bambara": true
        }
    }

Note : RSS par modèle individuel nécessite un fork à la création du modèle
(non implémenté ici — task T1 séparée). Cet endpoint donne la **vue globale**
process + liste modèles chargés.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter

from app.config import get_settings
from app.services.model_registry import registry

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/health", tags=["Health"])


def _get_process_memory_mb() -> dict[str, float | None]:
    """Retourne RSS + VMS en MB du process courant.

    Utilise psutil si disponible (recommandé), sinon resource (POSIX uniquement,
    Windows retourne None pour les champs RSS/VMS).
    """
    try:
        import psutil
        p = psutil.Process()
        mem = p.memory_info()
        return {
            "rss_mb": round(mem.rss / (1024 * 1024), 1),
            "vms_mb": round(mem.vms / (1024 * 1024), 1),
        }
    except ImportError:
        logger.warning("[HEALTH-MEM] psutil non installe — mesures memoire indisponibles")
        return {"rss_mb": None, "vms_mb": None}
    except Exception as e:
        logger.error("[HEALTH-MEM] Erreur lecture memoire: %s", e)
        return {"rss_mb": None, "vms_mb": None}


@router.get("/memory")
async def get_memory_status() -> dict:
    """Retourne RSS process + modèles chargés + état des feature flags (#42).

    Lecture lazy de toutes les valeurs pour refléter l'état courant (pas
    un snapshot startup).
    """
    settings = get_settings()
    return {
        "process": _get_process_memory_mb(),
        "models_loaded": registry.list_loaded(),
        "models_count": len(registry.list_loaded()),
        "feature_flags": {
            "enable_whisper": settings.enable_whisper,
            "enable_mms_dyu": settings.enable_mms_dyu,
            "enable_mms_bam": settings.enable_mms_bam,
            "preload_tts_dioula": settings.preload_tts_dioula,
            "preload_tts_bambara": settings.preload_tts_bambara,
        },
    }
