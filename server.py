import os
import base64
import logging
import uvicorn
from io import BytesIO
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import httpx
import mammoth
from docx import Document
from htmldocx import HtmlToDocx
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("nabard-translator")

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "nabard-translator")
OLLAMA_TIMEOUT = float(os.getenv("OLLAMA_TIMEOUT", "300"))
MAX_UPLOAD_MB = float(os.getenv("MAX_UPLOAD_MB", "20"))
MAX_UPLOAD_BYTES = int(MAX_UPLOAD_MB * 1024 * 1024)

_raw_cors = os.getenv("CORS_ORIGINS", "http://localhost:3000")
CORS_ORIGINS = [o.strip() for o in _raw_cors.split(",") if o.strip()]

app = FastAPI(
    title="NABARD Notesheet Translation Service",
    description="Translates administrative English notesheets to formal Hindi using a local Ollama model.",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SYSTEM_INSTRUCTION = (
    "You are NABARD TranslateGemma, an expert translator specializing in translating administrative documents, "
    "official notesheets, and banking correspondence from English to formal, official, administrative Hindi (Rajbhasha) "
    "for the National Bank for Agriculture and Rural Development (NABARD). "
    "\n\nCRITICAL CONSTRAINTS:"
    "\n1. Translate ONLY the text content."
    "\n2. Maintain the EXACT structure and placement of all HTML tags (such as <table>, <tr>, <td>, <ul>, <ol>, <li>, <p>, <h2>, <h3>, <h4>, <hr>, <strong>, etc.). Do NOT edit, delete, or translate any tag structures."
    "\n3. Do NOT add any prefix, conversational intro, explanation, or code blocks. Only reply with the translated string retaining original HTML tags."
    "\n4. Use high-quality official Hindi administrative vocabulary (Rajbhasha), e.g. use 'पुनर्वित्त' for 'refinance', 'स्वीकृति' for 'sanction', 'आवंटन' for 'allocation', 'संवितरण' for 'disbursement', 'अनुमोदनार्थ प्रस्तुत' for 'put up for approval'."
)


class TranslationRequest(BaseModel):
    content: str


class HtmlTranslationRequest(BaseModel):
    html: str


class TranslationResponse(BaseModel):
    translated: str
    docx_base64: str = ""
    structure_preserved: bool
    model_used: str


def html_to_docx_base64(html: str) -> str:
    doc = Document()
    HtmlToDocx().add_html_to_document(html, doc)
    buf = BytesIO()
    doc.save(buf)
    return base64.b64encode(buf.getvalue()).decode("utf-8")


async def call_ollama_chat(content: str) -> str:
    payload = {
        "model": OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_INSTRUCTION},
            {"role": "user", "content": f"Please translate this content: \n\n{content}"},
        ],
        "stream": False,
        "options": {"temperature": 0.1},
    }
    logger.info("Sending translation request to Ollama (model=%s)", OLLAMA_MODEL)
    try:
        async with httpx.AsyncClient(timeout=OLLAMA_TIMEOUT) as client:
            response = await client.post(f"{OLLAMA_HOST}/api/chat", json=payload)
            if response.status_code != 200:
                logger.error("Ollama returned status %s", response.status_code)
                raise HTTPException(status_code=500, detail=f"Ollama error: {response.status_code}")
            result = response.json()["message"]["content"]
            logger.info("Translation completed successfully")
            return result
    except httpx.ConnectError:
        logger.error("Cannot connect to Ollama at %s", OLLAMA_HOST)
        raise HTTPException(
            status_code=503,
            detail=f"Could not connect to Ollama at {OLLAMA_HOST}. Ensure Ollama is running.",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Unexpected error during translation")
        raise HTTPException(status_code=500, detail=f"Translation error: {str(e)}")


@app.get("/health")
async def health():
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.get(f"{OLLAMA_HOST}/api/tags")
            response.raise_for_status()
            tags = response.json()
            model_names = [m["name"] for m in tags.get("models", [])]
            ollama_status = "ok"
            model_status = OLLAMA_MODEL if any(OLLAMA_MODEL in n for n in model_names) else f"NOT FOUND — available: {model_names}"
    except Exception as exc:
        ollama_status = f"unreachable: {exc}"
        model_status = "unknown"

    return {"status": "ok", "ollama": ollama_status, "model": model_status}


@app.get("/")
def read_root():
    return {
        "status": "online",
        "service": "NABARD Notesheet Translator",
        "ollama_endpoint": OLLAMA_HOST,
        "ollama_model": OLLAMA_MODEL,
    }


@app.post("/api/translate", response_model=TranslationResponse)
async def translate_notesheet(request: TranslationRequest):
    if not request.content.strip():
        raise HTTPException(status_code=400, detail="Content cannot be empty.")
    translated = await call_ollama_chat(request.content)
    return TranslationResponse(translated=translated, structure_preserved=True, model_used=OLLAMA_MODEL)


@app.post("/api/translate-html", response_model=TranslationResponse)
async def translate_html(request: HtmlTranslationRequest):
    if not request.html.strip():
        raise HTTPException(status_code=400, detail="HTML content cannot be empty.")

    logger.info("translate-html request received")
    translated = await call_ollama_chat(request.html)

    docx_b64 = ""
    try:
        docx_b64 = html_to_docx_base64(translated)
    except Exception:
        logger.warning("docx generation failed for translate-html; returning without docx")

    return TranslationResponse(
        translated=translated,
        docx_base64=docx_b64,
        structure_preserved=True,
        model_used=OLLAMA_MODEL,
    )


@app.post("/api/translate-document", response_model=TranslationResponse)
async def translate_document(file: UploadFile = File(...)):
    if not file.filename.lower().endswith((".docx", ".doc")):
        raise HTTPException(status_code=422, detail="Only .doc and .docx files are accepted.")

    contents = await file.read()

    if len(contents) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum allowed size is {MAX_UPLOAD_MB:.0f} MB.",
        )

    logger.info("translate-document request: file=%s size=%d bytes", file.filename, len(contents))

    result = mammoth.convert_to_html(BytesIO(contents))
    html_content = result.value

    if not html_content.strip():
        raise HTTPException(status_code=422, detail="The document appears to be empty or contains no readable text.")

    translated_content = await call_ollama_chat(html_content)

    docx_b64 = ""
    try:
        docx_b64 = html_to_docx_base64(translated_content)
    except Exception:
        logger.warning("docx generation failed for translate-document; returning without docx")

    return TranslationResponse(
        translated=translated_content,
        docx_base64=docx_b64,
        structure_preserved=True,
        model_used=OLLAMA_MODEL,
    )


if __name__ == "__main__":
    logger.info("Starting NABARD Translation Service (model=%s, ollama=%s)", OLLAMA_MODEL, OLLAMA_HOST)
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
