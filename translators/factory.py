import os
import logging
from .base import BaseTranslator

logger = logging.getLogger("nabard-translator.factory")


def get_translator() -> BaseTranslator:
    backend = os.getenv("TRANSLATOR_BACKEND", "ollama").lower()
    logger.info("Loading translator backend: %s", backend)

    if backend == "ollama":
        from .ollama import OllamaTranslator
        return OllamaTranslator()
    elif backend == "gemini":
        from .gemini import GeminiTranslator
        return GeminiTranslator()
    else:
        raise RuntimeError(f"Unknown TRANSLATOR_BACKEND '{backend}'. Supported: ollama, gemini")
