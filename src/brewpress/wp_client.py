"""WordPress REST Client — Application Password auth, draft create/update.

Implements the WordPress Agent layer from the PRD:
    - Application Password auth (no plugin dependency)
    - Create post as draft or publish live
    - Update existing post (idempotent via find_post)
    - Update target resolution: slug → explicit ID → title search
    - Stop on ambiguous title matches; never auto-update multi-match
    - Failure bundle written locally when publish fails

Endpoints used (plugin-independent):
    /wp-json/wp/v2/posts
    /wp-json/wp/v2/tags
    /wp-json/wp/v2/categories

Auth:
    HTTP Basic via WordPress Application Passwords.
    WP_URL must use HTTPS (enforced by BrewPressConfig.load_config).
    Credentials come from BrewPressConfig — never from source code.

ADK integration note: WordPressClient.publish() is the natural ADK Tool
boundary for the WordPress Agent. find_post() can be a separate tool call
to support interactive disambiguation when AmbiguousMatchError is raised.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import markdown
import requests

from brewpress.config import BrewPressConfig
from brewpress.models import BlogJob

# ------------------------------------------------------------------ #
# Exceptions                                                           #
# ------------------------------------------------------------------ #


class AmbiguousMatchError(Exception):
    """Title search returned multiple posts; explicit post ID required.

    Attributes:
        title:   The title that was searched.
        matches: List of WP post dicts that matched.
    """

    def __init__(self, title: str, matches: list[dict[str, Any]]) -> None:
        self.title = title
        self.matches = matches
        ids = ", ".join(str(p.get("id")) for p in matches)
        super().__init__(
            f"Title search for {title!r} returned {len(matches)} matches "
            f"(post IDs: {ids}). "
            "Set target_wp_post_id on the BlogJob to resolve explicitly."
        )


class PublishError(Exception):
    """WP publish or update failed.

    A failure bundle should be generated after catching this error
    so the user can post manually or retry intentionally.
    """


# ------------------------------------------------------------------ #
# Markdown → HTML                                                      #
# ------------------------------------------------------------------ #

_MD_EXTENSIONS = ["fenced_code", "tables", "nl2br"]


def _md_to_html(text: str) -> str:
    """Convert Markdown body text to HTML for the WP REST API content field."""
    return markdown.markdown(text, extensions=_MD_EXTENSIONS)


# ------------------------------------------------------------------ #
# Failure bundle                                                       #
# ------------------------------------------------------------------ #


def generate_failure_bundle(
    job: BlogJob,
    path: Path | None = None,
) -> dict[str, Any]:
    """Build a local failure bundle from a BlogJob.

    The bundle contains everything needed to post manually or retry.
    If ``path`` is provided the bundle is written atomically to that file.

    Bundle schema (PRD §Failure Handling):
        title    — post title
        content  — raw Markdown body (not converted; portable for re-use)
        media    — empty list (Stack 7 will populate)
        seo      — meta_description, slug, excerpt, primary/secondary keywords
    """
    bundle: dict[str, Any] = {
        "title": job.title,
        "content": job.draft_body_md,
        "media": [],
        "seo": {
            "meta_description": job.meta_description,
            "slug": job.slug,
            "excerpt": job.excerpt,
            "primary_keyword": job.primary_keyword,
            "secondary_keywords": job.secondary_keywords,
        },
    }

    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(bundle, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.rename(path)

    return bundle


# ------------------------------------------------------------------ #
# WordPressClient                                                      #
# ------------------------------------------------------------------ #

_TIMEOUT = 30  # seconds


class WordPressClient:
    """WordPress REST API client using Application Password auth.

    Args:
        config: BrewPressConfig with wp_url, wp_username, wp_app_password set.

    Raises:
        ValueError: If any required credential is missing from config.

    Usage:
        config = load_config(required=("WP_URL", "WP_USERNAME", "WP_APP_PASSWORD"))
        client = WordPressClient(config)
        job = client.publish(job)
    """

    def __init__(self, config: BrewPressConfig) -> None:
        missing = [
            name
            for name, val in [
                ("WP_URL", config.wp_url),
                ("WP_USERNAME", config.wp_username),
                ("WP_APP_PASSWORD", config.wp_app_password),
            ]
            if not val
        ]
        if missing:
            raise ValueError(
                f"WordPressClient requires: {', '.join(missing)}. "
                "Set these environment variables before publishing."
            )

        self._base = config.wp_url  # already stripped of trailing slash by load_config
        self._session = requests.Session()
        # Application Passwords: WP strips spaces from the password on verification.
        self._session.auth = (config.wp_username, config.wp_app_password)
        self._session.headers.update({
            "Content-Type": "application/json",
            "Accept": "application/json",
        })

    # ---------------------------------------------------------------- #
    # Low-level HTTP                                                     #
    # ---------------------------------------------------------------- #

    def _url(self, path: str) -> str:
        return f"{self._base}/wp-json/wp/v2/{path}"

    def _get(self, path: str, **params: Any) -> Any:
        resp = self._session.get(self._url(path), params=params, timeout=_TIMEOUT)
        resp.raise_for_status()
        return resp.json()

    def _post(self, path: str, data: dict[str, Any]) -> dict[str, Any]:
        resp = self._session.post(self._url(path), json=data, timeout=_TIMEOUT)
        resp.raise_for_status()
        return resp.json()

    def _put(self, path: str, data: dict[str, Any]) -> dict[str, Any]:
        resp = self._session.put(self._url(path), json=data, timeout=_TIMEOUT)
        resp.raise_for_status()
        return resp.json()

    # ---------------------------------------------------------------- #
    # Taxonomy resolution                                               #
    # ---------------------------------------------------------------- #

    def _resolve_terms(self, names: list[str], taxonomy: str) -> list[int]:
        """Get or create taxonomy term IDs by name.

        Args:
            names:    Human-readable term names (e.g. ["Java", "Backend"]).
            taxonomy: WP taxonomy slug — "tags" or "categories".

        Returns:
            List of WP term IDs in the same order as ``names``.
        """
        ids: list[int] = []
        for name in names:
            # Search for existing term first.
            results: list[dict[str, Any]] = self._get(taxonomy, search=name, per_page=10)
            existing = next(
                (t for t in results if t.get("name", "").lower() == name.lower()),
                None,
            )
            if existing:
                ids.append(existing["id"])
            else:
                created: dict[str, Any] = self._post(taxonomy, {"name": name})
                ids.append(created["id"])
        return ids

    # ---------------------------------------------------------------- #
    # Update target resolution (PRD §Update Logic)                     #
    # ---------------------------------------------------------------- #

    def find_post(self, job: BlogJob) -> int | None:
        """Locate an existing WP post to update.

        Resolution order (PRD §Update Logic):
            1. slug  — exact slug match
            2. post ID — explicit ``target_wp_post_id`` on the job
            3. title search — title substring search; stops on multiple matches

        Returns:
            WP post ID of the match, or None if no post is found.

        Raises:
            AmbiguousMatchError: Title search returned more than one exact match.
        """
        # 1. Slug
        by_slug: list[dict[str, Any]] = self._get("posts", slug=job.slug, status="any")
        if by_slug:
            return int(by_slug[0]["id"])

        # 2. Explicit post ID
        if job.target_wp_post_id is not None:
            try:
                post: dict[str, Any] = self._get(f"posts/{job.target_wp_post_id}")
                return int(post["id"])
            except requests.HTTPError:
                pass  # ID not found — fall through to title search

        # 3. Title search
        if job.title:
            candidates: list[dict[str, Any]] = self._get(
                "posts", search=job.title, status="any", per_page=20
            )
            exact = [
                p for p in candidates
                if p.get("title", {}).get("rendered", "").strip() == job.title.strip()
            ]
            if len(exact) == 1:
                return int(exact[0]["id"])
            if len(exact) > 1:
                raise AmbiguousMatchError(job.title, exact)

        return None

    # ---------------------------------------------------------------- #
    # Payload construction                                              #
    # ---------------------------------------------------------------- #

    def _build_payload(self, job: BlogJob, status: str) -> dict[str, Any]:
        """Build the WP REST API post payload from a BlogJob.

        Uses plugin-independent fields only:
        title, content (HTML), excerpt, slug, status, tags, categories.
        """
        tag_ids = self._resolve_terms(job.tags, "tags") if job.tags else []
        cat_ids = self._resolve_terms(job.categories, "categories") if job.categories else []

        return {
            "title": job.title,
            "content": _md_to_html(job.draft_body_md),
            "excerpt": job.excerpt or job.meta_description,
            "slug": job.slug,
            "status": status,
            "tags": tag_ids,
            "categories": cat_ids,
        }

    # ---------------------------------------------------------------- #
    # Publish                                                           #
    # ---------------------------------------------------------------- #

    def publish(self, job: BlogJob) -> BlogJob:
        """Create or update a WP post from a BlogJob.

        Determines create vs update via find_post().  Sets the post status
        to "publish" when job.publish_live is True, "draft" otherwise.
        Never infers live publish — only acts on job.publish_live.

        Returns:
            Updated BlogJob with wp_post_id set.

        Raises:
            AmbiguousMatchError: Propagated from find_post(); caller must
                                 resolve by setting target_wp_post_id.
            PublishError:        Any network or HTTP error during create/update.
        """
        status = "publish" if job.publish_live else "draft"

        try:
            existing_id = self.find_post(job)
            payload = self._build_payload(job, status)

            if existing_id is not None:
                result = self._put(f"posts/{existing_id}", payload)
            else:
                result = self._post("posts", payload)

        except AmbiguousMatchError:
            raise  # let caller handle disambiguation
        except requests.RequestException as exc:
            raise PublishError(
                f"WordPress API request failed: {exc}. "
                "A failure bundle has been written — "
                "post manually or retry intentionally."
            ) from exc

        return job.model_copy(update={"wp_post_id": int(result["id"])})
