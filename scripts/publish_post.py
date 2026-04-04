#!/usr/bin/env python3
"""Publish reviewed blog post drafts.

Finds all draft posts in posts/drafts/, updates their front-matter to mark
them as published, moves them to posts/published/, and removes the originals.

Usage:
    Run from the repository root after checking out the branch that contains
    the merged draft(s):
        python scripts/publish_post.py
"""

import re
import sys
from datetime import datetime
from pathlib import Path


def find_draft_posts():
    """Return all markdown draft posts found in posts/drafts/."""
    drafts_dir = Path("posts/drafts")
    if not drafts_dir.exists():
        return []
    return sorted(
        p for p in drafts_dir.glob("*.md") if p.name != ".gitkeep"
    )


def update_front_matter(content, publish_date):
    """Set draft: false and add published_date in YAML front-matter."""
    content = re.sub(
        r"^draft:\s*true",
        "draft: false",
        content,
        flags=re.MULTILINE,
    )
    if "published_date:" not in content:
        content = re.sub(
            r"^(draft:\s*false)",
            rf"\1\npublished_date: {publish_date}",
            content,
            flags=re.MULTILINE,
        )
    return content


def publish_post(draft_path):
    """Move a single draft to posts/published/ and mark it as published."""
    content = draft_path.read_text(encoding="utf-8")
    publish_date = datetime.now().strftime("%Y-%m-%d")
    updated_content = update_front_matter(content, publish_date)

    published_dir = Path("posts/published")
    published_dir.mkdir(parents=True, exist_ok=True)

    published_path = published_dir / draft_path.name
    published_path.write_text(updated_content, encoding="utf-8")
    draft_path.unlink()

    return published_path


def set_output(name, value):
    """Write a value to the GitHub Actions step output file."""
    import os

    github_output = os.environ.get("GITHUB_OUTPUT", "")
    if github_output:
        with open(github_output, "a") as fh:
            fh.write(f"{name}={value}\n")


def main():
    draft_posts = find_draft_posts()

    if not draft_posts:
        print("No draft posts found to publish.")
        sys.exit(0)

    published_paths = []
    for draft_path in draft_posts:
        print(f"Publishing: {draft_path.name}")
        published_path = publish_post(draft_path)
        published_paths.append(published_path)
        print(f"  → Published to: {published_path}")

    print(f"\nSuccessfully published {len(published_paths)} post(s).")

    set_output("published_count", str(len(published_paths)))
    if published_paths:
        set_output("published_path", str(published_paths[0]))


if __name__ == "__main__":
    main()
