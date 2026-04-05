"""Tests for workflows/publish_flow.py."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from brewpress.wordpress.workflows.publish_flow import publish_article, update_post_status


def make_client():
    return MagicMock()


class TestPublishArticleFull:
    def test_full_pipeline_creates_new_post(self, tmp_path):
        client = make_client()
        img = tmp_path / "hero.jpg"
        img.write_bytes(b"img data")

        with patch("brewpress.wordpress.workflows.publish_flow.upload_image") as mock_img, \
             patch("brewpress.wordpress.workflows.publish_flow.resolve_categories") as mock_cats, \
             patch("brewpress.wordpress.workflows.publish_flow.resolve_tags") as mock_tags, \
             patch("brewpress.wordpress.workflows.publish_flow.find_by_slug") as mock_find, \
             patch("brewpress.wordpress.workflows.publish_flow.create_post") as mock_create:
            mock_img.return_value = {"id": 10}
            mock_cats.return_value = [1, 2]
            mock_tags.return_value = [3]
            mock_find.return_value = None
            mock_create.return_value = {"id": 99, "status": "draft"}

            result = publish_article(
                client,
                title="Hello",
                content="<p>World</p>",
                slug="hello-world",
                image_path=str(img),
                categories=["Tech"],
                tags=["Python"],
            )

        assert result == {"id": 99, "status": "draft"}
        mock_img.assert_called_once()
        mock_cats.assert_called_once_with(client, ["Tech"])
        mock_tags.assert_called_once_with(client, ["Python"])
        mock_create.assert_called_once()
        create_kwargs = mock_create.call_args[1]
        assert create_kwargs["featured_media"] == 10
        assert create_kwargs["categories"] == [1, 2]
        assert create_kwargs["tags"] == [3]

    def test_idempotent_updates_existing_post(self):
        client = make_client()
        with patch("brewpress.wordpress.workflows.publish_flow.upload_image") as mock_img, \
             patch("brewpress.wordpress.workflows.publish_flow.find_by_slug") as mock_find, \
             patch("brewpress.wordpress.workflows.publish_flow.update_post") as mock_update, \
             patch("brewpress.wordpress.workflows.publish_flow.resolve_categories") as mock_cats, \
             patch("brewpress.wordpress.workflows.publish_flow.resolve_tags") as mock_tags:
            mock_find.return_value = {"id": 55, "slug": "existing"}
            mock_update.return_value = {"id": 55, "status": "publish"}
            mock_cats.return_value = [1]
            mock_tags.return_value = [2]

            result = publish_article(
                client,
                title="Updated",
                content="<p>New content</p>",
                slug="existing",
                categories=["Tech"],
                tags=["Python"],
            )

        assert result == {"id": 55, "status": "publish"}
        mock_update.assert_called_once()
        mock_img.assert_not_called()

    def test_no_image_skips_upload(self):
        client = make_client()
        with patch("brewpress.wordpress.workflows.publish_flow.upload_image") as mock_img, \
             patch("brewpress.wordpress.workflows.publish_flow.find_by_slug") as mock_find, \
             patch("brewpress.wordpress.workflows.publish_flow.create_post") as mock_create:
            mock_find.return_value = None
            mock_create.return_value = {"id": 1}

            publish_article(client, title="T", content="C", slug="t")

        mock_img.assert_not_called()

    def test_no_categories_tags_skips_taxonomy(self):
        client = make_client()
        with patch("brewpress.wordpress.workflows.publish_flow.resolve_categories") as mock_cats, \
             patch("brewpress.wordpress.workflows.publish_flow.resolve_tags") as mock_tags, \
             patch("brewpress.wordpress.workflows.publish_flow.find_by_slug") as mock_find, \
             patch("brewpress.wordpress.workflows.publish_flow.create_post") as mock_create:
            mock_find.return_value = None
            mock_create.return_value = {"id": 1}

            publish_article(client, title="T", content="C")

        mock_cats.assert_not_called()
        mock_tags.assert_not_called()


class TestUpdatePostStatus:
    def test_updates_status(self):
        client = make_client()
        with patch("brewpress.wordpress.workflows.publish_flow.update_post") as mock_update:
            mock_update.return_value = {"id": 5, "status": "publish"}
            result = update_post_status(client, 5, "publish")
        assert result["status"] == "publish"
        mock_update.assert_called_once_with(client, 5, status="publish")
