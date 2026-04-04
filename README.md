# BrewPress

Autonomous dev content engine — generate, review, and publish
[DevelopersCoffee](https://github.com/DevelopersCoffee) blog posts directly
from real engineering work.

## How it works

1. **Generate** — When a pull request is merged into `main`, BrewPress
   fetches the PR title, description, commits, and file changes, then uses an
   AI model to write a polished markdown blog post draft.
2. **Review** — The draft is committed to a `blog-draft/*` branch and a pull
   request is opened for editorial review. Editors can read, comment on, and
   edit the post before approving it.
3. **Publish** — When the review PR is merged, the post is automatically moved
   from `posts/drafts/` to `posts/published/` with its front-matter updated to
   `draft: false` and a `published_date` set.

```
PR merged ──► Generate Blog Post workflow
                 └─► AI draft created in posts/drafts/
                 └─► Review PR opened (blog-draft/* branch)
                       └─► Editors review & merge
                             └─► Publish Blog Post workflow
                                   └─► Post moved to posts/published/
```

## Repository layout

```
.github/workflows/
  generate-blog-post.yml   # Triggered on PR merge; generates a draft
  publish-blog-post.yml    # Triggered when a draft PR is merged; publishes
posts/
  drafts/                  # AI-generated drafts awaiting review
  published/               # Reviewed and published posts
scripts/
  generate_post.py         # Fetches PR data and calls the AI model
  publish_post.py          # Moves drafts to published/
  requirements.txt         # Python dependencies
```

## Setup

### 1. Secrets

| Secret | Required | Description |
|--------|----------|-------------|
| `OPENAI_API_KEY` | Optional¹ | OpenAI API key |
| `GITHUB_MODELS_TOKEN` | Optional¹ | GitHub Models personal access token |

¹ If neither is supplied the workflow falls back to the built-in
`GITHUB_TOKEN` with the GitHub Models endpoint
(`https://models.inference.ai.azure.com`).

### 2. Variables (optional)

| Variable | Default | Description |
|----------|---------|-------------|
| `AI_MODEL` | `gpt-4o` | AI model name passed to the API |

### 3. Permissions

The workflows require the following repository permissions for
`GITHUB_TOKEN`:

- **Contents** — write (to push the draft branch and the publish commit)
- **Pull requests** — write (to open the review PR)

These are already declared in the workflow files; no manual changes are
needed for public repositories. For private repositories, confirm that
Actions have write access under *Settings → Actions → General →
Workflow permissions*.

## Triggering manually

Go to **Actions → Generate Blog Post → Run workflow** and enter:

- **PR number** — the number of the pull request you want to turn into a post.
- **Source repository** *(optional)* — defaults to this repository. Use
  `owner/repo` to pull from another public repository.

## Contributing

Pull requests are welcome. Please open an issue first to discuss significant
changes.

## License

[Apache License 2.0](LICENSE)
