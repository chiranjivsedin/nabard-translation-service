# NABARD Translation Service

FastAPI backend that translates English notesheets to formal Hindi (Rajbhasha) using a local [Ollama](https://ollama.com) model (`nabard-translator`).

## Prerequisites

- Python 3.10+
- [Ollama](https://ollama.com) installed and running
- `nabard-translator` model built (see setup below)

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
```

| Variable | Default | Description |
|---|---|---|
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama server URL |
| `OLLAMA_MODEL` | `nabard-translator` | Model name to use |
| `OLLAMA_TIMEOUT` | `300` | Request timeout in seconds |
| `MAX_UPLOAD_MB` | `20` | Max file upload size in MB |
| `CORS_ORIGINS` | `http://localhost:3000` | Comma-separated allowed origins |

### 3. Build the Ollama model

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

## API Reference

### `GET /health`

Check service and Ollama reachability.

**Response**
```json
{
  "status": "ok",
  "ollama": "ok",
  "model": "nabard-translator"
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
  "model_used": "nabard-translator"
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
  "model_used": "nabard-translator"
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
  "model_used": "nabard-translator"
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
        │  POST /api/chat  (Ollama chat API)
        ▼
Ollama (port 11434)
        │
        ▼
nabard-translator  (translategemma + NABARD Rajbhasha system prompt)
```

The service is **stateless** — no database, no session state.

---

## Production Notes

- Run on a dedicated server with minimum **16GB RAM**. A GPU is strongly recommended for acceptable translation speed.
- Set `OLLAMA_HOST` in `.env` if Ollama runs on a separate machine.
- Set `CORS_ORIGINS` to the production frontend domain.
- Deploy Ollama as a system service so it restarts on reboot.
- The service has no built-in auth — deploy behind the application's authentication layer.

---

## Project Structure

```
nabard-translation-service/
├── server.py            # FastAPI application
├── requirements.txt     # Python dependencies
├── .env                 # Local config (not committed)
├── .env.example         # Config template
└── README.md
```
