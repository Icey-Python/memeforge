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
    pexels_api_key: Optional[str] = None,
    pixabay_api_key: Optional[str] = None,
) -> List[BaseStockProvider]:
    """Instantiate every known stock connector.

    Client-supplied keys (studio key vault) take priority over the server
    .env defaults; blank client keys fall back to settings.
    """
    overrides = {"pexels": pexels_api_key, "pixabay": pixabay_api_key}
    return [
        cls(api_key=(overrides.get(pid) or ""))  # blank → settings fallback
        for pid, cls in _REGISTRY.items()
    ]


def list_stock_providers(
    pexels_api_key: Optional[str] = None,
    pixabay_api_key: Optional[str] = None,
) -> List[dict]:
    """Catalog payload: which stock connectors exist and are keyed."""
    return [
        {
            "id": pid,
            "label": pid.title(),
            "keyed": provider.is_configured(),
        }
        for pid, provider in zip(
            _REGISTRY,
            get_stock_providers(pexels_api_key, pixabay_api_key),
        )
    ]
