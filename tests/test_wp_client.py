"""Tests for brewpress.wp_client — WordPress REST client, update-target
resolution, failure bundle generation, and markdown conversion."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests

from brewpress.config import BrewPressConfig
from brewpress.models import BlogJob
from brewpress.wp_client import (
    AmbiguousMatchError,
    PublishError,
    WordPressClient,
    _md_to_html,
    generate_failure_bundle,
)

# ------------------------------------------------------------------ #
# Helpers                                                              #
# ------------------------------------------------------------------ #


def _config() -> BrewPressConfig:
    return BrewPressConfig(
        wp_url="https://example.com",
        wp_username="admin",
        wp_app_password="YOUR_WP_APP_PASSWORD",
    )


def _job(**overrides: object) -> BlogJob:
    base: dict = {
        "title": "Java 21 Virtual Threads",
        "slug": "java-21-virtual-threads",
        "meta_description": "A practical guide to virtual threads.",
        "excerpt": "Virtual threads simplify Java concurrency.",
        "primary_keyword": "Java 21 virtual threads",
        "secondary_keywords": ["project loom", "jdk 21", "java concurrency"],
        "tags": ["java", "concurrency"],
        "categories": ["Backend"],
        "draft_body_md": "## Intro\n\nVirtual threads are lightweight.",
    }
    base.update(overrides)
    return BlogJob(**base)


def _wp_post(post_id: int = 42, slug: str = "java-21-virtual-threads",
             title: str = "Java 21 Virtual Threads") -> dict:
    return {
        "id": post_id,
        "slug": slug,
        "title": {"rendered": title},
        "status": "draft",
        "link": f"https://example.com/{slug}",
    }


def _wp_term(term_id: int, name: str, slug: str | None = None) -> dict:
    return {"id": term_id, "name": name, "slug": slug or name.lower()}


def _mock_session(get_map: dict | None = None, post_result: dict | None = None,
                  put_result: dict | None = None) -> MagicMock:
    """Build a mocked requests.Session."""
    session = MagicMock()

    def _make_resp(data: object, status_code: int = 200) -> MagicMock:
        resp = MagicMock()
        resp.status_code = status_code
        resp.json.return_value = data
        resp.raise_for_status.return_value = None
        return resp

    get_map = get_map or {}

    def _get(url: str, params: dict | None = None, **_kw: object) -> MagicMock:
        path = url.split("/wp-json/wp/v2/")[-1].split("?")[0]
        p = params or {}
        if "slug" in p:
            return _make_resp(get_map.get(("slug", p["slug"]), []))
        if "search" in p:
            return _make_resp(get_map.get(("search", p["search"]), []))
        # bare GET posts/{id}
        return _make_resp(get_map.get(path, {}))

    session.get.side_effect = _get

    if post_result is not None:
        session.post.return_value = _make_resp(post_result)
    if put_result is not None:
        session.put.return_value = _make_resp(put_result)

    return session


def _client_with_session(session: MagicMock) -> WordPressClient:
    client = object.__new__(WordPressClient)
    client._base = "https://example.com"
    client._session = session
    return client


# ------------------------------------------------------------------ #
# _md_to_html                                                          #
# ------------------------------------------------------------------ #


def test_md_to_html_heading() -> None:
    assert "<h2>" in _md_to_html("## Hello")


def test_md_to_html_paragraph() -> None:
    assert "<p>" in _md_to_html("Some text here.")


def test_md_to_html_fenced_code_block() -> None:
    md = "```java\nSystem.out.println(\"hi\");\n```"
    html = _md_to_html(md)
    assert "<code" in html


def test_md_to_html_empty_string() -> None:
    assert _md_to_html("") == ""


# ------------------------------------------------------------------ #
# generate_failure_bundle                                              #
# ------------------------------------------------------------------ #


def test_failure_bundle_contains_title() -> None:
    bundle = generate_failure_bundle(_job())
    assert bundle["title"] == "Java 21 Virtual Threads"


def test_failure_bundle_contains_content() -> None:
    bundle = generate_failure_bundle(_job())
    assert "Virtual threads" in bundle["content"]


def test_failure_bundle_media_is_empty_list() -> None:
    bundle = generate_failure_bundle(_job())
    assert bundle["media"] == []


def test_failure_bundle_seo_meta_description() -> None:
    bundle = generate_failure_bundle(_job())
    assert bundle["seo"]["meta_description"] == "A practical guide to virtual threads."


def test_failure_bundle_seo_slug() -> None:
    bundle = generate_failure_bundle(_job())
    assert bundle["seo"]["slug"] == "java-21-virtual-threads"


def test_failure_bundle_seo_excerpt() -> None:
    bundle = generate_failure_bundle(_job())
    assert bundle["seo"]["excerpt"] == "Virtual threads simplify Java concurrency."


def test_failure_bundle_seo_keywords() -> None:
    bundle = generate_failure_bundle(_job())
    assert bundle["seo"]["primary_keyword"] == "Java 21 virtual threads"
    assert "jdk 21" in bundle["seo"]["secondary_keywords"]


def test_failure_bundle_written_to_file(tmp_path: Path) -> None:
    dest = tmp_path / "bundle.json"
    generate_failure_bundle(_job(), path=dest)
    assert dest.exists()
    data = json.loads(dest.read_text())
    assert data["title"] == "Java 21 Virtual Threads"


def test_failure_bundle_write_creates_parent_dirs(tmp_path: Path) -> None:
    dest = tmp_path / "nested" / "dir" / "bundle.json"
    generate_failure_bundle(_job(), path=dest)
    assert dest.exists()


def test_failure_bundle_write_is_valid_json(tmp_path: Path) -> None:
    dest = tmp_path / "bundle.json"
    generate_failure_bundle(_job(), path=dest)
    json.loads(dest.read_text())  # must not raise


def test_failure_bundle_no_path_returns_dict() -> None:
    result = generate_failure_bundle(_job())
    assert isinstance(result, dict)


# ------------------------------------------------------------------ #
# WordPressClient — constructor                                         #
# ------------------------------------------------------------------ #


def test_client_raises_missing_url() -> None:
    config = BrewPressConfig(wp_username="admin", wp_app_password="pass")
    with pytest.raises(ValueError, match="WP_URL"):
        WordPressClient(config)


def test_client_raises_missing_username() -> None:
    config = BrewPressConfig(wp_url="https://example.com", wp_app_password="pass")
    with pytest.raises(ValueError, match="WP_USERNAME"):
        WordPressClient(config)


def test_client_raises_missing_password() -> None:
    config = BrewPressConfig(wp_url="https://example.com", wp_username="admin")
    with pytest.raises(ValueError, match="WP_APP_PASSWORD"):
        WordPressClient(config)


def test_client_sets_auth_on_session() -> None:
    with patch("brewpress.wp_client.requests.Session") as MockSession:
        mock_session = MagicMock()
        MockSession.return_value = mock_session
        WordPressClient(_config())
        assert mock_session.auth == ("admin", "YOUR_WP_APP_PASSWORD")


# ------------------------------------------------------------------ #
# find_post — slug resolution (priority 1)                            #
# ------------------------------------------------------------------ #


def test_find_post_by_slug_returns_id() -> None:
    session = _mock_session(get_map={("slug", "java-21-virtual-threads"): [_wp_post(42)]})
    client = _client_with_session(session)
    assert client.find_post(_job()) == 42


def test_find_post_by_slug_does_not_fall_through_to_id_search() -> None:
    session = _mock_session(get_map={("slug", "java-21-virtual-threads"): [_wp_post(42)]})
    client = _client_with_session(session)
    client.find_post(_job(target_wp_post_id=99))
    # ID path not called — only slug GET was needed
    slug_calls = [
        c for c in session.get.call_args_list
        if "slug" in str(c)
    ]
    assert len(slug_calls) == 1


# ------------------------------------------------------------------ #
# find_post — explicit post ID (priority 2)                           #
# ------------------------------------------------------------------ #


def test_find_post_by_explicit_id_when_slug_misses() -> None:
    session = _mock_session(get_map={
        ("slug", "java-21-virtual-threads"): [],
        "posts/99": _wp_post(99),
    })
    client = _client_with_session(session)
    assert client.find_post(_job(target_wp_post_id=99)) == 99


def test_find_post_explicit_id_falls_through_on_404() -> None:
    session = MagicMock()
    not_found = MagicMock()
    not_found.raise_for_status.side_effect = requests.HTTPError("404")

    def _get(url: str, params: dict | None = None, **_kw: object) -> MagicMock:
        if "posts/99" in url:
            return not_found
        resp = MagicMock()
        resp.json.return_value = []
        resp.raise_for_status.return_value = None
        return resp

    session.get.side_effect = _get
    client = _client_with_session(session)
    # No title → returns None after ID miss
    result = client.find_post(_job(target_wp_post_id=99, title=""))
    assert result is None


# ------------------------------------------------------------------ #
# find_post — title search (priority 3)                               #
# ------------------------------------------------------------------ #


def test_find_post_by_title_search_single_match() -> None:
    post = _wp_post(77, title="Java 21 Virtual Threads")
    session = _mock_session(get_map={
        ("slug", "java-21-virtual-threads"): [],
        ("search", "Java 21 Virtual Threads"): [post],
    })
    client = _client_with_session(session)
    assert client.find_post(_job()) == 77


def test_find_post_title_search_no_match_returns_none() -> None:
    session = _mock_session(get_map={
        ("slug", "java-21-virtual-threads"): [],
        ("search", "Java 21 Virtual Threads"): [],
    })
    client = _client_with_session(session)
    assert client.find_post(_job()) is None


def test_find_post_title_search_ambiguous_raises() -> None:
    posts = [
        _wp_post(1, title="Java 21 Virtual Threads"),
        _wp_post(2, title="Java 21 Virtual Threads"),
    ]
    session = _mock_session(get_map={
        ("slug", "java-21-virtual-threads"): [],
        ("search", "Java 21 Virtual Threads"): posts,
    })
    client = _client_with_session(session)
    with pytest.raises(AmbiguousMatchError) as exc_info:
        client.find_post(_job())
    assert exc_info.value.title == "Java 21 Virtual Threads"
    assert len(exc_info.value.matches) == 2


def test_find_post_title_search_skips_partial_title_matches() -> None:
    """Posts where title contains but does not equal the search term are ignored."""
    partial = _wp_post(1, title="Java 21 Virtual Threads: Deep Dive")
    session = _mock_session(get_map={
        ("slug", "java-21-virtual-threads"): [],
        ("search", "Java 21 Virtual Threads"): [partial],
    })
    client = _client_with_session(session)
    assert client.find_post(_job()) is None


def test_find_post_returns_none_when_no_title() -> None:
    session = _mock_session(get_map={("slug", "my-slug"): []})
    client = _client_with_session(session)
    assert client.find_post(_job(title="", slug="my-slug")) is None


# ------------------------------------------------------------------ #
# publish — create new post                                            #
# ------------------------------------------------------------------ #


def _patched_client_for_publish(
    session: MagicMock,
) -> WordPressClient:
    """Client with _resolve_terms stubbed to return empty lists."""
    client = _client_with_session(session)
    client._resolve_terms = MagicMock(return_value=[])  # type: ignore[method-assign]
    return client


def test_publish_creates_post_when_none_exists() -> None:
    new_post = _wp_post(55)
    session = _mock_session(
        get_map={("slug", "java-21-virtual-threads"): []},
        post_result=new_post,
    )
    # Title search also returns nothing
    session.get.side_effect = None
    session.get.return_value = MagicMock(
        json=MagicMock(return_value=[]),
        raise_for_status=MagicMock(return_value=None),
    )
    session.post.return_value = MagicMock(
        json=MagicMock(return_value=new_post),
        raise_for_status=MagicMock(return_value=None),
    )
    client = _patched_client_for_publish(session)
    client.find_post = MagicMock(return_value=None)  # type: ignore[method-assign]

    updated_job = client.publish(_job())
    assert updated_job.wp_post_id == 55


def test_publish_updates_post_when_found() -> None:
    existing = _wp_post(42)
    session = MagicMock()
    session.put.return_value = MagicMock(
        json=MagicMock(return_value=existing),
        raise_for_status=MagicMock(return_value=None),
    )
    client = _patched_client_for_publish(session)
    client.find_post = MagicMock(return_value=42)  # type: ignore[method-assign]

    updated_job = client.publish(_job())
    assert updated_job.wp_post_id == 42
    session.put.assert_called_once()


def test_publish_sends_draft_status_by_default() -> None:
    new_post = _wp_post(10)
    session = MagicMock()
    session.post.return_value = MagicMock(
        json=MagicMock(return_value=new_post),
        raise_for_status=MagicMock(return_value=None),
    )
    client = _patched_client_for_publish(session)
    client.find_post = MagicMock(return_value=None)  # type: ignore[method-assign]

    client.publish(_job())
    payload = session.post.call_args[1]["json"]
    assert payload["status"] == "draft"


def test_publish_sends_publish_status_when_live() -> None:
    new_post = _wp_post(10)
    session = MagicMock()
    session.post.return_value = MagicMock(
        json=MagicMock(return_value=new_post),
        raise_for_status=MagicMock(return_value=None),
    )
    client = _patched_client_for_publish(session)
    client.find_post = MagicMock(return_value=None)  # type: ignore[method-assign]

    live_job = _job().mark_reviewed().approve_content().approve_publish(live=True)
    client.publish(live_job)
    payload = session.post.call_args[1]["json"]
    assert payload["status"] == "publish"


def test_publish_never_infers_live() -> None:
    """A job without approve_publish(live=True) must always go as draft."""
    new_post = _wp_post(10)
    session = MagicMock()
    session.post.return_value = MagicMock(
        json=MagicMock(return_value=new_post),
        raise_for_status=MagicMock(return_value=None),
    )
    client = _patched_client_for_publish(session)
    client.find_post = MagicMock(return_value=None)  # type: ignore[method-assign]

    # Even if the job is in APPROVED_STEP_2, without live=True it stays draft.
    approved_job = _job().mark_reviewed().approve_content().approve_publish(live=False)
    client.publish(approved_job)
    payload = session.post.call_args[1]["json"]
    assert payload["status"] == "draft"


def test_publish_returns_updated_job_with_wp_post_id() -> None:
    new_post = _wp_post(99)
    session = MagicMock()
    session.post.return_value = MagicMock(
        json=MagicMock(return_value=new_post),
        raise_for_status=MagicMock(return_value=None),
    )
    client = _patched_client_for_publish(session)
    client.find_post = MagicMock(return_value=None)  # type: ignore[method-assign]

    result = client.publish(_job())
    assert result.wp_post_id == 99


def test_publish_raises_publish_error_on_request_failure() -> None:
    session = MagicMock()
    session.post.side_effect = requests.ConnectionError("timeout")
    client = _patched_client_for_publish(session)
    client.find_post = MagicMock(return_value=None)  # type: ignore[method-assign]

    with pytest.raises(PublishError):
        client.publish(_job())


def test_publish_propagates_ambiguous_match_error() -> None:
    session = MagicMock()
    client = _patched_client_for_publish(session)
    client.find_post = MagicMock(  # type: ignore[method-assign]
        side_effect=AmbiguousMatchError("Java 21 Virtual Threads", [_wp_post(1), _wp_post(2)])
    )

    with pytest.raises(AmbiguousMatchError):
        client.publish(_job())


def test_publish_payload_contains_html_content() -> None:
    new_post = _wp_post(10)
    session = MagicMock()
    session.post.return_value = MagicMock(
        json=MagicMock(return_value=new_post),
        raise_for_status=MagicMock(return_value=None),
    )
    client = _patched_client_for_publish(session)
    client.find_post = MagicMock(return_value=None)  # type: ignore[method-assign]

    client.publish(_job())
    payload = session.post.call_args[1]["json"]
    # Markdown body should have been converted to HTML
    assert "<" in payload["content"]


def test_publish_payload_contains_slug() -> None:
    new_post = _wp_post(10)
    session = MagicMock()
    session.post.return_value = MagicMock(
        json=MagicMock(return_value=new_post),
        raise_for_status=MagicMock(return_value=None),
    )
    client = _patched_client_for_publish(session)
    client.find_post = MagicMock(return_value=None)  # type: ignore[method-assign]

    client.publish(_job())
    payload = session.post.call_args[1]["json"]
    assert payload["slug"] == "java-21-virtual-threads"


# ------------------------------------------------------------------ #
# AmbiguousMatchError                                                  #
# ------------------------------------------------------------------ #


def test_ambiguous_match_error_message_contains_count() -> None:
    err = AmbiguousMatchError("My Title", [_wp_post(1), _wp_post(2)])
    assert "2" in str(err)


def test_ambiguous_match_error_message_contains_title() -> None:
    err = AmbiguousMatchError("My Title", [_wp_post(1)])
    assert "My Title" in str(err)


def test_ambiguous_match_error_attributes() -> None:
    matches = [_wp_post(1), _wp_post(2)]
    err = AmbiguousMatchError("My Title", matches)
    assert err.title == "My Title"
    assert err.matches is matches


# ------------------------------------------------------------------ #
# BlogJob fields (tags / categories / excerpt propagated)             #
# ------------------------------------------------------------------ #


def test_blog_job_has_tags_field() -> None:
    job = _job(tags=["java", "spring"])
    assert job.tags == ["java", "spring"]


def test_blog_job_has_categories_field() -> None:
    job = _job(categories=["Backend"])
    assert job.categories == ["Backend"]


def test_blog_job_has_excerpt_field() -> None:
    job = _job(excerpt="Short teaser.")
    assert job.excerpt == "Short teaser."


def test_blog_job_tags_default_empty() -> None:
    assert BlogJob().tags == []


def test_blog_job_categories_default_empty() -> None:
    assert BlogJob().categories == []


def test_blog_job_excerpt_default_empty() -> None:
    assert BlogJob().excerpt == ""
