from abc import ABC, abstractmethod


class BaseTranslator(ABC):
    """Abstract base class. All translator backends must implement translate()."""

    @abstractmethod
    async def translate(self, content: str) -> str:
        """Translate English content to formal Hindi. Raises HTTPException on failure."""
        ...
