"""Tests for tools/posts.py."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import requests

from brewpress.wordpress.tools.posts import (
    create_post,
    delete_post,
    find_by_slug,
    get_post,
    list_posts,
    update_post,
)


def make_http_error(status_code: int) -> requests.HTTPError:
    resp = MagicMock()
    resp.status_code = status_code
    return requests.HTTPError(response=resp)


def make_client(get_return=None, post_return=None, put_return=None, delete_return=None):
    client = MagicMock()
    if get_return is not None:
        client.get.return_value = get_return
    if post_return is not None:
        client.post.return_value = post_return
    if put_return is not None:
        client.put.return_value = put_return
    if delete_return is not None:
        client.delete.return_value = delete_return
    return client


class TestListPosts:
    def test_list_without_status(self):
        client = make_client(get_return=[{"id": 1}])
        result = list_posts(client, per_page=5)
        assert result == [{"id": 1}]
        client.get.assert_called_once_with("posts", {"per_page": 5, "page": 1})

    def test_list_with_status(self):
        client = make_client(get_return=[{"id": 1}])
        result = list_posts(client, status="publish")
        assert result == [{"id": 1}]
        call_params = client.get.call_args[0][1]
        assert call_params["status"] == "publish"

    def test_list_fallback_on_400_with_status(self):
        client = MagicMock()
        client.get.side_effect = [
            make_http_error(400),
            [{"id": 1}],
        ]
        result = list_posts(client, status="any")
        assert result == [{"id": 1}]
        assert client.get.call_count == 2
        second_call_params = client.get.call_args[0][1]
        assert "status" not in second_call_params

    def test_list_raises_non_400_error(self):
        client = make_client()
        client.get.side_effect = make_http_error(500)
        with pytest.raises(requests.HTTPError):
            list_posts(client)


class TestFindBySlug:
    def test_returns_post_when_found(self):
        client = make_client(get_return=[{"id": 5, "slug": "hello"}])
        result = find_by_slug(client, "hello")
        assert result == {"id": 5, "slug": "hello"}

    def test_returns_none_when_not_found(self):
        client = make_client(get_return=[])
        result = find_by_slug(client, "not-found")
        assert result is None

    def test_fallback_on_400(self):
        client = MagicMock()
        client.get.side_effect = [
            make_http_error(400),
            [{"id": 5, "slug": "hello"}],
        ]
        result = find_by_slug(client, "hello")
        assert result == {"id": 5, "slug": "hello"}
        second_params = client.get.call_args[0][1]
        assert "status" not in second_params

    def test_raises_non_400_error(self):
        client = MagicMock()
        client.get.side_effect = make_http_error(403)
        with pytest.raises(requests.HTTPError):
            find_by_slug(client, "hello")


class TestCreatePost:
    def test_passes_correct_payload(self):
        client = make_client(post_return={"id": 10})
        result = create_post(client, title="Hello", content="<p>World</p>", status="draft")
        assert result == {"id": 10}
        payload = client.post.call_args[1]["json"]
        assert payload["title"] == "Hello"
        assert payload["content"] == "<p>World</p>"
        assert payload["status"] == "draft"

    def test_optional_fields_included_when_provided(self):
        client = make_client(post_return={"id": 11})
        create_post(
            client,
            title="T",
            content="C",
            slug="my-slug",
            excerpt="Short",
            categories=[1, 2],
            tags=[3],
            featured_media=99,
        )
        payload = client.post.call_args[1]["json"]
        assert payload["slug"] == "my-slug"
        assert payload["excerpt"] == "Short"
        assert payload["categories"] == [1, 2]
        assert payload["tags"] == [3]
        assert payload["featured_media"] == 99

    def test_optional_fields_excluded_when_none(self):
        client = make_client(post_return={"id": 12})
        create_post(client, title="T", content="C")
        payload = client.post.call_args[1]["json"]
        assert "slug" not in payload
        assert "featured_media" not in payload


class TestUpdatePost:
    def test_sends_correct_fields(self):
        client = make_client(put_return={"id": 5, "status": "publish"})
        result = update_post(client, 5, status="publish", title="New Title")
        assert result == {"id": 5, "status": "publish"}
        client.put.assert_called_once_with("posts/5", json={"status": "publish", "title": "New Title"})


class TestDeletePost:
    def test_delete_with_force(self):
        client = make_client(delete_return={"deleted": True})
        result = delete_post(client, 5, force=True)
        assert result == {"deleted": True}
        client.delete.assert_called_once_with("posts/5", params={"force": True})
