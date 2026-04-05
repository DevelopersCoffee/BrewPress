"""WordPress taxonomy tools — tags and categories."""
from __future__ import annotations

from typing import Any

from brewpress.wordpress.client.wp_client import WPClient


def list_tags(client: WPClient, search: str | None = None) -> list[dict[str, Any]]:
    params: dict[str, Any] = {"per_page": 100}
    if search is not None:
        params["search"] = search
    return client.get("tags", params)


def get_or_create_tag(client: WPClient, name: str) -> dict[str, Any]:
    """Search for a tag by name; create it if not found."""
    results = list_tags(client, search=name)
    existing = next(
        (t for t in results if t.get("name", "").lower() == name.lower()), None
    )
    if existing:
        return existing
    return client.post("tags", json={"name": name})


def list_categories(client: WPClient, search: str | None = None) -> list[dict[str, Any]]:
    params: dict[str, Any] = {"per_page": 100}
    if search is not None:
        params["search"] = search
    return client.get("categories", params)


def get_or_create_category(
    client: WPClient, name: str, parent: int | None = None
) -> dict[str, Any]:
    """Search for a category by name; create it if not found."""
    results = list_categories(client, search=name)
    existing = next(
        (c for c in results if c.get("name", "").lower() == name.lower()), None
    )
    if existing:
        return existing
    payload: dict[str, Any] = {"name": name}
    if parent is not None:
        payload["parent"] = parent
    return client.post("categories", json=payload)


def resolve_tags(client: WPClient, names: list[str]) -> list[int]:
    """Resolve tag names to IDs, creating tags that don't exist."""
    return [get_or_create_tag(client, name)["id"] for name in names]


def resolve_categories(client: WPClient, names: list[str]) -> list[int]:
    """Resolve category names to IDs, creating categories that don't exist."""
    return [get_or_create_category(client, name)["id"] for name in names]
