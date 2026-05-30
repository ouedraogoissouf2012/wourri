"""
Sous-package `app.services.chat` — modules extraits du god file `chat_service.py`
dans le cadre du refactor P2-09 (Sprint L #204).

PR 1 : MeteoInjector (cette PR)
PR 2 : CityDetector (futur)
PR 3 : NLUPreprocessor (futur)
PR 4 : IVRSearcher (futur)
PR 5 : DeepSeekRouter + ChatService final orchestrateur (futur)

Chaque module ici est :
  - PUR : pas de dependances cycliques avec ChatService
  - TESTABLE : fonctions/classes injectables
  - COHERENT : 1 responsabilite claire (SRP)
"""
