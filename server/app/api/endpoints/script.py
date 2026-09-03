"""Script generation endpoints (model connectors)."""

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from app.core import settings
from app.providers.llm import registry as llm_registry
from app.providers.llm.base import default_line_count
from app.schemas.render_schema import (
    LLMProvider,
    ModelDiscoveryRequest,
    ModelDiscoveryResponse,
    ScriptGenerateRequest,
    ScriptResponse,
)

script_router = APIRouter()


@script_router.get("/models")
async def list_models():
    """LLM connector catalog for the frontend model connector node."""
    return llm_registry.list_llm_providers()


@script_router.post("/models/discover", response_model=ModelDiscoveryResponse)
async def discover_models(request: ModelDiscoveryRequest):
    """Live model discovery for the selected provider.

    Queries the provider endpoint (Ollama `/api/tags`, OpenAI-compatible
    `GET /models`) so the model connector dropdown lists what is actually
    installed. Connectivity/HTTP failures are reported as `reachable: false`
    (HTTP 200) instead of a 5xx so the UI can render a helpful hint.
    """
    provider = llm_registry.get_llm_provider(
        request.provider.value,
        base_url=request.base_url,
        api_key=request.api_key,
    )
    try:
        models = await provider.list_models()
    except Exception as exc:
        detail = str(exc).strip() or type(exc).__name__
        return ModelDiscoveryResponse(
            provider=provider.name,
            base_url=provider.base_url,
            reachable=False,
            error=f"Could not list models at {provider.base_url} — {detail}",
            models=[],
        )
    return ModelDiscoveryResponse(
        provider=provider.name,
        base_url=provider.base_url,
        reachable=True,
        models=models,
    )


@script_router.post("/generate-script", response_model=ScriptResponse)
async def generate_script(request: ScriptGenerateRequest):
    """Generate a short-form video script about a topic with the selected
    model connector.

    `duration_target` paces the script: word budgets target ~2.2-2.5
    words/sec of speech, so the 60s default yields ~130-150 words —
    about a minute of speech. `max_lines` defaults to a duration-derived
    pacing (~4s of speech per line) when omitted.
    """
    provider = llm_registry.get_llm_provider(
        request.provider.value,
        model=request.model,
        base_url=request.base_url,
        api_key=request.api_key,
    )
    effective_max_lines = (
        request.max_lines or default_line_count(request.duration_target)
    )
    try:
        script = await provider.generate_script(
            topic=request.topic,
            tone=request.tone,
            max_lines=effective_max_lines,
            duration_target=request.duration_target,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=502, detail=f"Script generation failed: {exc}"
        ) from exc

    # Last line is always the punchline (SFX + caption color).
    return ScriptResponse(
        topic=request.topic,
        title=script.title,
        provider=provider.name,
        model=getattr(provider, "model", None),
        lines=[
            {
                "index": i,
                "text": text,
                "is_punchline": i == len(script.lines) - 1,
            }
            for i, text in enumerate(script.lines)
        ],
        generated_at=datetime.now(timezone.utc),
    )
