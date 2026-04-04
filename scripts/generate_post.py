#!/usr/bin/env python3
"""Generate a blog post draft from a GitHub PR using AI.

Usage:
    Set the following environment variables and run:
        GITHUB_TOKEN   - GitHub token for API access (required)
        PR_NUMBER      - Pull request number to generate a post from (required)
        SOURCE_REPO    - Repository containing the PR, e.g. "owner/repo" (required)
        OPENAI_API_KEY - OpenAI API key (optional, falls back to GitHub Models)
        GITHUB_MODELS_TOKEN - GitHub Models token (optional fallback)
        AI_MODEL       - Model name to use (default: gpt-4o)
"""

import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

try:
    from openai import OpenAI
except ImportError:
    print("Error: openai package not installed. Run: pip install openai")
    sys.exit(1)

try:
    from github import Github, GithubException
except ImportError:
    print("Error: PyGithub package not installed. Run: pip install PyGithub")
    sys.exit(1)


BLOG_POST_PROMPT = """You are a technical blog writer for DevelopersCoffee, an engaging developer community blog.

Write an insightful technical blog post about the following engineering work:

## PR Information
- **Title**: {title}
- **Author**: {author}
- **Repository**: {repo}
- **PR Number**: #{number}

## PR Description
{body}

## Files Changed ({file_count} files)
{files_summary}

## Commits ({commit_count} commits)
{commits_summary}

## Writing Instructions
Write a blog post that:
1. Has an engaging, informative title (can differ from the PR title)
2. Opens with a hook that explains the problem or motivation
3. Describes what was built/fixed and why it matters to developers
4. Includes relevant technical details about the approach and implementation
5. Highlights interesting challenges or design decisions
6. Closes with the impact and what developers can learn from this work
7. Is 600-1000 words, written for a technical audience
8. Uses proper markdown with headers and code examples where relevant

## Required Format
Respond with exactly this structure:
TITLE: <engaging blog post title>
TAGS: <comma-separated relevant tags, e.g., python, api, performance>
SUMMARY: <one sentence meta description for SEO, max 160 chars>
---
<complete blog post content in markdown, starting with the introduction paragraph (no H1 title)>
"""


def get_pr_details(g, repo_name, pr_number):
    """Fetch comprehensive PR details from the GitHub API."""
    repo = g.get_repo(repo_name)
    pr = repo.get_pull(int(pr_number))

    commits = list(pr.get_commits())
    files = list(pr.get_files())

    files_summary = "\n".join(
        f"- `{f.filename}` (+{f.additions}/-{f.deletions})"
        for f in files[:25]
    )
    if len(files) > 25:
        files_summary += f"\n- ... and {len(files) - 25} more files"

    commits_summary = "\n".join(
        f"- {c.sha[:7]}: {c.commit.message.splitlines()[0]}"
        for c in commits[:15]
    )
    if len(commits) > 15:
        commits_summary += f"\n- ... and {len(commits) - 15} more commits"

    return {
        "number": pr.number,
        "title": pr.title,
        "body": pr.body or "(No description provided)",
        "author": pr.user.login,
        "repo": repo_name,
        "file_count": len(files),
        "commit_count": len(commits),
        "files_summary": files_summary or "(No files changed)",
        "commits_summary": commits_summary or "(No commits)",
        "labels": [label.name for label in pr.labels],
    }


def create_openai_client():
    """Create an OpenAI client using the first available API credential."""
    if os.environ.get("OPENAI_API_KEY"):
        return OpenAI(api_key=os.environ["OPENAI_API_KEY"])

    token = os.environ.get("GITHUB_MODELS_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token:
        return OpenAI(
            api_key=token,
            base_url="https://models.inference.ai.azure.com",
        )

    raise ValueError(
        "No AI API key found. Set OPENAI_API_KEY or GITHUB_MODELS_TOKEN."
    )


def generate_blog_post(pr_details, model):
    """Call the AI model to generate a blog post from PR details."""
    client = create_openai_client()
    prompt = BLOG_POST_PROMPT.format(**pr_details)

    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
        max_tokens=2000,
    )

    return response.choices[0].message.content


def parse_response(raw_content, pr_details):
    """Parse the AI response and produce a formatted markdown post."""
    title = pr_details["title"]
    tags = ["engineering", "development"]
    summary = ""
    content = raw_content

    parts = raw_content.split("---", 1)
    if len(parts) == 2:
        header_section, content = parts
        for line in header_section.strip().splitlines():
            if line.startswith("TITLE:"):
                title = line.replace("TITLE:", "").strip()
            elif line.startswith("TAGS:"):
                raw_tags = line.replace("TAGS:", "").strip()
                tags = [t.strip() for t in raw_tags.split(",") if t.strip()]
            elif line.startswith("SUMMARY:"):
                summary = line.replace("SUMMARY:", "").strip()

    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:60]
    date_str = datetime.now().strftime("%Y-%m-%d")
    filename = f"{date_str}-{slug}.md"

    safe_title = title.replace('"', "'")
    safe_summary = summary.replace('"', "'")
    tags_yaml = json.dumps(tags)

    front_matter = (
        f"---\n"
        f'title: "{safe_title}"\n'
        f"date: {date_str}\n"
        f'author: "{pr_details["author"]}"\n'
        f"tags: {tags_yaml}\n"
        f'summary: "{safe_summary}"\n'
        f"source_pr: {pr_details['number']}\n"
        f'source_repo: "{pr_details["repo"]}"\n'
        f"draft: true\n"
        f"---\n\n"
    )

    return filename, slug, front_matter + content.strip()


def set_output(name, value):
    """Write a value to the GitHub Actions step output file."""
    github_output = os.environ.get("GITHUB_OUTPUT", "")
    if github_output:
        with open(github_output, "a") as fh:
            fh.write(f"{name}={value}\n")


def main():
    github_token = os.environ.get("GITHUB_TOKEN")
    if not github_token:
        print("Error: GITHUB_TOKEN environment variable is required.")
        sys.exit(1)

    source_repo = os.environ.get("SOURCE_REPO") or os.environ.get("GITHUB_REPOSITORY")
    pr_number = os.environ.get("PR_NUMBER")
    model = os.environ.get("AI_MODEL", "gpt-4o")

    if not source_repo:
        print("Error: SOURCE_REPO or GITHUB_REPOSITORY environment variable is required.")
        sys.exit(1)

    if not pr_number:
        print("Error: PR_NUMBER environment variable is required.")
        sys.exit(1)

    print(f"Fetching PR #{pr_number} from {source_repo}...")
    g = Github(github_token)
    try:
        pr_details = get_pr_details(g, source_repo, pr_number)
    except GithubException as exc:
        print(f"Error fetching PR: {exc}")
        sys.exit(1)

    print(f"Generating blog post for: {pr_details['title']}")
    raw_content = generate_blog_post(pr_details, model)

    filename, slug, formatted_content = parse_response(raw_content, pr_details)

    drafts_dir = Path("posts/drafts")
    drafts_dir.mkdir(parents=True, exist_ok=True)

    output_path = drafts_dir / filename
    output_path.write_text(formatted_content, encoding="utf-8")

    print(f"Blog post draft saved to: {output_path}")

    set_output("post_path", str(output_path))
    set_output("post_title", pr_details["title"])
    set_output("post_slug", slug)
    set_output("post_filename", filename)


if __name__ == "__main__":
    main()
