"""Stock video provider registry."""

from typing import Dict, List

from app.providers.stock.base import BaseStockProvider
from app.providers.stock.pexels import PexelsProvider
from app.providers.stock.pixabay import PixabayProvider

_REGISTRY: Dict[str, type] = {
    "pexels": PexelsProvider,
    "pixabay": PixabayProvider,
}


def get_stock_providers() -> List[BaseStockProvider]:
    """Instantiate every known stock connector (keys come from settings)."""
    return [cls() for cls in _REGISTRY.values()]


def list_stock_providers() -> List[dict]:
    """Catalog payload: which stock connectors exist and are keyed."""
    return [
        {"id": pid, "label": pid.title(), "keyed": cls().is_configured()}
        for pid, cls in _REGISTRY.items()
    ]
