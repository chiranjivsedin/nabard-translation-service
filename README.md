# NABARD Translation Service

FastAPI backend that translates English notesheets to formal Hindi (Rajbhasha) using a pluggable AI backend — switch between Ollama (local) and Gemini (cloud) via a single env var.

## Prerequisites

- Python 3.10+
- Ollama installed and running **or** a Gemini API key

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

For Gemini backend, also install:
```bash
pip install google-generativeai
```

### 2. Configure environment

```bash
cp .env.example .env
```

| Variable | Default | Description |
|---|---|---|
| `TRANSLATOR_BACKEND` | `ollama` | Which backend to use: `ollama` or `gemini` |
| `MAX_UPLOAD_MB` | `20` | Max file upload size in MB |
| `CORS_ORIGINS` | `http://localhost:3000` | Comma-separated allowed origins |
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama server URL (ollama only) |
| `OLLAMA_MODEL` | `nabard-translator` | Model name (ollama only) |
| `OLLAMA_TIMEOUT` | `300` | Request timeout in seconds (ollama only) |
| `GEMINI_API_KEY` | — | Gemini API key (gemini only) |
| `GEMINI_MODEL` | `gemini-2.0-flash` | Gemini model name (gemini only) |

### 3. Build the Ollama model (Ollama backend only)

The `nabard-translator` model is a customised version of `translategemma` with a formal Hindi system prompt. The `Modelfile` lives in the `nabard-modern-ui` repo.

```bash
# From nabard-modern-ui directory
ollama create nabard-translator -f Modelfile

# Verify
ollama list
```

### 4. Start the server

```bash
uvicorn server:app --host 0.0.0.0 --port 8000 --reload
```

Server runs at `http://localhost:8000`. Swagger UI available at `http://localhost:8000/docs`.

---

## Switching Backends

Only one env var needs to change — no code changes required.

**Ollama (local model):**
```env
TRANSLATOR_BACKEND=ollama
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=nabard-translator
```

**Gemini (cloud):**
```env
TRANSLATOR_BACKEND=gemini
GEMINI_API_KEY=your-api-key-here
GEMINI_MODEL=gemini-2.0-flash
```

Restart the server after changing `.env`.

---

## Adding a New Backend

1. Create `translators/yourbackend.py` extending `BaseTranslator`
2. Implement the `translate(content: str) -> str` method
3. Register it in `translators/factory.py`
4. Set `TRANSLATOR_BACKEND=yourbackend` in `.env`

No changes to `server.py` or any endpoints needed.

---

## API Reference

### `GET /health`

Check service health and active backend.

**Response**
```json
{
  "status": "ok",
  "backend": "gemini",
  "model": "gemini-2.0-flash"
}
```

---

### `POST /api/translate`

Translate plain English text to Hindi.

**Request**
```json
{
  "content": "The Notesheet has been approved by the Department."
}
```

**Response**
```json
{
  "translated": "टिप्पणी पत्र को विभाग द्वारा अनुमोदित किया गया है।",
  "docx_base64": "",
  "structure_preserved": true,
  "model_used": "gemini-2.0-flash"
}
```

---

### `POST /api/translate-html`

Translate HTML content (e.g. from rich text editor) to Hindi. Returns translated HTML and a generated `.docx` as base64.

**Request**
```json
{
  "html": "<p>The loan has been <strong>sanctioned</strong>.</p>"
}
```

**Response**
```json
{
  "translated": "<p>ऋण <strong>स्वीकृत</strong> किया गया है।</p>",
  "docx_base64": "<base64 string>",
  "structure_preserved": true,
  "model_used": "gemini-2.0-flash"
}
```

---

### `POST /api/translate-document`

Upload a `.doc` or `.docx` file. Converts to HTML via mammoth, translates to Hindi, returns translated HTML and a generated `.docx` as base64.

**Request**
`multipart/form-data` with field `file` — `.doc` or `.docx` only, max `MAX_UPLOAD_MB`.

**Response**
```json
{
  "translated": "<translated HTML>",
  "docx_base64": "<base64 string>",
  "structure_preserved": true,
  "model_used": "gemini-2.0-flash"
}
```

**Error responses**

| Status | Reason |
|---|---|
| `400` | Empty content |
| `413` | File exceeds `MAX_UPLOAD_MB` |
| `422` | Wrong file type or unreadable document |
| `503` | Ollama is unreachable |
| `500` | Translation or docx generation error |

---

## Architecture

```
Java Backend / Frontend
        │
        │  POST /api/translate-html   { html: "..." }
        │  POST /api/translate-document  (multipart .docx)
        ▼
FastAPI (port 8000)
        │
        ▼
translators/factory.py  (reads TRANSLATOR_BACKEND)
        │
        ├── OllamaTranslator  →  Ollama (port 11434)  →  nabard-translator
        └── GeminiTranslator  →  Gemini API  →  gemini-2.0-flash
```

The service is **stateless** — no database, no session state.

---

## Integration Note for Backend Team

This service was originally prototyped with frontend integration. For the correct **server-to-server** approach:

- Use **`POST /api/translate-html`** for both the notesheet editor tab and the upload tab.
- For the upload tab, the Java backend should fetch the saved document from Documentum, extract its HTML content, and send it to `/api/translate-html` — no need to re-upload the file to this service.
- `/api/translate-document` accepts a `.docx` file directly and handles the HTML extraction internally — use it only if fetching and extracting HTML from Documentum is not straightforward.
- `/api/translate` is for plain text and is useful for testing the service quickly.

---

## Production Notes

- For **Gemini**: no server setup needed, just a valid `GEMINI_API_KEY`.
- For **Ollama**: run on a dedicated server with minimum **16GB RAM**. A GPU is strongly recommended for acceptable translation speed.
- Set `CORS_ORIGINS` to the production frontend domain.
- The service has no built-in auth — deploy behind the application's authentication layer.

---

## Project Structure

```
nabard-translation-service/
├── server.py                # FastAPI application
├── translators/
│   ├── base.py              # Abstract base class
│   ├── factory.py           # Backend selector (reads TRANSLATOR_BACKEND)
│   ├── ollama.py            # Ollama implementation
│   └── gemini.py            # Gemini implementation
├── requirements.txt         # Python dependencies
├── .env                     # Local config (not committed)
├── .env.example             # Config template
└── README.md
```
