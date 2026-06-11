import os
import logging
import httpx
from fastapi import HTTPException
from .base import BaseTranslator

logger = logging.getLogger("nabard-translator.ollama")

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


class OllamaTranslator(BaseTranslator):
    def __init__(self):
        self.host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
        self.model = os.getenv("OLLAMA_MODEL", "nabard-translator")
        self.timeout = float(os.getenv("OLLAMA_TIMEOUT", "300"))
        logger.info("OllamaTranslator initialized (host=%s, model=%s)", self.host, self.model)

    async def translate(self, content: str) -> str:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_INSTRUCTION},
                {"role": "user", "content": f"Please translate this content: \n\n{content}"},
            ],
            "stream": False,
            "options": {"temperature": 0.1},
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(f"{self.host}/api/chat", json=payload)
                if response.status_code != 200:
                    logger.error("Ollama returned status %s", response.status_code)
                    raise HTTPException(status_code=500, detail=f"Ollama error: {response.status_code}")
                result = response.json()["message"]["content"]
                logger.info("Ollama translation completed")
                return result
        except httpx.ConnectError:
            logger.error("Cannot connect to Ollama at %s", self.host)
            raise HTTPException(
                status_code=503,
                detail=f"Could not connect to Ollama at {self.host}. Ensure Ollama is running.",
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.exception("Unexpected error during Ollama translation")
            raise HTTPException(status_code=500, detail=f"Translation error: {str(e)}")
