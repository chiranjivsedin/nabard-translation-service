# NABARD Translation Service

FastAPI backend that translates English notesheets to formal Hindi using a local [Ollama](https://ollama.com) model (`nabard-translator`).

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

Copy `.env.example` to `.env` and adjust as needed:

```bash
cp .env.example .env
```

| Variable | Default | Description |
|---|---|---|
| `OLLAMA_URL` | `http://localhost:11434` | Ollama server URL |
| `OLLAMA_MODEL` | `nabard-translator` | Model name to use |
| `OLLAMA_TIMEOUT` | `120` | Request timeout in seconds |
| `CORS_ORIGINS` | `http://localhost:3000` | Comma-separated allowed origins |

### 3. Build the Ollama model

The `nabard-translator` model is a customised version of `translategemma` with a formal government Hindi system prompt. The `Modelfile` lives in the main frontend repo (`nabard-modern-ui/Modelfile`).

```bash
# From nabard-modern-ui directory
ollama create nabard-translator -f Modelfile

# Verify
ollama list
```

### 4. Start the server

```bash
python -m uvicorn main:app --port 8000 --reload
```

Server runs at `http://localhost:8000`.

---

## API Reference

### `GET /health`

Check service health and Ollama reachability.

**Response**
```json
{
  "status": "ok",
  "ollama": "ok",
  "model": "nabard-translator"
}
```

If Ollama is down:
```json
{
  "status": "ok",
  "ollama": "unreachable: ...",
  "model": "unknown"
}
```

---

### `POST /translate`

Translate English text to formal Hindi.

**Request**
```json
{
  "text": "The Notesheet has been approved by the Department."
}
```

**Response**
```json
{
  "hindi": "टिप्पणी पत्र को विभाग द्वारा अनुमोदित किया गया है।"
}
```

**Error responses**

| Status | Reason |
|---|---|
| `422` | Empty or missing `text` field |
| `503` | Ollama is unreachable |
| `504` | Ollama did not respond within timeout |
| `502` | Ollama returned an error or empty translation |

---

### `GET /docs`

Auto-generated Swagger UI — available at `http://localhost:8000/docs`.

---

## Architecture

```
Frontend (React)
    │
    │  POST /translate  { text: "..." }
    ▼
FastAPI (port 8000)
    │
    │  POST /api/generate  { model, prompt, stream: false }
    ▼
Ollama (port 11434)
    │
    ▼
nabard-translator  (translategemma + NABARD system prompt)
```

The frontend sends plain English text. The backend forwards it to Ollama and returns the Hindi response. Glossary pre-processing (replacing known terms before translation) and artifact stripping (removing "Translation:" prefixes) are handled in the frontend hook (`useNotesheetTranslation.js`) before the text reaches this service.

---

## Production Notes

- In production, Ollama runs on the application server (not the user's browser machine).
- Change `OLLAMA_URL` in `.env` to point to the production Ollama instance.
- Update `CORS_ORIGINS` to the production frontend domain.
- The frontend hook needs its `OLLAMA_URL` constant replaced with the deployed backend URL (one-line change in `useNotesheetTranslation.js`).
- The service is stateless — no database, no auth. Deploy behind the existing backend's authentication layer if needed.

---

## Project Structure

```
nabard-translation-service/
├── main.py              # FastAPI app
├── requirements.txt     # Python dependencies
├── .env                 # Local config (not committed)
├── .env.example         # Config template
└── README.md
```
