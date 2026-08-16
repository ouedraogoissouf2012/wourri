"""Wourri — Import incrémental du corpus depuis Convex (L3 #410).

Convex est la source de vérité du texte validé (reponse_fr / reponse_bambara).
Ce script synchronise le corpus PostgreSQL+pgvector local avec l'export Convex,
SANS remplacer `import_corpus_ivr.py` (import initial full-rebuild depuis le JSON).
Prévu au boot du conteneur + cron horaire. Trois garanties (brief Marcel) :

- **Idempotent** : `revision` (jeton OPAQUE, égalité stricte) comparée à
  `corpus_metadata.convex_revision`. Identique -> zéro écriture, exit 0.
- **Autonome** : Convex injoignable / non-200 / JSON invalide -> log + exit 0,
  le corpus local reste servi tel quel (jamais planter le moteur).
- **Fusion non destructive** : par `id`, met à jour reponse_fr/reponse_bambara et
  recalcule `document_text` via `import_corpus_ivr._build_document_text` (fonction
  canonique) avec les tags/phrases LOCAUX — cohérence exacte avec l'index. Les
  entrées locales absentes de l'export sont conservées (jamais supprimées), loggées.
- **ADR-0031** : n'écrit dans pgvector que les fiches **Or / Production**.
  Bronze / Argent et `source_lang=bam` non revalidé `dyu` sont ignorés
  (`corpus_service` inchangé : ce qui n'est pas importé n'est pas servi).

Usage : voir `import_corpus_ivr.py`, plus CONVEX_BASE_URL + X_CORPUS_KEY (env).
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent.parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

try:
    from dotenv import load_dotenv

    load_dotenv(_HERE / ".env", override=False)
except ImportError:
    pass

logger = logging.getLogger("wouri.import_corpus_convex")

CONVEX_REVISION_KEY = "convex_revision"
_EXPORT_PATH = "/corpus/export"
_DEFAULT_TIMEOUT = 15.0


# --- Logique pure (testable sans I/O) --------------------------------------

def should_import(fetched_revision, stored_revision) -> bool:
    """True si la révision Convex diffère de celle stockée localement.

    `fetched_revision` est un jeton OPAQUE : comparaison d'égalité stricte,
    aucune hypothèse sur son format. Une révision vide/absente n'importe jamais
    (donnée douteuse -> on conserve le corpus local).
    """
    if not fetched_revision:
        return False
    return fetched_revision != stored_revision


def plan_fusion(convex_entries, local_ids):
    """Partitionne l'export en (à_mettre_à_jour, à_insérer).

    Un `id` déjà présent en local -> mise à jour (fusion texte Convex +
    métadonnées locales). Sinon -> insertion.
    """
    to_update = [e for e in convex_entries if e.get("id") in local_ids]
    to_insert = [e for e in convex_entries if e.get("id") not in local_ids]
    return to_update, to_insert


_PUBLISHABLE_STATUSES = frozenset({"or", "gold", "production"})
_BLOCKED_STATUSES = frozenset({"bronze", "argent", "silver"})
_BAM_SOURCES = frozenset({"bam", "bambara"})
_DYU_TARGETS = frozenset({"dyu", "dioula"})


def is_publishable(entry) -> bool:
    """True si la fiche peut entrer dans pgvector (ADR-0031).

    - status absent : Production implicite (export Convex actuel, 197 fiches).
    - bronze / argent / silver : jamais.
    - source_lang bam/bambara : jamais, sauf revalidation explicite `validated_as=dyu`.
    """
    if not isinstance(entry, dict):
        return False
    status = str(entry.get("status") or "").strip().lower()
    if status in _BLOCKED_STATUSES:
        return False
    if status and status not in _PUBLISHABLE_STATUSES:
        return False
    source = str(entry.get("source_lang") or "").strip().lower()
    if source in _BAM_SOURCES:
        validated = str(entry.get("validated_as") or "").strip().lower()
        return validated in _DYU_TARGETS
    return True


def filter_publishable(entries):
    """Sépare (servables, ignorées) sans muter l'entrée."""
    kept, skipped = [], []
    for entry in entries or []:
        (kept if is_publishable(entry) else skipped).append(entry)
    return kept, skipped


# --- Accès Convex (autonome : ne lève jamais) ------------------------------

def fetch_corpus_export(base_url, corpus_key, *, timeout=_DEFAULT_TIMEOUT, client=None):
    """GET {base_url}/corpus/export avec l'en-tête X-Corpus-Key.

    AUTONOMIE : toute erreur (réseau, timeout, non-200, JSON invalide) retourne
    None ; l'appelant conserve alors le corpus local intact.
    """
    url = base_url.rstrip("/") + _EXPORT_PATH
    headers = {"X-Corpus-Key": corpus_key}
    owns_client = client is None
    try:
        if owns_client:
            import httpx

            client = httpx.Client()
        resp = client.get(url, headers=headers, timeout=timeout)
        if resp.status_code != 200:
            logger.warning(
                "Convex /corpus/export a répondu %s — corpus local conservé",
                resp.status_code,
            )
            return None
        return resp.json()
    except Exception as exc:  # autonomie : jamais planter le moteur
        logger.warning("Convex injoignable (%s) — corpus local conservé", exc)
        return None
    finally:
        if owns_client and client is not None:
            try:
                client.close()
            except Exception:
                pass


# --- Accès BD --------------------------------------------------------------

def _get_stored_revision(conn):
    from sqlalchemy import text

    row = conn.execute(
        text("SELECT value FROM corpus_metadata WHERE key = :k"),
        {"k": CONVEX_REVISION_KEY},
    ).fetchone()
    return row[0] if row else None


def _set_revision(conn, revision) -> None:
    from sqlalchemy import text

    conn.execute(
        text(
            "INSERT INTO corpus_metadata (key, value, updated_at) "
            "VALUES (:k, :v, NOW()) "
            "ON CONFLICT (key) DO UPDATE "
            "SET value = EXCLUDED.value, updated_at = NOW()"
        ),
        {"k": CONVEX_REVISION_KEY, "v": revision},
    )


def _load_local_ids(conn):
    from sqlalchemy import text

    rows = conn.execute(text("SELECT id FROM corpus_entries")).fetchall()
    return {r[0] for r in rows}


def _load_local_context(conn, ids):
    """Tags + phrases_attestées LOCAUX des entrées à mettre à jour.

    Sert à reconstruire `document_text` à l'identique de l'import JSON :
    reponse_fr (nouveau, Convex) + tags (local) + phrases (local).
    """
    from sqlalchemy import text

    if not ids:
        return {}
    id_list = list(ids)
    tag_rows = conn.execute(
        text("SELECT id, tags FROM corpus_entries WHERE id = ANY(:ids)"),
        {"ids": id_list},
    ).fetchall()
    ctx = {r[0]: {"tags": r[1] or [], "phrases_attestees": []} for r in tag_rows}
    # ORDER BY id = ordre d'insertion = ordre du JSON d'origine : reproduit
    # exactement le document_text (donc l'embedding) de l'import initial.
    phrase_rows = conn.execute(
        text(
            "SELECT entry_id, text FROM corpus_phrases_attestees "
            "WHERE entry_id = ANY(:ids) ORDER BY id"
        ),
        {"ids": id_list},
    ).fetchall()
    for entry_id, txt in phrase_rows:
        if entry_id in ctx:
            ctx[entry_id]["phrases_attestees"].append({"text": txt})
    return ctx


def _embed(model, docs):
    """Encode les documents (mêmes options que import_corpus_ivr, cohérence)."""
    return model.encode(
        docs, convert_to_numpy=True, show_progress_bar=False, normalize_embeddings=False
    )


def _apply_updates(conn, model, to_update, local_ctx) -> int:
    """Met à jour reponse_fr/reponse_bambara + document_text + embedding."""
    from sqlalchemy import text

    if not to_update:
        return 0

    # Ne jamais blanchir une réponse servie : un reponse_bambara vide côté export
    # (donnée douteuse) ne doit pas écraser le contenu local. Skip + log.
    servable = [e for e in to_update if e.get("reponse_bambara")]
    if len(servable) != len(to_update):
        logger.warning(
            "%d mise(s) à jour ignorée(s) — reponse_bambara vide côté Convex",
            len(to_update) - len(servable),
        )
    to_update = servable
    if not to_update:
        return 0

    from scripts.import_corpus_ivr import _build_document_text, _format_vector

    docs = []
    for e in to_update:
        ctx = local_ctx.get(e["id"], {"tags": [], "phrases_attestees": []})
        docs.append(
            _build_document_text(
                {
                    "reponse_fr": e.get("reponse_fr", ""),
                    "tags": ctx["tags"],
                    "phrases_attestees": ctx["phrases_attestees"],
                }
            )
        )
    embeddings = _embed(model, docs)
    update_sql = text(
        """
        UPDATE corpus_entries
        SET reponse_fr = :reponse_fr,
            reponse_bambara = :reponse_bambara,
            document_text = :document_text,
            embedding = CAST(:embedding AS vector),
            updated_at = NOW()
        WHERE id = :id
        """
    )
    for e, doc, emb in zip(to_update, docs, embeddings):
        conn.execute(
            update_sql,
            {
                "id": e["id"],
                "reponse_fr": e.get("reponse_fr", ""),
                "reponse_bambara": e.get("reponse_bambara", ""),
                "document_text": doc,
                "embedding": _format_vector(emb),
            },
        )
    return len(to_update)


def _apply_inserts(conn, model, to_insert) -> int:
    """Insère les entrées nouvelles (id absent en local).

    `intent` et `reponse_bambara` sont NOT NULL en base : une entrée qui les
    manque est ignorée + loggée (jamais insérer une entrée non servable).
    Pas de tags/phrases côté Convex -> document_text = reponse_fr seul.
    """
    from sqlalchemy import text

    if not to_insert:
        return 0
    from scripts.import_corpus_ivr import _build_document_text, _format_vector

    valid = []
    for e in to_insert:
        if not e.get("intent") or not e.get("reponse_bambara"):
            logger.warning(
                "Entrée Convex '%s' ignorée (intent/reponse_bambara manquant)",
                e.get("id"),
            )
            continue
        valid.append(e)
    if not valid:
        return 0

    docs = [_build_document_text({"reponse_fr": e.get("reponse_fr", "")}) for e in valid]
    embeddings = _embed(model, docs)
    insert_sql = text(
        """
        INSERT INTO corpus_entries (
            id, intent, cultures, conditions, reponse_bambara, reponse_fr,
            score_validation, tags, source, document_text, embedding
        ) VALUES (
            :id, :intent, :cultures, :conditions, :reponse_bambara, :reponse_fr,
            0.5, ARRAY[]::TEXT[], 'convex', :document_text,
            CAST(:embedding AS vector)
        )
        """
    )
    for e, doc, emb in zip(valid, docs, embeddings):
        conn.execute(
            insert_sql,
            {
                "id": e["id"],
                "intent": e["intent"],
                "cultures": e.get("cultures") or ["*"],
                "conditions": e.get("conditions") or [],
                "reponse_bambara": e["reponse_bambara"],
                "reponse_fr": e.get("reponse_fr", ""),
                "document_text": doc,
                "embedding": _format_vector(emb),
            },
        )
    return len(valid)


def main() -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    base_url = os.getenv("CONVEX_BASE_URL", "").strip()
    corpus_key = os.getenv("X_CORPUS_KEY", "").strip()
    if not base_url or not corpus_key:
        logger.error(
            "CONVEX_BASE_URL et X_CORPUS_KEY requis (secrets Dokploy) — abandon."
        )
        return 2

    export = fetch_corpus_export(base_url, corpus_key)
    if export is None:
        return 0  # autonomie : corpus local conservé

    fetched_revision = str(export.get("revision") or "")
    raw_entries = export.get("entries") or []
    entries, skipped = filter_publishable(raw_entries)
    if skipped:
        logger.info(
            "ADR-0031 : %d fiche(s) non Or+ / bam non revalidé — non importées",
            len(skipped),
        )
    if not fetched_revision or not entries:
        logger.warning(
            "Export Convex sans révision/entrées — corpus local conservé (exit 0)."
        )
        return 0

    from sqlalchemy import create_engine

    from app.db.url_resolver import resolve_postgres_url

    engine = create_engine(resolve_postgres_url(), future=True)

    with engine.connect() as conn:
        stored = _get_stored_revision(conn)
    if not should_import(fetched_revision, stored):
        logger.info(
            "Révision inchangée (%s) — rien à importer (idempotent).", fetched_revision
        )
        return 0

    # Modèle chargé uniquement si un import est réellement nécessaire (~coûteux).
    from scripts.import_corpus_ivr import _load_model

    model = _load_model()

    with engine.begin() as conn:
        local_ids = _load_local_ids(conn)
        to_update, to_insert = plan_fusion(entries, local_ids)
        local_ctx = _load_local_context(conn, {e["id"] for e in to_update})
        n_updated = _apply_updates(conn, model, to_update, local_ctx)
        n_inserted = _apply_inserts(conn, model, to_insert)
        applied = n_updated + n_inserted
        # La révision n'avance QUE si au moins une entrée a été appliquée. Une
        # révision changée + 0 entrée appliquée signale une anomalie (schéma de
        # l'export décalé, ou toutes les entrées mal formées) : ne pas avancer
        # garde l'anomalie visible (ERROR à chaque run) et la rend auto-corrective
        # dès que l'export est réparé — au lieu de la masquer par un no-op.
        if applied:
            _set_revision(conn, fetched_revision)

    if not applied:
        logger.error(
            "Révision %s : %d entrée(s) reçue(s) mais 0 appliquée — schéma de "
            "l'export à vérifier. Révision NON avancée.",
            fetched_revision,
            len(entries),
        )
        return 3

    convex_ids = {e.get("id") for e in entries}
    local_only = local_ids - convex_ids
    if local_only:
        logger.info(
            "%d entrée(s) locale(s) absente(s) de Convex — conservées : %s",
            len(local_only),
            sorted(local_only),
        )

    logger.info(
        "Import Convex OK — %d mises à jour, %d insertions, révision=%s",
        n_updated,
        n_inserted,
        fetched_revision,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
