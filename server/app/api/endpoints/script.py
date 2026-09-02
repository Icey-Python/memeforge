"""Script generation endpoints (model connectors)."""

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from app.core import settings
from app.providers.llm import registry as llm_registry
from app.schemas.render_schema import (
    LLMProvider,
    ScriptGenerateRequest,
    ScriptResponse,
)

script_router = APIRouter()


@script_router.get("/models")
async def list_models():
    """LLM connector catalog for the frontend model connector node."""
    return llm_registry.list_llm_providers()


@script_router.post("/generate-script", response_model=ScriptResponse)
async def generate_script(request: ScriptGenerateRequest):
    """Generate a meme script about a topic with the selected model connector."""
    provider = llm_registry.get_llm_provider(
        request.provider.value, model=request.model
    )
    try:
        script = await provider.generate_script(
            topic=request.topic, tone=request.tone, max_lines=request.max_lines
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
