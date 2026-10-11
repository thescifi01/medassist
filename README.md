# MedAssist: Multimodal Chest X-ray Assistant

Upload a chest X-ray and optional symptoms. Get predicted findings, a Grad-CAM heatmap
showing where the model looked, an LLM-drafted report, and an AI assistant you can chat
with about the scan. Every scan and chat is saved in a database so you can reopen it later.

> **Educational demo only. Not a medical device. Not for diagnosis.**

## Architecture

```
Vercel (static frontend)  --HTTPS-->  Render (FastAPI + Docker)  -->  Postgres (Neon)
  frontend/                             backend/                       scans, messages
  upload, results, chat, history        |
                                        +-- DenseNet121 (TorchXRayVision, pretrained)
                                        +-- Grad-CAM on the top finding
                                        +-- Claude: draft report + chat assistant
```

- **Database**: SQLAlchemy. Tables `scans` (findings, report, symptoms, processed heatmap)
  and `messages` (chat turns, cascade-deleted with the scan). Tables are created on startup.
- **Identity**: no accounts. The browser generates a random ID stored in `localStorage` and
  sends it as `X-Client-Id`; every query is scoped to it. Fine for a demo, not real auth.
- **Privacy**: the uploaded file is never stored, only a processed 448px heatmap preview.
  Users can delete any scan (and its chat) from the UI.
- **Assistant**: sees the scan's findings, symptoms and report, keeps the last 12 messages of
  context, refuses to diagnose, and flags red-flag symptoms. Rate limited per client.

## Run locally

Backend (uses SQLite `medassist.db` automatically):
```bash
cd backend
python -m venv venv && source venv/bin/activate
pip install torch torchvision
pip install -r requirements.txt
export ANTHROPIC_API_KEY=your_key    # needed for the chat assistant
uvicorn api:app --reload             # http://localhost:8000/docs
```

Frontend (second terminal):
```bash
cd frontend
python -m http.server 5173           # open http://localhost:5173
```
`frontend/config.js` already points at `http://localhost:8000`.

## Deploy

### 1. Database (Neon, free Postgres)
Render's free filesystem is wiped on every restart, so SQLite would lose your data.
1. Create a project at neon.tech and copy the connection string
   (`postgresql://user:pass@host/dbname?sslmode=require`).
2. You will paste it into Render as `DATABASE_URL` below. Check the provider's current free-tier
   limits and retention rules.

### 2. Backend on Render
1. Push this repo to GitHub.
2. Render dashboard: **New > Blueprint**, pick the repo (it reads `render.yaml`).
3. Set env vars: `DATABASE_URL` (from Neon), `ANTHROPIC_API_KEY`. Leave `ALLOWED_ORIGINS` for step 4.
4. Deploy, copy the service URL (e.g. `https://medassist-api.onrender.com`) and check
   `/health` returns `{"status":"ok"}`.

The free plan has 512 MB RAM, which is tight for PyTorch. If the deploy crashes with
out-of-memory, change `plan: free` to `plan: starter` in `render.yaml`. The free plan also
sleeps after idle time; the frontend shows "waking up" and the first request is slow.

### 3. Frontend on Vercel
1. Edit `frontend/config.js`, set `API_URL` to your Render URL, commit and push.
2. Vercel: **Add New > Project**, import the repo, set **Root Directory** to `frontend`,
   framework preset **Other**, no build command. Deploy.

### 4. Lock down CORS
In Render set `ALLOWED_ORIGINS` to your Vercel URL (comma-separate multiple), e.g.
`https://medassist.vercel.app`, then redeploy.

## API

All routes except `/health` need the header `X-Client-Id` (16-64 chars, letters/digits/dashes).

| Method | Path | Purpose |
|---|---|---|
| POST | `/analyze` | multipart `file` (PNG/JPG, max 10 MB) + optional `symptoms`; saves and returns the scan |
| GET | `/scans` | your last 50 scans (summaries) |
| GET | `/scans/{id}` | full scan with heatmap, report and chat messages |
| DELETE | `/scans/{id}` | delete a scan and its chat |
| POST | `/scans/{id}/chat` | JSON `{"message": "..."}`, returns `{"reply": "..."}` |
| GET | `/health` | health check |

## Credits

Pretrained model: [TorchXRayVision](https://github.com/mlmed/torchxrayvision) (Cohen et al.).

## Roadmap

- Real user accounts (OAuth) instead of anonymous IDs
- Alembic migrations
- Streaming chat replies
- Held-out evaluation (AUROC per class)
