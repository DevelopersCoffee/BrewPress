"""Tests for WordPressAgent."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from brewpress.wordpress.agent import WordPressAgent


def make_agent():
    client = MagicMock()
    return WordPressAgent(client=client), client


class TestWordPressAgentDispatch:
    def test_publish_calls_publish_article(self):
        agent, client = make_agent()
        with patch("brewpress.wordpress.agent.publish_article") as mock_pub:
            mock_pub.return_value = {"id": 1}
            result = agent.run({"type": "publish", "title": "T", "content": "C"})
        mock_pub.assert_called_once_with(client, title="T", content="C")
        assert result == {"id": 1}

    def test_list_calls_list_posts(self):
        agent, client = make_agent()
        with patch("brewpress.wordpress.agent.list_posts") as mock_list:
            mock_list.return_value = [{"id": 1}]
            result = agent.run({"type": "list", "per_page": 5})
        mock_list.assert_called_once_with(client, per_page=5)
        assert result == [{"id": 1}]

    def test_get_calls_get_post(self):
        agent, client = make_agent()
        with patch("brewpress.wordpress.agent.get_post") as mock_get:
            mock_get.return_value = {"id": 42}
            result = agent.run({"type": "get", "post_id": 42})
        mock_get.assert_called_once_with(client, 42)

    def test_update_calls_update_post(self):
        agent, client = make_agent()
        with patch("brewpress.wordpress.agent.update_post") as mock_update:
            mock_update.return_value = {"id": 5}
            result = agent.run({"type": "update", "post_id": 5, "status": "publish"})
        mock_update.assert_called_once_with(client, 5, status="publish")

    def test_delete_calls_delete_post(self):
        agent, client = make_agent()
        with patch("brewpress.wordpress.agent.delete_post") as mock_delete:
            mock_delete.return_value = {"deleted": True}
            result = agent.run({"type": "delete", "post_id": 5})
        mock_delete.assert_called_once_with(client, 5, force=True)

    def test_unknown_type_raises_value_error(self):
        agent, _ = make_agent()
        with pytest.raises(ValueError, match="Unknown task type"):
            agent.run({"type": "unknown"})
