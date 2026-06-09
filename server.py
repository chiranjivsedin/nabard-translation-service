import os
import base64
import uvicorn
from io import BytesIO
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import httpx
import mammoth
from docx import Document
from htmldocx import HtmlToDocx

app = FastAPI(
    title="NABARD Notesheet Translation Backend - FastAPI POC",
    description="Python FastAPI backend POC to translate administrative English notesheets into official Hindi using a local Ollama model (nabard-translator)",
    version="1.0.0"
)

# Enable CORS so the React frontend can easily make requests to this backend when running locally
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "nabard-translator")

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
    content: str  # Can be raw text or HTML content
    style: str = "Rajbhasha"  # Optional styling choice

class TranslationResponse(BaseModel):
    translated: str
    docx_base64: str = ""
    structure_preserved: bool
    model_used: str

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
        "ollama_model": OLLAMA_MODEL
    }

@app.post("/api/translate", response_model=TranslationResponse)
async def translate_notesheet(request: TranslationRequest):
    """
    Translates English notesheet contents (with HTML/text formatting) into formal governmental Hindi,
    maintaining formatting by instructing the local Ollama TranslateGemma (nabard-translator) model.
    """
    if not request.content.strip():
        raise HTTPException(status_code=400, detail="Content cannot be empty.")

    ollama_url = f"{OLLAMA_HOST}/api/chat"
    payload = {
        "model": OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_INSTRUCTION},
            {"role": "user", "content": f"Please translate this content: \n\n{request.content}"}
        ],
        "stream": False,
        "options": {
            "temperature": 0.1,  # Low temperature ensures high accuracy and consistency
        }
    }

    try:
        async with httpx.AsyncClient(timeout=300.0) as client:
            response = await client.post(ollama_url, json=payload)
            
            if response.status_code != 200:
                raise HTTPException(
                    status_code=500, 
                    detail=f"Ollama backend returned status {response.status_code}: {response.text}"
                )
                
            resp_data = response.json()
            translated_content = resp_data["message"]["content"]
            
            return TranslationResponse(
                translated=translated_content,
                structure_preserved=True,
                model_used=OLLAMA_MODEL
            )

    except httpx.ConnectError:
        # Provide a helpful error when Ollama is not running
        raise HTTPException(
            status_code=503,
            detail=(
                f"Could not connect to Ollama service at {OLLAMA_HOST}. "
                "Ensure Ollama is running (`ollama serve`) and the model "
                f"'{OLLAMA_MODEL}' is successfully pulled."
            )
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Translation error: {str(e)}")

@app.post("/api/translate-document", response_model=TranslationResponse)
async def translate_document(file: UploadFile = File(...)):
    """
    Accepts a .docx file, converts it to HTML via mammoth, translates the HTML
    to formal Hindi via Ollama /api/chat, and returns the translated HTML.
    """
    if not file.filename.lower().endswith((".docx", ".doc")):
        raise HTTPException(status_code=422, detail="Only .doc and .docx files are accepted.")

    contents = await file.read()

    result = mammoth.convert_to_html(BytesIO(contents))
    html_content = result.value

    if not html_content.strip():
        raise HTTPException(status_code=422, detail="The document appears to be empty or contains no readable text.")

    payload = {
        "model": OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_INSTRUCTION},
            {"role": "user", "content": f"Please translate this content: \n\n{html_content}"}
        ],
        "stream": False,
        "options": {"temperature": 0.1}
    }

    try:
        async with httpx.AsyncClient(timeout=300.0) as client:
            response = await client.post(f"{OLLAMA_HOST}/api/chat", json=payload)

            if response.status_code != 200:
                raise HTTPException(
                    status_code=500,
                    detail=f"Ollama backend returned status {response.status_code}: {response.text}"
                )

            translated_content = response.json()["message"]["content"]

            # Generate docx from translated HTML
            docx_b64 = ""
            try:
                doc = Document()
                parser = HtmlToDocx()
                parser.add_html_to_document(translated_content, doc)
                buf = BytesIO()
                doc.save(buf)
                docx_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
            except Exception:
                pass  # docx generation failure is non-blocking

            return TranslationResponse(
                translated=translated_content,
                docx_base64=docx_b64,
                structure_preserved=True,
                model_used=OLLAMA_MODEL
            )

    except httpx.ConnectError:
        raise HTTPException(
            status_code=503,
            detail=(
                f"Could not connect to Ollama service at {OLLAMA_HOST}. "
                "Ensure Ollama is running (`ollama serve`) and the model "
                f"'{OLLAMA_MODEL}' is successfully pulled."
            )
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Translation error: {str(e)}")


if __name__ == "__main__":
    print(f"Starting FastAPI server for NABARD Notesheet Translator...")
    print(f"Connecting to Ollama model '{OLLAMA_MODEL}' at {OLLAMA_HOST}")
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
