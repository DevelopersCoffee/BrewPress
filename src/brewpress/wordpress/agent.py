"""WordPressAgent — task router. No business logic here."""
from __future__ import annotations

from typing import Any

from brewpress.config import BrewPressConfig, load_config
from brewpress.wordpress.client.wp_client import WPClient
from brewpress.wordpress.tools.posts import delete_post, get_post, list_posts, update_post
from brewpress.wordpress.workflows.publish_flow import publish_article


class WordPressAgent:
    """Router-only agent. Dispatches tasks to tools and workflows.

    Supported task types:
      - "publish" → publish_article workflow
      - "update"  → update_post tool
      - "delete"  → delete_post tool
      - "list"    → list_posts tool
      - "get"     → get_post tool

    Args:
        client: Optional WPClient. If not provided, one is created from config.
    """

    def __init__(
        self,
        client: WPClient | None = None,
        config: BrewPressConfig | None = None,
    ) -> None:
        if client is not None:
            self._client = client
        else:
            cfg = config or load_config(required=("WP_URL", "WP_USERNAME", "WP_APP_PASSWORD"))
            if not cfg.wp_url or not cfg.wp_username or not cfg.wp_app_password:
                raise ValueError(
                    "WordPressAgent requires WP_URL, WP_USERNAME, and WP_APP_PASSWORD "
                    "in environment or .env file."
                )
            self._client = WPClient(
                base_url=cfg.wp_url,
                auth=(cfg.wp_username, cfg.wp_app_password),
            )

    def run(self, task: dict[str, Any]) -> dict[str, Any] | list[dict[str, Any]]:
        """Dispatch a task by its type field.

        Args:
            task: Dict with "type" key and task-specific kwargs.

        Returns:
            Result from the dispatched tool/workflow.

        Raises:
            ValueError: For unknown task types.
        """
        task_type = task.get("type")
        params = {k: v for k, v in task.items() if k != "type"}

        if task_type == "publish":
            return publish_article(self._client, **params)
        elif task_type == "update":
            post_id = params.pop("post_id")
            return update_post(self._client, post_id, **params)
        elif task_type == "delete":
            post_id = params.pop("post_id")
            force = params.get("force", True)
            return delete_post(self._client, post_id, force=force)
        elif task_type == "list":
            return list_posts(self._client, **params)
        elif task_type == "get":
            return get_post(self._client, params["post_id"])
        else:
            raise ValueError(
                f"Unknown task type: {task_type!r}. "
                "Supported types: publish, update, delete, list, get"
            )
