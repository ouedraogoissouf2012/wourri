#!/usr/bin/env bash
#
# Wourri — Wrapper Alembic migrations en prod (Sprint I.a, issue #201).
#
# Pourquoi un script dédié plutôt qu'un hook `on_startup` :
#   - Alembic prend des locks DDL exclusifs sur la BDD pendant les migrations
#   - Si 2 workers uvicorn démarrent simultanément, ils déclenchent 2 migrations
#     parallèles → l'une bloque l'autre → timeout au démarrage
#   - Pattern projet recommandé : étape explicite AVANT `docker compose up`
#
# Usage (sur le serveur Scaleway après pull d'une nouvelle image) :
#   docker compose -f docker-compose.prod.yml run --rm wouri-api \
#       /app/scripts/run_migrations.sh
#
# Variables d'environnement attendues (issue #258 — 2 formes acceptées) :
#   POSTGRES_URL   postgresql+psycopg://user:pwd@host:5432/wourri_prod
#   OU composants  POSTGRES_HOST [+ POSTGRES_PORT] + POSTGRES_USER +
#                  POSTGRES_DB + POSTGRES_PASSWORD_FILE|POSTGRES_PASSWORD
#   (alembic/env.py résout via app/db/url_resolver.py — mêmes sources)
#
# Référence : ADR-0008 §Phase B (migrations Alembic versionnées).

set -euo pipefail

# ──────────────────────────────────────────────────────────────────
# 1. Pré-vérifications
# ──────────────────────────────────────────────────────────────────
# Issue #258 : le compose prod ne passe plus POSTGRES_URL mais les composants
# POSTGRES_* + le secret postgres_password. On vérifie qu'AU MOINS une des
# deux formes est présente ; la résolution fine (composants incomplets →
# message détaillé) est déléguée à url_resolver via alembic/env.py.
if [[ -z "${POSTGRES_URL:-}" && -z "${POSTGRES_HOST:-}" ]]; then
    echo "[MIGRATIONS] ERREUR : ni POSTGRES_URL ni POSTGRES_HOST définies."
    echo "[MIGRATIONS] Configurez dans .env.prod / compose (cf. .env.prod.template, issue #258)."
    exit 1
fi

cd /app

# ──────────────────────────────────────────────────────────────────
# 2. Affiche l'état actuel + ce qui va être appliqué
# ──────────────────────────────────────────────────────────────────
echo "[MIGRATIONS] État BDD actuel :"
alembic current

# Sprint I.a review NICE-3 : on liste l'historique complet plutôt que
# d'extraire la révision courante via awk (parsing fragile sur les lignes
# INFO d'Alembic). L'opérateur voit toute l'histoire — utile pour debug.
echo
echo "[MIGRATIONS] Historique complet des migrations :"
alembic history

# ──────────────────────────────────────────────────────────────────
# 3. Application
# ──────────────────────────────────────────────────────────────────
echo
echo "[MIGRATIONS] Application de toutes les migrations en attente..."
alembic upgrade head

# ──────────────────────────────────────────────────────────────────
# 4. Vérification post-migration
# ──────────────────────────────────────────────────────────────────
echo
echo "[MIGRATIONS] État BDD après migration :"
alembic current

echo
echo "[MIGRATIONS] OK — toutes les migrations sont appliquées."
