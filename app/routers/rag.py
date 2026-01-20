"""
WOURI - Routes RAG (Base de connaissances agricoles)
"""
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional, List
from app.services import rag_knowledge

router = APIRouter(prefix="/api/rag", tags=["RAG - Connaissances"])


class SearchQuery(BaseModel):
    query: str
    top_k: int = 3


class DocumentInput(BaseModel):
    text: str
    metadata: Optional[dict] = None


@router.post("/search")
async def search_knowledge(query: SearchQuery):
    """
    Recherche dans la base de connaissances agricoles.

    - **query**: Question ou mots-cles
    - **top_k**: Nombre de resultats (defaut: 3)
    """
    if not rag_knowledge.RAG_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="Service RAG non disponible. Installez: pip install sentence-transformers"
        )

    results = rag_knowledge.search(query.query, query.top_k)

    return JSONResponse(content={
        "success": True,
        "query": query.query,
        "results": results,
        "count": len(results)
    })


@router.post("/add")
async def add_document(doc: DocumentInput):
    """
    Ajoute un document a la base de connaissances.

    - **text**: Contenu du document
    - **metadata**: Metadonnees optionnelles (culture, categorie, etc.)
    """
    if not rag_knowledge.RAG_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="Service RAG non disponible"
        )

    success = rag_knowledge.add_document(doc.text, doc.metadata)

    if not success:
        raise HTTPException(status_code=500, detail="Erreur lors de l'ajout")

    return JSONResponse(content={
        "success": True,
        "message": "Document ajoute",
        "total_documents": len(rag_knowledge._knowledge_base)
    })


@router.post("/init")
async def init_knowledge_base():
    """
    Initialise la base avec des connaissances agricoles par defaut.
    """
    if not rag_knowledge.RAG_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="Service RAG non disponible"
        )

    count = rag_knowledge.init_default_knowledge()

    return JSONResponse(content={
        "success": True,
        "message": f"Base initialisee avec {count} documents",
        "total_documents": len(rag_knowledge._knowledge_base)
    })


@router.get("/status")
async def get_rag_status():
    """Retourne le statut du service RAG"""
    return rag_knowledge.check_rag_status()


@router.get("/documents")
async def list_documents():
    """Liste tous les documents de la base"""
    docs = [
        {
            "text": doc["text"][:200] + "..." if len(doc["text"]) > 200 else doc["text"],
            "metadata": doc["metadata"]
        }
        for doc in rag_knowledge._knowledge_base
    ]

    return JSONResponse(content={
        "success": True,
        "documents": docs,
        "count": len(docs)
    })
