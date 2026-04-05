"""WordPress user tools."""
from __future__ import annotations

from typing import Any

from brewpress.wordpress.client.wp_client import WPClient


def get_current_user(client: WPClient) -> dict[str, Any]:
    return client.get("users/me", {"context": "edit"})


def list_users(client: WPClient, per_page: int = 10) -> list[dict[str, Any]]:
    return client.get("users", {"per_page": per_page})
