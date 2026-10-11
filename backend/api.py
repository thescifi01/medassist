"""Production API for MedAssist (educational demo): analysis, history, AI chat."""
import base64
import io
import os
import re
import threading
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, defer

import assistant
from db import get_db, init_db
from models import Message, Scan
from pipeline import analyze, get_model
from ratelimit import RateLimiter

MAX_BYTES = 10 * 1024 * 1024
MAX_PIXELS = 40_000_000
ALLOWED_TYPES = {"image/png", "image/jpeg", "image/jpg"}
CLIENT_ID_RE = re.compile(r"[A-Za-z0-9-]{16,64}")

# Grad-CAM registers hooks on the shared model, so run one analysis at a time.
_model_lock = threading.Lock()
analyze_limiter = RateLimiter(limit=10, window_seconds=600)
chat_limiter = RateLimiter(limit=20, window_seconds=600)


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    get_model()  # load weights once at startup so the first request is fast
    yield


app = FastAPI(title="MedAssist API (educational demo)", lifespan=lifespan)

origins = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "*").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)


# ---------- helpers ----------
def current_client(x_client_id: str = Header(...)) -> str:
    """Anonymous per-browser id. All data is scoped to it (no accounts in this demo)."""
    if not CLIENT_ID_RE.fullmatch(x_client_id):
        raise HTTPException(400, "Invalid client id.")
    return x_client_id


def iso(dt: datetime) -> str:
    if dt.tzinfo is None:  # SQLite returns naive datetimes
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def scan_or_404(db: Session, scan_id: int, client: str) -> Scan:
    scan = db.get(Scan, scan_id)
    if scan is None or scan.client_id != client:
        raise HTTPException(404, "Scan not found.")
    return scan


def summary(s: Scan) -> dict:
    return {
        "id": s.id,
        "created_at": iso(s.created_at),
        "top_finding": s.findings[0] if s.findings else None,
        "heatmap_label": s.heatmap_label,
    }


def detail(s: Scan) -> dict:
    return {
        **summary(s),
        "symptoms": s.symptoms,
        "findings": s.findings,
        "heatmap": "data:image/jpeg;base64," + base64.b64encode(s.heatmap_jpeg).decode(),
        "report": s.report,
        "messages": [
            {"id": m.id, "role": m.role, "content": m.content, "created_at": iso(m.created_at)}
            for m in s.messages
        ],
        "disclaimer": "Educational demo only. Not a diagnosis.",
    }


# ---------- routes ----------
@app.get("/")
def root():
    return {"service": "medassist-api", "docs": "/docs", "health": "/health"}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/analyze")
def analyze_endpoint(
    file: UploadFile = File(...),
    symptoms: str = Form(""),
    client: str = Depends(current_client),
    db: Session = Depends(get_db),
):
    analyze_limiter.check(client)

    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(400, "Please upload a PNG or JPG image.")
    data = file.file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "Image is larger than 10 MB.")
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except (UnidentifiedImageError, OSError):
        raise HTTPException(400, "Could not read that image file.")
    if img.width * img.height > MAX_PIXELS:
        raise HTTPException(400, "Image resolution is too large.")

    symptoms = symptoms.strip()[:500]
    with _model_lock:
        out = analyze(img, symptoms)

    buf = io.BytesIO()
    out["heatmap"].convert("RGB").save(buf, format="JPEG", quality=80)

    scan = Scan(
        client_id=client,
        symptoms=symptoms,
        findings=[{"label": n, "probability": p} for n, p in out["findings"]],
        heatmap_label=out["heatmap_label"],
        report=out["report"],
        heatmap_jpeg=buf.getvalue(),
    )
    db.add(scan)
    db.commit()
    return detail(scan)


@app.get("/scans")
def list_scans(client: str = Depends(current_client), db: Session = Depends(get_db)):
    rows = db.scalars(
        select(Scan)
        .where(Scan.client_id == client)
        .options(defer(Scan.heatmap_jpeg))
        .order_by(Scan.id.desc())
        .limit(50)
    ).all()
    return [summary(s) for s in rows]


@app.get("/scans/{scan_id}")
def get_scan(scan_id: int, client: str = Depends(current_client), db: Session = Depends(get_db)):
    return detail(scan_or_404(db, scan_id, client))


@app.delete("/scans/{scan_id}", status_code=204)
def delete_scan(scan_id: int, client: str = Depends(current_client), db: Session = Depends(get_db)):
    scan = scan_or_404(db, scan_id, client)
    db.delete(scan)
    db.commit()
    return Response(status_code=204)


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=1000)


@app.post("/scans/{scan_id}/chat")
def chat(
    scan_id: int,
    body: ChatIn,
    client: str = Depends(current_client),
    db: Session = Depends(get_db),
):
    chat_limiter.check(client)
    scan = scan_or_404(db, scan_id, client)
    text = body.message.strip()
    if not text:
        raise HTTPException(400, "Message is empty.")

    history = [{"role": m.role, "content": m.content} for m in scan.messages][-12:]
    while history and history[0]["role"] != "user":  # must start with a user turn
        history.pop(0)

    try:
        reply = assistant.ask(scan, history, text)
    except assistant.AssistantUnavailable as e:
        raise HTTPException(503, str(e))
    except Exception:
        raise HTTPException(502, "The assistant is temporarily unavailable. Please try again.")

    db.add_all(
        [
            Message(scan_id=scan.id, role="user", content=text),
            Message(scan_id=scan.id, role="assistant", content=reply),
        ]
    )
    db.commit()
    return {"reply": reply}
