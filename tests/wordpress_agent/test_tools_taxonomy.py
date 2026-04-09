"""Tests for tools/taxonomy.py."""
from __future__ import annotations

from unittest.mock import MagicMock

from brewpress.wordpress.tools.taxonomy import (
    get_or_create_category,
    get_or_create_tag,
    resolve_tags,
)


def make_client():
    return MagicMock()


class TestGetOrCreateTag:
    def test_returns_existing_tag(self):
        client = make_client()
        client.get.return_value = [{"id": 1, "name": "Python"}]
        result = get_or_create_tag(client, "Python")
        assert result == {"id": 1, "name": "Python"}
        client.post.assert_not_called()

    def test_creates_when_not_found(self):
        client = make_client()
        client.get.return_value = []
        client.post.return_value = {"id": 5, "name": "NewTag"}
        result = get_or_create_tag(client, "NewTag")
        assert result == {"id": 5, "name": "NewTag"}
        client.post.assert_called_once_with("tags", json={"name": "NewTag"})

    def test_case_insensitive_match(self):
        client = make_client()
        client.get.return_value = [{"id": 2, "name": "python"}]
        result = get_or_create_tag(client, "Python")
        assert result["id"] == 2
        client.post.assert_not_called()


class TestGetOrCreateCategory:
    def test_returns_existing_category(self):
        client = make_client()
        client.get.return_value = [{"id": 3, "name": "Tech"}]
        result = get_or_create_category(client, "Tech")
        assert result["id"] == 3
        client.post.assert_not_called()

    def test_creates_with_parent(self):
        client = make_client()
        client.get.return_value = []
        client.post.return_value = {"id": 10, "name": "Sub", "parent": 3}
        get_or_create_category(client, "Sub", parent=3)
        payload = client.post.call_args[1]["json"]
        assert payload["parent"] == 3


class TestResolveTags:
    def test_returns_list_of_ids(self):
        client = make_client()
        client.get.side_effect = [
            [{"id": 1, "name": "Python"}],
            [],
        ]
        client.post.return_value = {"id": 7, "name": "Django"}
        result = resolve_tags(client, ["Python", "Django"])
        assert result == [1, 7]
