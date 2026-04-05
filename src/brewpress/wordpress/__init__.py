"""WordPress subpackage for BrewPress.

Public API:
    WordPressAgent  — task router (publish/update/delete/list/get)
    WPClient        — low-level HTTP client
    publish_article — full publish pipeline workflow
"""
from __future__ import annotations

from brewpress.wordpress.agent import WordPressAgent
from brewpress.wordpress.client.wp_client import WPClient
from brewpress.wordpress.workflows.publish_flow import publish_article

__all__ = ["WordPressAgent", "WPClient", "publish_article"]
