
from typing import Any, List, Optional, Tuple
from abc import ABC, abstractmethod

class AIProvider(ABC):
    """Abstract base class for all AI backends (Gemini, Ollama, etc.)."""
    
    @abstractmethod
    def list_models(self) -> List[str]:
        """Returns available models."""
        pass

    @abstractmethod
    def generate_json(self, prompt: str, stage_label: str = "AI REQUEST", images: Optional[Any] = None) -> Optional[Any]:
        """Executes a structured JSON fallback request."""
        pass

    @abstractmethod
    def get_adaptive_delay(self) -> float:
        """Returns current rate-limit delay."""
        pass
