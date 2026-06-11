import os
import base64
import logging
import uvicorn
from io import BytesIO
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import mammoth
from docx import Document
from htmldocx import HtmlToDocx
from dotenv import load_dotenv
from translators.factory import get_translator

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("nabard-translator")

MAX_UPLOAD_MB = float(os.getenv("MAX_UPLOAD_MB", "20"))
MAX_UPLOAD_BYTES = int(MAX_UPLOAD_MB * 1024 * 1024)

_raw_cors = os.getenv("CORS_ORIGINS", "http://localhost:3000")
CORS_ORIGINS = [o.strip() for o in _raw_cors.split(",") if o.strip()]

translator = get_translator()

app = FastAPI(
    title="NABARD Notesheet Translation Service",
    description="Translates administrative English notesheets to formal Hindi using a pluggable AI backend.",
    version="3.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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


def get_model_name() -> str:
    backend = os.getenv("TRANSLATOR_BACKEND", "ollama").lower()
    if backend == "ollama":
        return os.getenv("OLLAMA_MODEL", "nabard-translator")
    if backend == "gemini":
        return os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
    return backend


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "backend": os.getenv("TRANSLATOR_BACKEND", "ollama"),
        "model": get_model_name(),
    }


@app.get("/")
def read_root():
    return {
        "status": "online",
        "service": "NABARD Notesheet Translator",
        "backend": os.getenv("TRANSLATOR_BACKEND", "ollama"),
        "model": get_model_name(),
    }


@app.post("/api/translate", response_model=TranslationResponse)
async def translate_notesheet(request: TranslationRequest):
    if not request.content.strip():
        raise HTTPException(status_code=400, detail="Content cannot be empty.")
    translated = await translator.translate(request.content)
    return TranslationResponse(translated=translated, structure_preserved=True, model_used=get_model_name())


@app.post("/api/translate-html", response_model=TranslationResponse)
async def translate_html(request: HtmlTranslationRequest):
    if not request.html.strip():
        raise HTTPException(status_code=400, detail="HTML content cannot be empty.")

    logger.info("translate-html request received")
    translated = await translator.translate(request.html)

    docx_b64 = ""
    try:
        docx_b64 = html_to_docx_base64(translated)
    except Exception:
        logger.warning("docx generation failed for translate-html; returning without docx")

    return TranslationResponse(
        translated=translated,
        docx_base64=docx_b64,
        structure_preserved=True,
        model_used=get_model_name(),
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

    translated_content = await translator.translate(html_content)

    docx_b64 = ""
    try:
        docx_b64 = html_to_docx_base64(translated_content)
    except Exception:
        logger.warning("docx generation failed for translate-document; returning without docx")

    return TranslationResponse(
        translated=translated_content,
        docx_base64=docx_b64,
        structure_preserved=True,
        model_used=get_model_name(),
    )


if __name__ == "__main__":
    logger.info("Starting NABARD Translation Service (backend=%s, model=%s)", os.getenv("TRANSLATOR_BACKEND", "ollama"), get_model_name())
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
