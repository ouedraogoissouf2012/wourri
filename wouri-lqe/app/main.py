"""Point d'entrée LQE — routers minces, pas de métier ici."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routers import corpus, health, ingest, languages, session, tasks

settings = get_settings()
app = FastAPI(title="WOURI LQE", docs_url="/docs", openapi_url="/openapi.json")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(health.router)
app.include_router(session.router)
app.include_router(languages.router)
app.include_router(tasks.router)
app.include_router(ingest.router)
app.include_router(corpus.router)
