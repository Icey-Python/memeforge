"""LLM connector base class.

A provider turns a meme topic into a short video script (list of spoken
lines). Implementations must be async so they can be awaited directly
inside FastAPI endpoints and background render jobs.
"""

from typing import List, Optional

from pydantic import BaseModel


class GeneratedScript(BaseModel):
    title: str
    lines: List[str]


class DiscoveredModel(BaseModel):
    """A model served by a provider endpoint (live discovery)."""

    id: str  # exact model name to send back to the provider
    label: str = ""  # display label for dropdowns
    size_bytes: Optional[int] = None
    family: Optional[str] = None
    parameter_size: Optional[str] = None
    quantization: Optional[str] = None
    modified_at: Optional[str] = None
    available: bool = True


class BaseLLMProvider:
    """Contract for model connectors (OpenAI-compatible, Ollama, ...)."""

    name: str = "base"

    def __init__(self, model: Optional[str] = None, base_url: Optional[str] = None,
                 api_key: Optional[str] = None) -> None:
        self.model = model
        self.base_url = base_url
        self.api_key = api_key

    async def generate_script(
        self, topic: str, tone: str = "reddit-commenter", max_lines: int = 8
    ) -> GeneratedScript:
        """Generate a short punchy script about `topic`."""
        raise NotImplementedError

    async def list_models(self) -> List[DiscoveredModel]:
        """Discover the models this connector's endpoint currently serves.

        Powers `/api/v1/models/discover` (Ollama `/api/tags`, OpenAI-
        compatible `GET /models`). Raises on connectivity/HTTP errors;
        the endpoint reports those as `reachable: false`.
        """
        raise NotImplementedError

    def is_configured(self) -> bool:
        """Whether this connector has everything it needs to run."""
        return True
