"""Florida portal adapters. Other states return portal-down rather than an empty search."""

from portals.base import PortalResult, PortalRow
from portals.fl_dfs import DfsPortal
from portals.fl_sunbiz import SunbizPortal

__all__ = ["PortalResult", "PortalRow", "DfsPortal", "SunbizPortal", "search_portal"]


def search_portal(kind: str, name: str, *, state: str = "FL", fetcher, base_url: str = "", limit: int = 10) -> PortalResult:
    """Run one Florida adapter. A state without an adapter is portal-down, not an empty search."""
    if (state or "").strip().upper() != "FL":
        return PortalResult(
            status="portal-down",
            executed=False,
            note=f"no portal adapter for {state or 'that state'}",
        )
    if kind == "business":
        return SunbizPortal(base_url).search(fetcher, name, limit=limit)
    if kind == "license":
        return DfsPortal(base_url).search(fetcher, name, limit=limit)
    return PortalResult(status="portal-down", executed=False, note=f"no portal adapter for kind {kind}")
