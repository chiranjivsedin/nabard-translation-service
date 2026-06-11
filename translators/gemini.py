import os
import logging
from fastapi import HTTPException
from .base import BaseTranslator

logger = logging.getLogger("nabard-translator.gemini")

SYSTEM_INSTRUCTION = (
    "You are an expert translator specializing in translating administrative documents, "
    "official notesheets, and banking correspondence from English to formal, official, administrative Hindi (Rajbhasha) "
    "for the National Bank for Agriculture and Rural Development (NABARD). "
    "\n\nCRITICAL CONSTRAINTS:"
    "\n1. Translate ONLY the text content."
    "\n2. Maintain the EXACT structure and placement of all HTML tags (such as <table>, <tr>, <td>, <ul>, <ol>, <li>, <p>, <h2>, <h3>, <h4>, <hr>, <strong>, etc.). Do NOT edit, delete, or translate any tag structures."
    "\n3. Do NOT add any prefix, conversational intro, explanation, or code blocks. Only reply with the translated string retaining original HTML tags."
    "\n4. Use high-quality official Hindi administrative vocabulary (Rajbhasha), e.g. use 'पुनर्वित्त' for 'refinance', 'स्वीकृति' for 'sanction', 'आवंटन' for 'allocation', 'संवितरण' for 'disbursement', 'अनुमोदनार्थ प्रस्तुत' for 'put up for approval'."
)


class GeminiTranslator(BaseTranslator):
    def __init__(self):
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY is required for GeminiTranslator")

        try:
            import google.generativeai as genai
            genai.configure(api_key=api_key)
            self.model = genai.GenerativeModel(
                model_name=os.getenv("GEMINI_MODEL", "gemini-2.0-flash"),
                system_instruction=SYSTEM_INSTRUCTION,
            )
            logger.info("GeminiTranslator initialized (model=%s)", os.getenv("GEMINI_MODEL", "gemini-2.0-flash"))
        except ImportError:
            raise RuntimeError("google-generativeai package is not installed. Run: pip install google-generativeai")

    async def translate(self, content: str) -> str:
        try:
            response = self.model.generate_content(content)
            result = response.text
            logger.info("Gemini translation completed")
            return result
        except Exception as e:
            logger.exception("Gemini translation error")
            raise HTTPException(status_code=500, detail=f"Gemini translation error: {str(e)}")
