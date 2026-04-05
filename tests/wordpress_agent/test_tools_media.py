"""Tests for tools/media.py."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from brewpress.wordpress.tools.media import upload_image


class TestUploadImage:
    def _run_upload(self, filename: str, expected_content_type: str, tmp_path: Path):
        client = MagicMock()
        client.post.return_value = {"id": 99, "source_url": "https://example.com/img"}

        img_path = tmp_path / filename
        img_path.write_bytes(b"fake image data")

        result = upload_image(client, img_path)
        assert result == {"id": 99, "source_url": "https://example.com/img"}

        files_arg = client.post.call_args[1]["files"]
        _, (name, fh, ct) = list(files_arg.items())[0]
        assert ct == expected_content_type
        assert name == filename

    def test_jpg_content_type(self, tmp_path):
        self._run_upload("photo.jpg", "image/jpeg", tmp_path)

    def test_png_content_type(self, tmp_path):
        self._run_upload("image.png", "image/png", tmp_path)

    def test_webp_content_type(self, tmp_path):
        self._run_upload("banner.webp", "image/webp", tmp_path)

    def test_gif_content_type(self, tmp_path):
        self._run_upload("anim.gif", "image/gif", tmp_path)

    def test_custom_filename_override(self, tmp_path):
        client = MagicMock()
        client.post.return_value = {"id": 100}
        img_path = tmp_path / "local.jpg"
        img_path.write_bytes(b"data")

        upload_image(client, img_path, filename="custom_name.jpg")
        files_arg = client.post.call_args[1]["files"]
        name = list(files_arg.values())[0][0]
        assert name == "custom_name.jpg"
