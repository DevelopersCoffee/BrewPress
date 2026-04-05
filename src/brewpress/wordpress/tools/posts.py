"""WordPress post CRUD tools."""
from __future__ import annotations

from typing import Any

import requests

from brewpress.wordpress.client.wp_client import WPClient


def list_posts(
    client: WPClient,
    per_page: int = 10,
    page: int = 1,
    status: str | None = None,
    search: str | None = None,
) -> list[dict[str, Any]]:
    """List posts with optional filters.

    Falls back to no status param if status=any causes a 400 (limited WP roles).
    """
    params: dict[str, Any] = {"per_page": per_page, "page": page}
    if status is not None:
        params["status"] = status
    if search is not None:
        params["search"] = search

    try:
        return client.get("posts", params)
    except requests.HTTPError as exc:
        if exc.response is not None and exc.response.status_code == 400 and status is not None:
            # Role lacks capability for the given status filter — retry without it
            params.pop("status")
            return client.get("posts", params)
        raise


def get_post(client: WPClient, post_id: int) -> dict[str, Any]:
    return client.get(f"posts/{post_id}")


def create_post(
    client: WPClient,
    title: str,
    content: str,
    status: str = "draft",
    slug: str | None = None,
    excerpt: str | None = None,
    categories: list[int] | None = None,
    tags: list[int] | None = None,
    featured_media: int | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "title": title,
        "content": content,
        "status": status,
    }
    if slug is not None:
        payload["slug"] = slug
    if excerpt is not None:
        payload["excerpt"] = excerpt
    if categories is not None:
        payload["categories"] = categories
    if tags is not None:
        payload["tags"] = tags
    if featured_media is not None:
        payload["featured_media"] = featured_media
    return client.post("posts", json=payload)


def update_post(client: WPClient, post_id: int, **fields: Any) -> dict[str, Any]:
    return client.put(f"posts/{post_id}", json=fields)


def delete_post(client: WPClient, post_id: int, force: bool = True) -> dict[str, Any]:
    return client.delete(f"posts/{post_id}", params={"force": force})


def find_by_slug(client: WPClient, slug: str) -> dict[str, Any] | None:
    """Find a post by slug. Tries status=any first; falls back on 400."""
    try:
        results = client.get("posts", {"slug": slug, "status": "any"})
    except requests.HTTPError as exc:
        if exc.response is not None and exc.response.status_code == 400:
            results = client.get("posts", {"slug": slug})
        else:
            raise
    return results[0] if results else None
