"""Runtime configuration loaded exclusively from environment variables.

No secrets are read from files tracked by git.
Call load_config() at startup; it raises EnvironmentError on any missing var.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

_REQUIRED: tuple[str, ...] = (
    "WP_URL",
    "WP_USERNAME",
    "WP_APP_PASSWORD",
    "GOOGLE_API_KEY",
)


@dataclass(frozen=True)
class BrewPressConfig:
    wp_url: str
    wp_username: str
    wp_app_password: str
    google_api_key: str


def load_config() -> BrewPressConfig:
    """Load and validate all required environment variables.

    Raises:
        EnvironmentError: If any required variable is missing or empty.
    """
    missing = [k for k in _REQUIRED if not os.environ.get(k, "").strip()]
    if missing:
        raise EnvironmentError(
            f"Missing required environment variables: {', '.join(missing)}. "
            "Copy .env.example to .env and fill in real values."
        )

    return BrewPressConfig(
        wp_url=os.environ["WP_URL"].rstrip("/"),
        wp_username=os.environ["WP_USERNAME"],
        wp_app_password=os.environ["WP_APP_PASSWORD"],
        google_api_key=os.environ["GOOGLE_API_KEY"],
    )
