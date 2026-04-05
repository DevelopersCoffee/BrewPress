"""Runtime configuration loaded exclusively from environment variables.

No secrets are read from files tracked by git.
Call load_config() with a `required` tuple specifying which vars the calling
subcommand needs. Only the listed vars are validated; others default to None.

Local development: place a .env file in the project root (git-ignored).
python-dotenv is used to load it automatically — values with spaces (e.g.
WordPress Application Passwords) must be quoted in .env:

    WP_APP_PASSWORD="xxxx xxxx xxxx xxxx xxxx xxxx"
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

_ALL_VARS: tuple[str, ...] = (
    "WP_URL",
    "WP_USERNAME",
    "WP_APP_PASSWORD",
    "GOOGLE_API_KEY",
)


def _load_dotenv() -> None:
    """Load .env from the project root if present, without overriding existing vars."""
    try:
        from dotenv import load_dotenv

        env_path = Path(__file__).resolve().parent.parent.parent / ".env"
        if env_path.exists():
            load_dotenv(env_path, override=False)
    except ImportError:
        pass  # python-dotenv optional; CI/CD injects vars directly


@dataclass(frozen=True)
class BrewPressConfig:
    wp_url: str | None = None
    wp_username: str | None = None
    wp_app_password: str | None = None
    google_api_key: str | None = None


def load_config(
    required: tuple[str, ...] = _ALL_VARS,
) -> BrewPressConfig:
    """Load environment variables, validating only the ones in `required`.

    Automatically loads a .env file from the project root when present so
    that Application Passwords with spaces are handled correctly without
    requiring the caller to manually source the file.

    Args:
        required: Tuple of env var names this subcommand needs. Defaults to
                  all four vars (WP_URL, WP_USERNAME, WP_APP_PASSWORD,
                  GOOGLE_API_KEY).

    Returns:
        BrewPressConfig with non-None values only for vars that were present.
        Fields for vars not in `required` are None even if the env var is set.

    Raises:
        EnvironmentError: If any var listed in `required` is missing or empty.
    """
    _load_dotenv()

    missing = [k for k in required if not os.environ.get(k, "").strip()]
    if missing:
        raise OSError(
            f"Missing required environment variables: {', '.join(missing)}. "
            "Copy .env.example to .env and fill in real values."
        )

    wp_url = os.environ.get("WP_URL", "").strip().rstrip("/") or None
    if wp_url and not wp_url.startswith("https://"):
        print(
            "Warning: WP_URL does not use HTTPS. WordPress credentials will be "
            "transmitted in plaintext. Update WP_URL to https:// before use.",
            file=sys.stderr,
        )

    return BrewPressConfig(
        wp_url=wp_url,
        wp_username=os.environ.get("WP_USERNAME", "").strip() or None,
        wp_app_password=os.environ.get("WP_APP_PASSWORD", "").strip() or None,
        google_api_key=os.environ.get("GOOGLE_API_KEY", "").strip() or None,
    )
