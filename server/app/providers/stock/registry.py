"""Stock video provider registry."""

from typing import Dict, List, Optional

from app.providers.stock.base import BaseStockProvider
from app.providers.stock.pexels import PexelsProvider
from app.providers.stock.pixabay import PixabayProvider

_REGISTRY: Dict[str, type] = {
    "pexels": PexelsProvider,
    "pixabay": PixabayProvider,
}


def get_stock_providers(
    api_keys: Optional[Dict[str, str]] = None,
) -> List[BaseStockProvider]:
    """Instantiate every known stock connector.

    `api_keys` carries per-request overrides from the studio UI
    (encrypted browser vault); each provider falls back to the server
    .env key when its override is empty.
    """
    keys = api_keys or {}
    return [
        cls(api_key=keys.get(pid, "")) for pid, cls in _REGISTRY.items()
    ]


def list_stock_providers() -> List[dict]:
    """Catalog payload: which stock connectors exist and are keyed."""
    return [
        {"id": pid, "label": pid.title(), "keyed": cls().is_configured()}
        for pid, cls in _REGISTRY.items()
    ]
