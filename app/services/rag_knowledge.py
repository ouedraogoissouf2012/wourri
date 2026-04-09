"""
WOURI - RAG (Retrieval-Augmented Generation)
Base de connaissances agricoles avec embeddings

NOTE: Necessite sentence-transformers
Pour installer: pip install sentence-transformers
"""
import logging
import os
import json
from typing import List, Optional
from app.config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()

# Verifier si sentence-transformers est disponible
RAG_AVAILABLE = False
SentenceTransformer = None
np = None

try:
    from sentence_transformers import SentenceTransformer as _ST
    import numpy as _np
    SentenceTransformer = _ST
    np = _np
    RAG_AVAILABLE = True
except ImportError:
    logger.info("INFO: sentence-transformers non installe - RAG desactive")
    logger.info("Pour activer: pip install sentence-transformers")

# Cache du modele et des embeddings
_embedding_model = None
_knowledge_base = []  # Liste de documents
_knowledge_embeddings = None  # Matrice d'embeddings

# Chemin du modele local
MODEL_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "modeles_manuels",
    "paraphrase-multilingual-MiniLM-L12-v2"
)


def get_embedding_model():
    """Charge le modele d'embeddings (lazy loading)"""
    global _embedding_model

    if not RAG_AVAILABLE:
        return None

    if _embedding_model is None:
        logger.info("Chargement du modele d'embeddings...")
        # Utiliser le modele local s'il existe, sinon telecharger
        if os.path.exists(MODEL_PATH):
            logger.info(f"Utilisation du modele local: {MODEL_PATH}")
            _embedding_model = SentenceTransformer(MODEL_PATH)
        else:
            logger.info("Telechargement du modele depuis HuggingFace...")
            _embedding_model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
        logger.info("Modele d'embeddings charge!")

    return _embedding_model


def add_document(text: str, metadata: dict = None) -> bool:
    """
    Ajoute un document a la base de connaissances.

    Args:
        text: Contenu du document
        metadata: Metadonnees optionnelles (source, categorie, etc.)

    Returns:
        True si ajoute avec succes
    """
    global _knowledge_base, _knowledge_embeddings

    if not RAG_AVAILABLE or not text:
        return False

    try:
        model = get_embedding_model()
        if model is None:
            return False

        # Creer l'embedding
        embedding = model.encode([text])[0]

        # Ajouter a la base
        doc = {
            "text": text,
            "metadata": metadata or {},
            "embedding": embedding.tolist()
        }
        _knowledge_base.append(doc)

        # Mettre a jour la matrice d'embeddings
        if _knowledge_embeddings is None:
            _knowledge_embeddings = np.array([embedding])
        else:
            _knowledge_embeddings = np.vstack([_knowledge_embeddings, embedding])

        return True

    except Exception as e:
        logger.error(f"Erreur ajout document: {e}")
        return False


def search(query: str, top_k: int = 3) -> List[dict]:
    """
    Recherche les documents les plus pertinents pour une requete.

    Args:
        query: Question ou requete de recherche
        top_k: Nombre de resultats a retourner

    Returns:
        Liste de documents avec score de similarite
    """
    if not RAG_AVAILABLE or not query or len(_knowledge_base) == 0:
        return []

    try:
        model = get_embedding_model()
        if model is None:
            return []

        # Encoder la requete
        query_embedding = model.encode([query])[0]

        # Calculer les similarites cosinus
        similarities = np.dot(_knowledge_embeddings, query_embedding) / (
            np.linalg.norm(_knowledge_embeddings, axis=1) * np.linalg.norm(query_embedding)
        )

        # Trier par similarite
        top_indices = np.argsort(similarities)[::-1][:top_k]

        results = []
        for idx in top_indices:
            results.append({
                "text": _knowledge_base[idx]["text"],
                "metadata": _knowledge_base[idx]["metadata"],
                "score": float(similarities[idx])
            })

        return results

    except Exception as e:
        logger.error(f"Erreur recherche RAG: {e}")
        return []


def load_knowledge_base(filepath: str) -> int:
    """
    Charge une base de connaissances depuis un fichier JSON.

    Args:
        filepath: Chemin vers le fichier JSON

    Returns:
        Nombre de documents charges
    """
    if not os.path.exists(filepath):
        return 0

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

        count = 0
        for doc in data:
            if add_document(doc.get("text", ""), doc.get("metadata")):
                count += 1

        logger.info(f"Base de connaissances chargee: {count} documents")
        return count

    except Exception as e:
        logger.error(f"Erreur chargement base: {e}")
        return 0


def save_knowledge_base(filepath: str) -> bool:
    """
    Sauvegarde la base de connaissances dans un fichier JSON.
    """
    try:
        data = [
            {"text": doc["text"], "metadata": doc["metadata"]}
            for doc in _knowledge_base
        ]

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        return True

    except Exception as e:
        logger.error(f"Erreur sauvegarde base: {e}")
        return False


def init_default_knowledge():
    """Initialise la base avec des connaissances agricoles de base"""
    default_docs = [
        {
            "text": "Le cacao necessite un climat tropical humide avec des temperatures entre 21 et 32 degres Celsius. La pluviometrie ideale est de 1500 a 2000 mm par an.",
            "metadata": {"culture": "cacao", "categorie": "climat"}
        },
        {
            "text": "Pour le cafe, la recolte se fait generalement entre octobre et fevrier en Cote d'Ivoire. Les cerises doivent etre rouges et mures.",
            "metadata": {"culture": "cafe", "categorie": "recolte"}
        },
        {
            "text": "L'igname se plante au debut de la saison des pluies, entre mars et avril. La recolte intervient 8 a 12 mois apres la plantation.",
            "metadata": {"culture": "igname", "categorie": "calendrier"}
        },
        {
            "text": "Le manioc est resistant a la secheresse mais craint l'exces d'eau. Il se multiplie par boutures de 20 a 30 cm.",
            "metadata": {"culture": "manioc", "categorie": "plantation"}
        },
        {
            "text": "Pour lutter contre les maladies du cacaoyer comme le swollen shoot, il faut eliminer les arbres malades et traiter les voisins.",
            "metadata": {"culture": "cacao", "categorie": "maladie"}
        },
        {
            "text": "Le riz pluvial se cultive sans irrigation, avec une pluviometrie de 1000 a 1500 mm. Le semis se fait en debut de saison des pluies.",
            "metadata": {"culture": "riz", "categorie": "technique"}
        },
        {
            "text": "L'anacarde (noix de cajou) se recolte entre fevrier et mai. Les pommes tombees au sol indiquent la maturite.",
            "metadata": {"culture": "anacarde", "categorie": "recolte"}
        },
        {
            "text": "Pour l'hevea, la saignee commence 5 a 7 ans apres la plantation. Elle se fait tot le matin pour un meilleur rendement en latex.",
            "metadata": {"culture": "hevea", "categorie": "technique"}
        }
    ]

    count = 0
    for doc in default_docs:
        if add_document(doc["text"], doc["metadata"]):
            count += 1

    logger.info(f"Base de connaissances initialisee: {count} documents agricoles")
    return count


def check_rag_status() -> dict:
    """Verifie le statut du RAG"""
    return {
        "rag_available": RAG_AVAILABLE,
        "model_loaded": _embedding_model is not None,
        "documents_count": len(_knowledge_base),
        "model_path": MODEL_PATH if os.path.exists(MODEL_PATH) else "huggingface"
    }
