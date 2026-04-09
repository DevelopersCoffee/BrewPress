# BrewPress

AI-powered blog generation and WordPress publishing for technical writers.

BrewPress turns topics, notes, git diffs, and GitHub PRs into structured technical blog posts, then publishes them to any WordPress site via the REST API.

---

## What it does

- **Generates drafts** from a topic, notes, or a local git diff using Gemini Flash
- **Captures proof screenshots** of terminal output for code-heavy posts
- **Extracts SEO metadata** — title, slug, meta description, keywords, tags
- **Runs a deterministic review loop** — no accidental publishes
- **Publishes to WordPress as a draft first** — live only when you say `--live`
- **Adapts to your site's voice** via a tone fingerprint (`brewpress calibrate`)

---

## Install

```bash
pip install brewpress
```

Or install from source:

```bash
git clone https://github.com/your-org/brewpress.git
cd brewpress
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[gemini]"
```

---

## Quickstart

### 1. Set environment variables

```bash
cp .env.example .env
# Edit .env and fill in your credentials
```

| Variable | Required | Description |
|---|---|---|
| `WP_URL` | Yes | Your WordPress URL (must be `https://`) |
| `WP_USERNAME` | Yes | WordPress username |
| `WP_APP_PASSWORD` | Yes | [Application Password](https://wordpress.org/documentation/article/application-passwords/) from WP Admin |
| `GOOGLE_API_KEY` | Yes (draft) | [Google AI Studio](https://aistudio.google.com/app/apikey) key |
| `BREWPRESS_SITE_NAME` | No | Human name of your site, used in AI prompts (default: `my technical blog`) |
| `BREWPRESS_SITE_FOCUS` | No | Topic focus for draft generation (default: `backend development`) |

### 2. Check your setup

```bash
brewpress doctor
```

This verifies Python version, env vars, WordPress connectivity, and the Gemini package.

### 3. Generate a draft

```bash
# From a topic
brewpress draft --topic "Java 21 virtual threads in practice"

# From a git diff
brewpress draft --diff path/to/changes.diff --topic "what changed"

# From notes
brewpress draft --topic "Spring Boot caching" --notes "We replaced Caffeine with Redis"
```

### 4. Review and approve

```bash
brewpress review                   # display current draft
brewpress approve-content          # step 1 of 2
brewpress approve-publish          # step 2: saves as WordPress draft
brewpress approve-publish --live   # publishes live
```

### 5. Revise or reject

```bash
brewpress revise "shorten the introduction and add a TL;DR"
brewpress reject --reason "off topic"
```

### 6. Calibrate your tone (optional but recommended)

```bash
brewpress calibrate
```

Fetches your 20 most recent posts and writes a tone fingerprint to `~/.brewpress/tone.json`. Future drafts automatically use this fingerprint.

### 7. Surface topic ideas

```bash
brewpress suggest --topic "spring boot" "ai agents" --count 5
```

---

## All commands

| Command | Description |
|---|---|
| `brewpress doctor` | Check environment and connectivity |
| `brewpress draft` | Generate a new blog post draft |
| `brewpress review` | Display the current draft |
| `brewpress approve-content` | Approve content (step 1 of 2) |
| `brewpress approve-publish` | Send to WordPress (step 2 of 2) |
| `brewpress revise <instruction>` | Revise and reset approvals |
| `brewpress reject` | Discard the current draft |
| `brewpress calibrate` | Build tone fingerprint from your site |
| `brewpress suggest` | Suggest topics using trend signals |

---

## Review flow

```
draft  →  [review]  →  approve-content  →  approve-publish
                ↑                               |
              revise  ←──────────────────────────
```

- `approve-publish` always creates a **WordPress draft** by default.
- Add `--live` to publish immediately.
- Rejecting from `APPROVED_STEP_2` requires `--force`.

---

## Site customization

BrewPress is site-agnostic. Set two optional env vars to ground drafts in your site's identity:

```bash
BREWPRESS_SITE_NAME="Acme Engineering Blog"
BREWPRESS_SITE_FOCUS="distributed systems and platform engineering"
```

Run `brewpress calibrate` to layer in your actual writing style on top.

---

## WordPress setup

1. Log in to WordPress Admin.
2. Go to **Users → Profile → Application Passwords**.
3. Create a new Application Password named `brewpress`.
4. Copy the generated password (spaces included) into `WP_APP_PASSWORD`.

BrewPress uses the WordPress REST API (`/wp-json/wp/v2/`) — no plugins required.

> HTTPS is enforced. Credentials are never sent over plain HTTP.

---

## CI / GitHub Actions

The included workflows run on every push and PR:

- **CI** (`.github/workflows/ci.yml`): lint + test matrix across Python 3.11, 3.12, 3.13
- **Release** (`.github/workflows/release.yml`): builds sdist, wheel, and native binaries for Linux, macOS, Windows on every `v*.*.*` tag

To add WordPress credentials to CI, store them as repository secrets under **Settings → Secrets → Actions**:

- `WP_URL`, `WP_USERNAME`, `WP_APP_PASSWORD`, `GOOGLE_API_KEY`

---

## License

[Apache-2.0](./LICENSE)
