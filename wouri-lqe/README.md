# WOURI LQE (ADR-0033)

Atelier linguistique **hors** `wouri-api`.

- Backend : `wouri-lqe` FastAPI (port 8090)
- Front : `wouri-lqe-web` Vue 3 + Vite + Tailwind (port 5173)
- Un compte = une langue (`LQE_ACCOUNTS` JSON)
- Store unique `tasks.jsonl` / `corpus.jsonl` + champ `language`
- Ne touche pas WhatsApp / pgvector

## Local

```
cd wouri-lqe
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --port 8090

cd ..\wouri-lqe-web
npm install
npm run dev
```
