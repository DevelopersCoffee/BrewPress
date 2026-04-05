"""Tests for WPClient."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import requests

from brewpress.wordpress.client.wp_client import WPClient


def make_client() -> WPClient:
    return WPClient(base_url="https://example.com", auth=("user", "pass word"))


def mock_response(json_data, status_code=200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.raise_for_status.return_value = None
    return resp


class TestWPClientBasicMethods:
    def test_get_returns_parsed_json(self):
        client = make_client()
        with patch.object(client._session, "request") as mock_req:
            mock_req.return_value = mock_response({"id": 1})
            result = client.get("posts/1")
        assert result == {"id": 1}

    def test_post_returns_parsed_json(self):
        client = make_client()
        with patch.object(client._session, "request") as mock_req:
            mock_req.return_value = mock_response({"id": 2})
            result = client.post("posts", json={"title": "Hello"})
        assert result == {"id": 2}

    def test_put_returns_parsed_json(self):
        client = make_client()
        with patch.object(client._session, "request") as mock_req:
            mock_req.return_value = mock_response({"id": 3, "status": "publish"})
            result = client.put("posts/3", json={"status": "publish"})
        assert result == {"id": 3, "status": "publish"}

    def test_delete_returns_parsed_json(self):
        client = make_client()
        with patch.object(client._session, "request") as mock_req:
            mock_req.return_value = mock_response({"deleted": True})
            result = client.delete("posts/3", params={"force": True})
        assert result == {"deleted": True}

    def test_raise_for_status_called(self):
        client = make_client()
        mock_resp = mock_response({"id": 1})
        with patch.object(client._session, "request", return_value=mock_resp):
            client.get("posts/1")
        mock_resp.raise_for_status.assert_called_once()

    def test_single_session_instance(self):
        client = make_client()
        session1 = client._session
        assert client._session is session1


class TestWPClientRetry:
    def test_retry_on_connection_error(self):
        client = make_client()
        success_resp = mock_response({"id": 1})
        with patch.object(client._session, "request") as mock_req, \
             patch("brewpress.wordpress.client.wp_client.time.sleep"):
            mock_req.side_effect = [
                requests.ConnectionError("conn refused"),
                requests.ConnectionError("conn refused"),
                success_resp,
            ]
            result = client.get("posts/1")
        assert result == {"id": 1}
        assert mock_req.call_count == 3

    def test_retry_on_timeout(self):
        client = make_client()
        success_resp = mock_response([{"id": 1}])
        with patch.object(client._session, "request") as mock_req, \
             patch("brewpress.wordpress.client.wp_client.time.sleep"):
            mock_req.side_effect = [
                requests.Timeout("timed out"),
                success_resp,
            ]
            result = client.get("posts")
        assert result == [{"id": 1}]
        assert mock_req.call_count == 2

    def test_raises_after_max_retries(self):
        client = WPClient(base_url="https://example.com", auth=("u", "p"), max_retries=3)
        with patch.object(client._session, "request") as mock_req, \
             patch("brewpress.wordpress.client.wp_client.time.sleep"):
            mock_req.side_effect = requests.ConnectionError("conn refused")
            with pytest.raises(requests.ConnectionError):
                client.get("posts")
        assert mock_req.call_count == 3

    def test_no_retry_on_400(self):
        client = make_client()
        http_err_resp = MagicMock()
        http_err_resp.status_code = 400
        exc = requests.HTTPError(response=http_err_resp)
        with patch.object(client._session, "request") as mock_req:
            mock_req.return_value.raise_for_status.side_effect = exc
            with pytest.raises(requests.HTTPError):
                client.get("posts")
        assert mock_req.call_count == 1

    def test_no_retry_on_401(self):
        client = make_client()
        http_err_resp = MagicMock()
        http_err_resp.status_code = 401
        exc = requests.HTTPError(response=http_err_resp)
        with patch.object(client._session, "request") as mock_req:
            mock_req.return_value.raise_for_status.side_effect = exc
            with pytest.raises(requests.HTTPError):
                client.get("posts")
        assert mock_req.call_count == 1
