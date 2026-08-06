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
from functools import lru_cache
from pathlib import Path

from app.services.corpus import season_scoring

logger = logging.getLogger(__name__)

# Chemin du corpus IVR
_CORPUS_PATH = Path(__file__).parent.parent.parent / "dictionnaires" / "corpus_ivr.json"

# Cache du corpus en mémoire (chargé une seule fois au démarrage)
_corpus_cache: dict | None = None

def _load_corpus() -> dict:
    """Charge le corpus IVR en mémoire (singleton)."""
    global _corpus_cache
    if _corpus_cache is None:
        try:
            with open(_CORPUS_PATH, encoding="utf-8") as f:
                _corpus_cache = json.load(f)
        except Exception as e:
            logger.error(f"[VDB] Impossible de charger le corpus IVR: {e}")
            _corpus_cache = {"entries": []}
    return _corpus_cache
# Chemin de persistance Chroma
_CHROMA_DIR = Path(__file__).parent.parent.parent / "data" / "chroma_ivr"

# Identifiant HuggingFace du modèle d'embedding (followup #246).
# DOIT être strictement identique à scripts/import_corpus_ivr.py::_HF_MODEL_ID
# pour garantir la cohérence des embeddings entre import et search. Avant cette
# constante, le fallback `DefaultEmbeddingFunction()` de chromadb utilisait un
# modèle 384-dim générique DIFFERENT → divergence silencieuse import vs search.
_HF_MODEL_ID = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

_chroma_collection = None


def _load_corpus_entries() -> list[dict]:
    """Retourne les entrées du corpus IVR (via le cache de _load_corpus)."""
    return _load_corpus().get("entries", [])


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

        # Embedding function : paraphrase-multilingual.
        # Followup #246 : fallback HuggingFace (cohérence avec scripts/import_corpus_ivr.py).
        # Avant : `DefaultEmbeddingFunction()` chromadb (modèle 384-dim générique
        # DIFFÉRENT) → bug silencieux de divergence embeddings import vs search.
        # Apres : meme modele paraphrase-multilingual via slug HF (telechargement
        # cache HF_HOME, persistant sur volume `wourri_hf_cache` en prod).
        model_path = Path(__file__).parent.parent.parent / "modeles_manuels" / "paraphrase-multilingual-MiniLM-L12-v2"
        if model_path.exists():
            ef = embedding_functions.SentenceTransformerEmbeddingFunction(
                model_name=str(model_path)
            )
        else:
            logger.info("[VDB] Modele local absent — fallback HF: %s", _HF_MODEL_ID)
            ef = embedding_functions.SentenceTransformerEmbeddingFunction(
                model_name=_HF_MODEL_ID
            )

        _chroma_collection = client.get_or_create_collection(
            name="corpus_ivr",
            embedding_function=ef,
            metadata={"description": "Wourri corpus IVR agricole bambara/dioula"}
        )

        # Synchroniser si vide, si le count a changé, ou si la version du corpus a changé
        with open(_CORPUS_PATH, encoding="utf-8") as f:
            corpus_data = json.load(f)
        corpus_entries = corpus_data.get("entries", [])
        corpus_version = corpus_data.get("version", "")
        vdb_count = _chroma_collection.count()

        _VERSION_FILE = _CHROMA_DIR / ".corpus_version"
        stored_version = _VERSION_FILE.read_text(encoding="utf-8").strip() if _VERSION_FILE.exists() else ""

        needs_rebuild = (
            vdb_count == 0
            or vdb_count != len(corpus_entries)
            or stored_version != corpus_version
        )

        if needs_rebuild:
            if vdb_count == 0:
                logger.info(f"[VDB] Collection vide — peuplement initial ({len(corpus_entries)} entrées)")
            else:
                logger.info(
                    f"[VDB] Corpus mis à jour (count={vdb_count}→{len(corpus_entries)}, "
                    f"version={stored_version!r}→{corpus_version!r}) — rechargement"
                )
                client.delete_collection("corpus_ivr")
                _chroma_collection = client.get_or_create_collection(
                    name="corpus_ivr",
                    embedding_function=ef,
                    metadata={"description": "Wourri corpus IVR agricole bambara/dioula"}
                )
            _populate_collection(_chroma_collection, corpus_entries)
            _VERSION_FILE.write_text(corpus_version, encoding="utf-8")
        else:
            logger.info(f"[VDB] Corpus à jour — {vdb_count} entrées (v{corpus_version})")

        return _chroma_collection

    except ImportError:
        logger.error("[VDB] chromadb non installé — pip install chromadb")
        return None
    except Exception as e:
        logger.error(f"[VDB] Erreur initialisation Chroma: {e}")
        return None


def _populate_collection(collection, entries=None):
    """Peuple la collection Chroma depuis le corpus JSON (ou depuis entries si fourni)."""
    if entries is None:
        entries = _load_corpus_entries()
    if not entries:
        logger.warning("[VDB] Corpus IVR vide — rien à indexer")
        return

    ids = []
    documents = []
    metadatas = []

    for entry in entries:
        ids.append(entry["id"])
        # Document = texte de recherche (tags + réponse FR + phrases bambara CI attestées)
        tags_text = " ".join(entry.get("tags", []))
        phrases_text = " ".join(p["text"] for p in entry.get("phrases_attestees", []))
        doc_text = f"{entry.get('reponse_fr', '')} {tags_text} {phrases_text}"
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

    # Essai 1 : intent exact + culture exacte ($eq, compatible chromadb 1.5+)
    for culture in cultures:
        try:
            results = collection.query(
                query_texts=[f"{intent} {culture}"],
                n_results=3,
                where={"$and": [
                    {"intent": {"$eq": intent}},
                    {"cultures": {"$eq": culture}}
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
                {"cultures": {"$eq": "*"}}
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


def _best_result(
    results: dict, conditions: list[str], season: str | None = None
) -> dict | None:
    """Sélectionne la meilleure entrée parmi les résultats Chroma.

    Le scoring métier (bonus/pénalité saison, bonus conditions) est délégué à
    `season_scoring.score_entry` — logique partagée avec le backend pgvector.
    Ce backend ne fait que son I/O : désérialiser les conditions Chroma (CSV)
    et mapper les métadonnées.

    Args:
        season: saison courante, injectable pour les tests ; par défaut
            `season_scoring.get_current_season()`.
    """
    if not results or not results.get("ids") or not results["ids"][0]:
        return None

    ids = results["ids"][0]
    metadatas = results["metadatas"][0]

    if season is None:
        season = season_scoring.get_current_season()
    best = None
    best_score = -1.0

    for entry_id, meta in zip(ids, metadatas):
        base = float(
            meta.get("score_validation", season_scoring.DEFAULT_VALIDATION_SCORE)
        )
        # Chroma stocke les conditions en CSV → désérialisation (I/O du backend).
        entry_conditions = meta.get("conditions", "").split(",")
        score = season_scoring.score_entry(base, entry_conditions, conditions, season)

        if score > best_score:
            best_score = score
            best = {
                "id": entry_id,
                "reponse_bambara": meta["reponse_bambara"],
                "reponse_fr": meta.get("reponse_fr", ""),
                "score_validation": base,
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


def get_phrases_for_intent(intent: str, cultures: list[str]) -> list[dict]:
    """
    Retourne les phrases_attestees de la première entrée IVR correspondant à intent + culture.
    Utilisé pour enrichir le meta de la réponse avec des exemples bambara CI réels.
    Utilise le cache mémoire — pas de lecture disque à chaque appel.
    """
    try:
        data = _load_corpus()
        for entry in data.get("entries", []):
            if entry["intent"] != intent:
                continue
            entry_cultures = entry.get("cultures", ["*"])
            if any(c in entry_cultures for c in cultures + ["*"]):
                phrases = entry.get("phrases_attestees", [])
                if phrases:
                    return phrases
    except Exception as e:
        logger.warning(f"[VDB] Erreur lecture phrases_attestees (intent={intent}): {e}")
    return []


def initialiser_vdb():
    """Pré-initialise la VDB au démarrage de l'API."""
    logger.info("[VDB] Initialisation BD vectorielle IVR...")
    collection = _get_collection()
    if collection:
        logger.info(f"[VDB] Prête — {collection.count()} entrées")
    else:
        logger.warning("[VDB] BD vectorielle non disponible — fallback traduction actif")
