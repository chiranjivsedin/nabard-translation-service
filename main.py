import os
import logging
from contextlib import asynccontextmanager

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, field_validator

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "nabard-translator")
OLLAMA_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", "120"))
CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")]


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting NABARD Translation Service")
    logger.info("Ollama URL: %s | Model: %s | Timeout: %ss", OLLAMA_URL, OLLAMA_MODEL, OLLAMA_TIMEOUT)
    yield
    logger.info("Shutting down NABARD Translation Service")


app = FastAPI(
    title="NABARD Translation Service",
    description="Translates English notesheets to formal Hindi using a local Ollama model.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


class TranslateRequest(BaseModel):
    text: str

    @field_validator("text")
    @classmethod
    def text_must_not_be_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("text must not be empty")
        return v.strip()


class TranslateResponse(BaseModel):
    hindi: str


class HealthResponse(BaseModel):
    status: str
    ollama: str
    model: str


@app.get("/health", response_model=HealthResponse)
async def health():
    """Check service health and Ollama reachability."""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.get(f"{OLLAMA_URL}/api/tags")
            response.raise_for_status()
            tags = response.json()
            model_names = [m["name"] for m in tags.get("models", [])]
            ollama_status = "ok"
            model_status = OLLAMA_MODEL if any(OLLAMA_MODEL in n for n in model_names) else f"NOT FOUND — available: {model_names}"
    except Exception as exc:
        logger.warning("Ollama health check failed: %s", exc)
        ollama_status = f"unreachable: {exc}"
        model_status = "unknown"

    return HealthResponse(status="ok", ollama=ollama_status, model=model_status)


@app.post("/translate", response_model=TranslateResponse)
async def translate(body: TranslateRequest):
    """Translate English text to formal Hindi using the nabard-translator Ollama model."""
    logger.info("Translate request — %d chars", len(body.text))

    try:
        async with httpx.AsyncClient(timeout=OLLAMA_TIMEOUT) as client:
            response = await client.post(
                f"{OLLAMA_URL}/api/generate",
                json={
                    "model": OLLAMA_MODEL,
                    "prompt": body.text,
                    "stream": False,
                },
            )
    except httpx.ConnectError:
        logger.error("Cannot connect to Ollama at %s", OLLAMA_URL)
        raise HTTPException(status_code=503, detail="Ollama service is unreachable. Ensure Ollama is running.")
    except httpx.TimeoutException:
        logger.error("Ollama request timed out after %ss", OLLAMA_TIMEOUT)
        raise HTTPException(status_code=504, detail=f"Ollama did not respond within {OLLAMA_TIMEOUT} seconds.")

    if response.status_code != 200:
        logger.error("Ollama returned %s: %s", response.status_code, response.text)
        raise HTTPException(status_code=502, detail=f"Ollama error: {response.status_code}")

    data = response.json()
    hindi = data.get("response", "").strip()

    if not hindi:
        logger.warning("Ollama returned empty response for input: %.100s", body.text)
        raise HTTPException(status_code=502, detail="Ollama returned an empty translation.")

    logger.info("Translate success — %d chars out", len(hindi))
    return TranslateResponse(hindi=hindi)
