"""
Wourri — Service BD Vectorielle IVR (BLOC B)

Approche : IVR intelligent inspiré CGIAR/Viamo
- Corpus pré-écrit de réponses bambara validées par intent × culture × condition
- Chroma comme BD vectorielle locale (embarquée, pas de serveur)
- Recherche par métadonnées structurées (intent + culture) + similarité sémantique sur les tags
- Aucune traduction en temps réel sur le chemin principal
"""

import json
import os
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Chemin du corpus IVR
_CORPUS_PATH = Path(__file__).parent.parent.parent / "dictionnaires" / "corpus_ivr.json"
# Chemin de persistance Chroma
_CHROMA_DIR = Path(__file__).parent.parent.parent / "data" / "chroma_ivr"

_chroma_collection = None


def _load_corpus() -> list[dict]:
    """Charge le corpus IVR depuis le fichier JSON."""
    with open(_CORPUS_PATH, encoding="utf-8") as f:
        data = json.load(f)
    return data.get("entries", [])


def _get_collection():
    """Initialise et retourne la collection Chroma (singleton)."""
    global _chroma_collection
    if _chroma_collection is not None:
        return _chroma_collection

    try:
        import chromadb
        from chromadb.utils import embedding_functions

        _CHROMA_DIR.mkdir(parents=True, exist_ok=True)

        client = chromadb.PersistentClient(path=str(_CHROMA_DIR))

        # Embedding function : paraphrase-multilingual (déjà présent dans modeles_manuels)
        model_path = Path(__file__).parent.parent.parent / "modeles_manuels" / "paraphrase-multilingual-MiniLM-L12-v2"
        if model_path.exists():
            ef = embedding_functions.SentenceTransformerEmbeddingFunction(
                model_name=str(model_path)
            )
        else:
            ef = embedding_functions.DefaultEmbeddingFunction()
            logger.warning("[VDB] Modèle multilingual non trouvé — utilisation embedding par défaut")

        _chroma_collection = client.get_or_create_collection(
            name="corpus_ivr",
            embedding_function=ef,
            metadata={"description": "Wourri corpus IVR agricole bambara/dioula"}
        )

        # Peupler si vide
        if _chroma_collection.count() == 0:
            _populate_collection(_chroma_collection)

        logger.info(f"[VDB] Collection chargée : {_chroma_collection.count()} entrées")
        return _chroma_collection

    except ImportError:
        logger.error("[VDB] chromadb non installé — pip install chromadb")
        return None
    except Exception as e:
        logger.error(f"[VDB] Erreur initialisation Chroma: {e}")
        return None


def _populate_collection(collection):
    """Peuple la collection Chroma depuis le corpus JSON."""
    entries = _load_corpus()
    if not entries:
        logger.warning("[VDB] Corpus IVR vide — rien à indexer")
        return

    ids = []
    documents = []
    metadatas = []

    for entry in entries:
        ids.append(entry["id"])
        # Document = texte de recherche (tags + réponse FR pour l'embedding)
        tags_text = " ".join(entry.get("tags", []))
        doc_text = f"{entry.get('reponse_fr', '')} {tags_text}"
        documents.append(doc_text)
        metadatas.append({
            "intent": entry["intent"],
            "cultures": ",".join(entry.get("cultures", ["*"])),
            "conditions": ",".join(entry.get("conditions", [])),
            "reponse_bambara": entry["reponse_bambara"],
            "reponse_fr": entry.get("reponse_fr", ""),
            "score_validation": str(entry.get("score_validation", 0.5)),
            "source": entry.get("source", "corpus_ivr"),
        })

    collection.add(ids=ids, documents=documents, metadatas=metadatas)
    logger.info(f"[VDB] {len(ids)} entrées indexées dans Chroma")


def chercher_reponse_ivr(intent: str, cultures: list[str], conditions: list[str] = None) -> dict | None:
    """
    Cherche la meilleure réponse bambara dans la BD vectorielle.

    Stratégie :
    1. Filtre exact sur intent + culture (métadonnées)
    2. Si plusieurs résultats → choisit le meilleur score_validation
    3. Si aucun résultat exact → cherche par intent seul
    4. Si toujours rien → retourne None (fallback activé)

    Retourne : dict avec reponse_bambara, reponse_fr, score_validation, id
    """
    collection = _get_collection()
    if collection is None:
        return None

    conditions = conditions or []

    # Construire les filtres de culture possibles
    culture_filters = cultures + ["*"]

    # Essai 1 : intent exact + culture exacte
    for culture in cultures:
        try:
            results = collection.query(
                query_texts=[f"{intent} {culture}"],
                n_results=3,
                where={"$and": [
                    {"intent": {"$eq": intent}},
                    {"cultures": {"$contains": culture}}
                ]}
            )
            entry = _best_result(results, conditions)
            if entry:
                logger.info(f"[VDB] Match exact: {entry['id']} (intent={intent}, culture={culture})")
                return entry
        except Exception:
            pass

    # Essai 2 : intent exact + culture générique "*"
    try:
        results = collection.query(
            query_texts=[f"{intent}"],
            n_results=3,
            where={"$and": [
                {"intent": {"$eq": intent}},
                {"cultures": {"$contains": "*"}}
            ]}
        )
        entry = _best_result(results, conditions)
        if entry:
            logger.info(f"[VDB] Match générique: {entry['id']} (intent={intent}, culture=*)")
            return entry
    except Exception:
        pass

    # Essai 3 : intent seul, toutes cultures
    try:
        results = collection.query(
            query_texts=[f"{intent} {' '.join(cultures)}"],
            n_results=5,
            where={"intent": {"$eq": intent}}
        )
        entry = _best_result(results, conditions)
        if entry:
            logger.info(f"[VDB] Match intent seul: {entry['id']} (intent={intent})")
            return entry
    except Exception as e:
        logger.warning(f"[VDB] Erreur recherche: {e}")

    logger.info(f"[VDB] Aucun résultat pour intent={intent}, cultures={cultures}")
    return None


def _best_result(results: dict, conditions: list[str]) -> dict | None:
    """Sélectionne la meilleure entrée parmi les résultats Chroma."""
    if not results or not results.get("ids") or not results["ids"][0]:
        return None

    ids = results["ids"][0]
    metadatas = results["metadatas"][0]

    best = None
    best_score = -1.0

    for i, (entry_id, meta) in enumerate(zip(ids, metadatas)):
        score = float(meta.get("score_validation", 0.5))

        # Bonus si les conditions correspondent
        entry_conditions = meta.get("conditions", "").split(",")
        for cond in conditions:
            if cond in entry_conditions:
                score += 0.1

        if score > best_score:
            best_score = score
            best = {
                "id": entry_id,
                "reponse_bambara": meta["reponse_bambara"],
                "reponse_fr": meta.get("reponse_fr", ""),
                "score_validation": float(meta.get("score_validation", 0.5)),
                "intent": meta["intent"],
                "cultures": meta.get("cultures", "*"),
            }

    return best


def ajouter_reponse_validee(
    intent: str,
    cultures: list[str],
    reponse_bambara: str,
    reponse_fr: str,
    score_validation: float,
    conditions: list[str] = None,
    tags: list[str] = None,
) -> bool:
    """
    Injecte une nouvelle réponse validée dans la BD vectorielle (auto-apprentissage C6).
    Appelé quand le pipeline de validation valide une réponse dynamique (score > 0.75).
    """
    collection = _get_collection()
    if collection is None:
        return False

    import time
    entry_id = f"dynamic_{intent}_{cultures[0] if cultures else 'generic'}_{int(time.time())}"
    doc_text = f"{reponse_fr} {' '.join(tags or [])}"

    try:
        collection.add(
            ids=[entry_id],
            documents=[doc_text],
            metadatas=[{
                "intent": intent,
                "cultures": ",".join(cultures or ["*"]),
                "conditions": ",".join(conditions or []),
                "reponse_bambara": reponse_bambara,
                "reponse_fr": reponse_fr,
                "score_validation": str(score_validation),
                "source": "auto_validated",
            }]
        )
        logger.info(f"[VDB] Nouvelle entrée validée ajoutée: {entry_id} (score={score_validation:.2f})")
        return True
    except Exception as e:
        logger.error(f"[VDB] Erreur ajout entrée: {e}")
        return False


def get_reponse_fallback() -> str:
    """Retourne la réponse de sécurité bambara quand VDB ne trouve rien."""
    collection = _get_collection()
    if collection is None:
        return "N bɛ i dɛmɛ i ka sɛnɛ ko la. I ka i ka ɲinini wele fɔ cogo wɛrɛ."

    try:
        results = collection.query(
            query_texts=["fallback"],
            n_results=1,
            where={"intent": {"$eq": "_FALLBACK"}}
        )
        if results and results["ids"] and results["ids"][0]:
            return results["metadatas"][0][0]["reponse_bambara"]
    except Exception:
        pass

    return "N bɛ i dɛmɛ i ka sɛnɛ ko la. I ka i ka ɲinini wele fɔ cogo wɛrɛ."


def initialiser_vdb():
    """Pré-initialise la VDB au démarrage de l'API."""
    logger.info("[VDB] Initialisation BD vectorielle IVR...")
    collection = _get_collection()
    if collection:
        logger.info(f"[VDB] Prête — {collection.count()} entrées")
    else:
        logger.warning("[VDB] BD vectorielle non disponible — fallback traduction actif")
