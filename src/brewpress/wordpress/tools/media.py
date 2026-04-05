"""WordPress media upload tools."""
from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Any

from brewpress.wordpress.client.wp_client import WPClient

_MIME_OVERRIDES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
}


def _infer_content_type(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in _MIME_OVERRIDES:
        return _MIME_OVERRIDES[ext]
    guessed, _ = mimetypes.guess_type(str(path))
    return guessed or "application/octet-stream"


def upload_image(
    client: WPClient,
    path: str | Path,
    filename: str | None = None,
) -> dict[str, Any]:
    """Upload an image file to the WordPress media library.

    Args:
        client:   WPClient instance.
        path:     Local path to the image file.
        filename: Override filename; defaults to the file's name.

    Returns:
        WP media object dict.
    """
    file_path = Path(path)
    name = filename or file_path.name
    content_type = _infer_content_type(file_path)

    with file_path.open("rb") as fh:
        files = {"file": (name, fh, content_type)}
        headers = {"Content-Disposition": f'attachment; filename="{name}"'}
        return client.post("media", files=files, headers=headers)


def get_media(client: WPClient, media_id: int) -> dict[str, Any]:
    return client.get(f"media/{media_id}")


def delete_media(client: WPClient, media_id: int, force: bool = True) -> dict[str, Any]:
    return client.delete(f"media/{media_id}", params={"force": force})
