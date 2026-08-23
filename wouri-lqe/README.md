# WOURI LQE (ADR-0033/0034)

Atelier linguistique **hors** `wouri-api`.

- Backend : `wouri-lqe` FastAPI (port 8090)
- Front : `wouri-lqe-web` Vue 3 + Vite + Tailwind (port 5173)
- Un compte = une langue (`LQE_ACCOUNTS` JSON)
- **Backend unique : PostgreSQL, schéma `lqe`** — table `productions`
  (`bronze → admin_accepted → production`), langues en table `languages`
  (activer une langue = un `INSERT`). Plus de JSONL (ADR-0034 P4).
- Ne touche pas WhatsApp ni le corpus pgvector du moteur

## Local

```
docker compose -f docker-compose.lqe.yml up -d        # lqe + postgres pgvector (LQE_SECRET requis)

# ou à la main (Postgres requis) :
cd wouri-lqe
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env    # définir LQE_SECRET (>= 16), POSTGRES_*
uvicorn app.main:app --port 8090    # applique les migrations (schéma lqe + seed) au démarrage

cd ..\wouri-lqe-web
npm install
npm run dev
```

## Migration des données JSONL existantes (one-shot)

Si un déploiement antérieur a produit des `tasks.jsonl` / `corpus.jsonl` :

```
cd wouri-lqe
python -m scripts.migrate_jsonl_to_pg    # idempotent, sûr si vide
```
