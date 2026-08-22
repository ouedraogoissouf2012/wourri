"""Point d'entrée LQE — routers minces, pas de métier ici."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routers import accounts, corpus, health, ingest, languages, session, tasks

settings = get_settings()
app = FastAPI(
    title="WOURI LQE",
    version="0.1.0",
    description=(
        "Atelier linguistique (ADR-0033). "
        "Login via POST /auth/login puis Authorize n'est pas requis : "
        "Swagger envoie le cookie de session. "
        "Une session = une langue (dyu, bci, …)."
    ),
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    openapi_tags=[
        {"name": "Santé", "description": "Liveness"},
        {"name": "Auth", "description": "Session cookie, langue portée par le compte"},
        {"name": "Langues", "description": "Codes autorisés (env LQE_LANGUAGE_CODES)"},
        {"name": "Ingest", "description": "Upload JSON/CSV/XLSX → Bronze"},
        {"name": "Tâches", "description": "File Bronze / acceptées"},
        {"name": "Corpus", "description": "Promotion atelier (pas pgvector moteur)"},
    ],
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(health.router, tags=["Santé"])
app.include_router(session.router, tags=["Auth"])
app.include_router(languages.router, tags=["Langues"])
app.include_router(ingest.router, tags=["Ingest"])
app.include_router(tasks.router, tags=["Tâches"])
app.include_router(corpus.router, tags=["Corpus"])
app.include_router(accounts.router, tags=["Comptes"])

