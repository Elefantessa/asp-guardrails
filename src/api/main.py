"""
Cloudway Policy Guardrails — FastAPI application

Start:
    uvicorn src.api.main:app --reload --port 8000

Endpoints:
    POST /api/chat              — submit a query
    GET  /api/chat/examples     — sidebar example queries
    GET  /api/history/{tid}     — conversation history
    GET  /api/review/pending    — escalated cases awaiting review
    POST /api/review/{turn_id}  — approve / reject a case
    GET  /api/review/history    — reviewed cases
    GET  /healthz               — health check
"""

import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

# Normalize lowercase env var keys (dotenv may write aws_* in lowercase)
for _k in list(os.environ.keys()):
    if _k.startswith(("aws_", "bedrock_")):
        os.environ.setdefault(_k.upper(), os.environ[_k])

from src.api.routes.chat import router as chat_router
from src.api.routes.history import router as history_router
from src.api.routes.review import router as review_router

app = FastAPI(
    title="Cloudway Policy Guardrails API",
    version="1.0.0",
    description="Neuro-symbolic LLM guardrails for holiday booking policy compliance.",
)

# Allow the Next.js dev server and any configured origin
_allowed_origins = os.getenv(
    "CORS_ALLOWED_ORIGINS",
    "http://localhost:3000,http://localhost:3001",
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _allowed_origins],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat_router)
app.include_router(history_router)
app.include_router(review_router)


@app.get("/healthz", tags=["meta"])
def health() -> dict:
    return {"status": "ok", "version": app.version}
