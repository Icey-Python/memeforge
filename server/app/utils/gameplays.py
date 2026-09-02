"""Gameplay background loop catalog.

Viral-style shorts need a continuous gameplay loop filling the full
vertical frame as background. Drop matching files into
`server/assets/gameplay/` (id.mp4) to make a clip `available`; the render
API only accepts available clips.
"""

from typing import Dict, List, Optional

from app.core import settings
from app.schemas.render_schema import GameplayClip

_CATALOG: List[GameplayClip] = [
    GameplayClip(
        id="minecraft-parkour",
        label="Minecraft Parkour",
        game="Minecraft",
        description="Classic endless parkour jump loop — the meme meta standard.",
    ),
    GameplayClip(
        id="subway-surfers",
        label="Subway Surfers Run",
        game="Subway Surfers",
        description="Endless runner with trains and coins. Satisfying swipes.",
    ),
    GameplayClip(
        id="gta5-stunts",
        label="GTA 5 Stunt Track",
        game="Grand Theft Auto V",
        description="San Andreas stunt jumps and bicycle mega-ramps.",
    ),
    GameplayClip(
        id="satisfactory-belt",
        label="Satisfactory Conveyor Belt",
        game="Satisfactory",
        description="Hypnotic factory conveyor loops. Brain melts pleasantly.",
    ),
    GameplayClip(
        id="rocket-league-aerial",
        label="Rocket League Aerials",
        game="Rocket League",
        description="Ceiling shots and musty flicks on repeat.",
    ),
    GameplayClip(
        id="fortnite-builds",
        label="Fortnite 90s",
        game="Fortnite",
        description="Cranking 90s until the frame rate begs for mercy.",
    ),
]


def list_gameplays() -> List[GameplayClip]:
    """Catalog with resolved source paths (available if the file exists)."""
    out: List[GameplayClip] = []
    for clip in _CATALOG:
        resolved = settings.GAMEPLAY_DIR / f"{clip.id}.mp4"
        available = resolved.exists()
        out.append(
            clip.model_copy(
                update={
                    "source": str(resolved) if available else None,
                    "available": available,
                }
            )
        )
    return out


def get_gameplay(clip_id: str) -> Optional[GameplayClip]:
    for clip in list_gameplays():
        if clip.id == clip_id:
            return clip
    return None
