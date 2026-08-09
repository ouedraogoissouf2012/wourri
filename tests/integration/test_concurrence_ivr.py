"""Tests de concurrence — Sprint G.2 (issue #193).

Vérifie que les appels IVR concurrents ne bloquent pas le event loop FastAPI.

Avant Sprint G.2 : `chercher_reponse_ivr()` (qui invoque
`corpus_service._embed_query()` SentenceTransformer ~50-200ms) était appelé
**sans `asyncio.to_thread`** depuis `chat_service._try_ivr_exact` et
`_search_ivr_by_concept`. Conséquence : N appels concurrents traités
séquentiellement (le event loop est bloqué pendant l'inférence ML).

Après Sprint G.2 : wrapping `to_thread` autour des appels → 3 appels parallèles
finissent en ~1× le temps d'un seul (au lieu de 3×).

Tests :
- Mock de `chercher_reponse_ivr` avec un délai artificiel → vérifier que 3
  appels concurrents se chevauchent en temps réel.
- Test sans mock (intégration vraie BDD) skip si Postgres absent.
"""
from __future__ import annotations

import asyncio
import time
from unittest.mock import patch

import pytest

from app.models.schemas import Language
from app.services.chat_service import ChatService, NLUResult


# ─────────────────────────────────────────────────────────────────────────
# Test 1 : preuve que to_thread débloque le event loop
# ─────────────────────────────────────────────────────────────────────────


class TestConcurrenceIVR:
    """3 appels IVR concurrents doivent finir en parallèle, pas séquentiel."""

    async def test_three_concurrent_ivr_searches_dont_block_event_loop(self):
        """Mock `chercher_reponse_ivr` avec sleep 100ms. 3 appels parallèles
        doivent finir en ~110ms (parallèle), PAS ~300ms (séquentiel).

        C'est le test critique du fix Sprint G.2 : sans `to_thread`, le sleep
        sync de 100ms bloque le event loop → 3 appels = 300ms minimum.
        Avec `to_thread`, les 3 sleeps tournent en threads parallèles → ~100ms.
        """
        service = ChatService()
        sleep_ms = 100

        def fake_chercher(intent, cultures, conditions):
            time.sleep(sleep_ms / 1000)  # bloque ce thread, pas le event loop
            return {
                "id": f"fake_{intent}",
                "reponse_bambara": "test ba",
                "reponse_fr": "test fr",
                "score_validation": 0.8,
                "intent": intent,
                "cultures": cultures[0] if cultures else "*",
            }

        # Patch la fonction réelle (backend pgvector unique, #203)
        with patch(
            "app.services.corpus_service.chercher_reponse_ivr",
            side_effect=fake_chercher,
        ):
            nlu = NLUResult(
                message_for_deepseek="test",
                intent="CONSEIL_PRODUCTION",
                concepts={"CULTURE_RIZ": 1.0},
            )

            t0 = time.perf_counter()
            results = await asyncio.gather(
                service._try_ivr_exact(nlu, "Abidjan", None, False, Language.BOTH),
                service._try_ivr_exact(nlu, "Abidjan", None, False, Language.BOTH),
                service._try_ivr_exact(nlu, "Abidjan", None, False, Language.BOTH),
            )
            elapsed_ms = (time.perf_counter() - t0) * 1000

            # Compromis seuil 250ms :
            # - Cas parallèle réel attendu : ~110-150ms (sleep + overhead thread)
            # - Cas séquentiel régression : ≥ 300ms (3 × 100ms)
            # - Marge anti-flake CI Windows : 250-150 = 100ms (scheduling thread
            #   ~15ms granularité, overhead asyncio, GIL acquisition)
            # Si le test devient flaky en CI : élargir à 280ms (toujours < 300 séquentiel)
            assert all(r is not None for r in results)
            assert elapsed_ms < 250, (
                f"3 appels parallèles ont pris {elapsed_ms:.0f}ms (attendu < 250ms). "
                f"Si ≥ 300ms : le event loop est bloqué (régression Sprint G.2)."
            )

    async def test_search_ivr_by_concept_is_async(self):
        """`_search_ivr_by_concept` doit être awaitable (Sprint G.2)."""
        service = ChatService()
        # Appel avec concepts vide → retourne None sans toucher la BDD
        coro = service._search_ivr_by_concept({})
        assert asyncio.iscoroutine(coro), (
            "_search_ivr_by_concept doit être async (Sprint G.2 pour ne pas bloquer "
            "le event loop sur l'embedding SentenceTransformer)"
        )
        result = await coro
        assert result is None
