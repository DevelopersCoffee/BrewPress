"""High-level publish workflow."""
from __future__ import annotations

from typing import Any

from brewpress.wordpress.client.wp_client import WPClient
from brewpress.wordpress.tools.media import upload_image
from brewpress.wordpress.tools.posts import create_post, find_by_slug, update_post
from brewpress.wordpress.tools.taxonomy import resolve_categories, resolve_tags


def publish_article(
    client: WPClient,
    title: str,
    content: str,
    status: str = "draft",
    slug: str | None = None,
    excerpt: str | None = None,
    image_path: str | None = None,
    categories: list[str] | None = None,
    tags: list[str] | None = None,
) -> dict[str, Any]:
    """Full publish pipeline.

    Pipeline:
    1. Upload featured image (if image_path provided)
    2. Resolve/create categories (if provided)
    3. Resolve/create tags (if provided)
    4. Check for existing post by slug (find_by_slug) → update if found, create if not
    5. Set featured_media, categories, tags on the post
    6. Return final WP post dict

    On any failure after the post is created, the post remains in its current
    state so the pipeline can be retried without data loss (retryable pattern).
    """
    # Step 1: Upload featured image
    media_id: int | None = None
    if image_path is not None:
        media_obj = upload_image(client, image_path)
        media_id = int(media_obj["id"])

    # Step 2: Resolve categories
    category_ids: list[int] | None = None
    if categories:
        category_ids = resolve_categories(client, categories)

    # Step 3: Resolve tags
    tag_ids: list[int] | None = None
    if tags:
        tag_ids = resolve_tags(client, tags)

    # Step 4: Find existing post by slug or create new
    existing = find_by_slug(client, slug) if slug else None

    if existing is not None:
        fields: dict[str, Any] = {
            "title": title,
            "content": content,
            "status": status,
        }
        if excerpt is not None:
            fields["excerpt"] = excerpt
        if media_id is not None:
            fields["featured_media"] = media_id
        if category_ids is not None:
            fields["categories"] = category_ids
        if tag_ids is not None:
            fields["tags"] = tag_ids
        return update_post(client, int(existing["id"]), **fields)
    else:
        return create_post(
            client,
            title=title,
            content=content,
            status=status,
            slug=slug,
            excerpt=excerpt,
            categories=category_ids,
            tags=tag_ids,
            featured_media=media_id,
        )


def update_post_status(client: WPClient, post_id: int, status: str) -> dict[str, Any]:
    """Transition a post to a new status (draft → publish, etc.)."""
    return update_post(client, post_id, status=status)
