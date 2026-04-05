"""Trend Scout — topic ideation and keyword guidance from trend signals.

Suggests blog topics filtered to developer-relevant categories, scored by
recency-weighted trend data, and classified into content strategy.

ADK integration note: TrendScout is stateless and data-source agnostic.
Wrap it as an ADK Tool by injecting the data source via __init__; the
suggest() method maps cleanly to a tool call with typed inputs/outputs.

Data flow:
    keywords
        -> is_relevant() filter (hard category filter from PRD)
        -> TrendDataSource.fetch() per window
        -> score_signals() (recency-weighted average)
        -> classify_strategy() (Quick Post vs Evergreen Tutorial)
        -> TopicSuggestion list, sorted by score descending
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, runtime_checkable

# ------------------------------------------------------------------ #
# PRD constants                                                        #
# ------------------------------------------------------------------ #

class TrendWindow(StrEnum):
    WEEK = "7d"
    MONTH = "30d"
    QUARTER = "90d"


class ContentStrategy(StrEnum):
    QUICK_POST = "quick_post"           # spiking trend, time-sensitive
    EVERGREEN_TUTORIAL = "evergreen_tutorial"  # stable demand, long shelf life


# Recency weights from PRD: 7d high, 30d medium, 90d low.
WINDOW_WEIGHTS: dict[TrendWindow, float] = {
    TrendWindow.WEEK: 1.0,
    TrendWindow.MONTH: 0.6,
    TrendWindow.QUARTER: 0.3,
}

# Hard filter: only topics in these categories are surfaced (PRD §Trend System).
# Matching is substring/case-insensitive so "Java Spring Boot" matches "spring".
ALLOWED_CATEGORIES: frozenset[str] = frozenset({
    "backend",
    "java",
    "spring",
    "ai agent",
    "llm",
    "developer productivity",
    "productivity",
    "system design",
})

# Score threshold above which a trend is classified as Quick Post.
QUICK_POST_THRESHOLD = 0.65


# ------------------------------------------------------------------ #
# Data models                                                          #
# ------------------------------------------------------------------ #

@dataclass(frozen=True)
class TrendSignal:
    """A single trend data point for one keyword in one time window."""

    keyword: str
    window: TrendWindow
    raw_score: float  # Google Trends scale: 0–100


@dataclass(frozen=True)
class TopicSuggestion:
    """A suggested blog topic with angle, keywords, and strategy."""

    topic: str
    angle: str              # "why now" framing for the post
    keywords: list[str]     # SEO keywords to target
    strategy: ContentStrategy
    score: float            # normalized 0.0–1.0
    reasoning: str          # one-line explanation of why this was suggested


# ------------------------------------------------------------------ #
# Data source protocol                                                 #
# ------------------------------------------------------------------ #

@runtime_checkable
class TrendDataSource(Protocol):
    """Fetch raw trend signals for a list of keywords.

    Implement this protocol to swap in Google Trends, a cache layer,
    or a test fixture without changing TrendScout.
    """

    def fetch(
        self,
        keywords: list[str],
        window: TrendWindow,
        region: str,
    ) -> list[TrendSignal]:
        """Return one TrendSignal per keyword for the given window/region."""
        ...


class NullTrendSource:
    """Offline fallback that returns empty signals.

    Used when no trend data source is configured. TrendScout will
    produce no suggestions, which is the correct safe default.
    """

    def fetch(
        self,
        keywords: list[str],
        window: TrendWindow,
        region: str,
    ) -> list[TrendSignal]:
        return []


# ------------------------------------------------------------------ #
# Pure functions (deterministic, no I/O)                              #
# ------------------------------------------------------------------ #

def is_relevant(keyword: str) -> bool:
    """Return True if the keyword falls within an allowed category.

    Matching is case-insensitive substring: "Spring Boot" matches "spring".
    """
    normalized = keyword.lower()
    return any(cat in normalized for cat in ALLOWED_CATEGORIES)


def score_signals(signals: list[TrendSignal]) -> float:
    """Compute a recency-weighted trend score from multi-window signals.

    Each signal's raw score (0–100) is normalised to 0–1 and weighted
    by its window weight. Returns 0.0 when signals is empty.
    """
    if not signals:
        return 0.0
    weighted_sum = sum(
        (sig.raw_score / 100.0) * WINDOW_WEIGHTS[sig.window] for sig in signals
    )
    weight_total = sum(WINDOW_WEIGHTS[sig.window] for sig in signals)
    return weighted_sum / weight_total


def classify_strategy(score: float) -> ContentStrategy:
    """Classify a topic as Quick Post (spiking) or Evergreen Tutorial (stable)."""
    return (
        ContentStrategy.QUICK_POST
        if score >= QUICK_POST_THRESHOLD
        else ContentStrategy.EVERGREEN_TUTORIAL
    )


def build_angle(topic: str, strategy: ContentStrategy) -> str:
    """Generate a 'why now' angle for the topic."""
    if strategy == ContentStrategy.QUICK_POST:
        return f"Why {topic} is gaining traction now — and what developers need to know"
    return f"A practical developer guide to {topic}"


def build_reasoning(score: float, strategy: ContentStrategy) -> str:
    """One-line explanation for the suggestion."""
    label = "spiking" if strategy == ContentStrategy.QUICK_POST else "stable"
    return f"trend score {score:.2f} ({label} demand)"


# ------------------------------------------------------------------ #
# TrendScout                                                           #
# ------------------------------------------------------------------ #

class TrendScout:
    """Suggest blog topics and keywords from trend signals.

    Args:
        source: Any object implementing TrendDataSource. Defaults to
                NullTrendSource (offline, returns no suggestions).
        region: ISO 3166-1 alpha-2 region code (e.g. "US", "GB").

    Example:
        scout = TrendScout(source=NullTrendSource())
        suggestions = scout.suggest(["python asyncio", "spring boot 3"])
    """

    def __init__(
        self,
        source: TrendDataSource | None = None,
        region: str = "US",
    ) -> None:
        self._source: TrendDataSource = source or NullTrendSource()
        self._region = region

    def suggest(
        self,
        keywords: list[str],
        windows: tuple[TrendWindow, ...] = (
            TrendWindow.WEEK,
            TrendWindow.MONTH,
            TrendWindow.QUARTER,
        ),
        limit: int = 10,
    ) -> list[TopicSuggestion]:
        """Return topic suggestions sorted by score descending.

        Args:
            keywords: Seed keywords to evaluate.
            windows:  Trend windows to query. Defaults to all three.
            limit:    Maximum number of suggestions to return.

        Returns:
            List of TopicSuggestion, highest score first. Empty when no
            keywords pass the relevance filter or no signals are returned.
        """
        suggestions: list[TopicSuggestion] = []

        for keyword in keywords:
            if not is_relevant(keyword):
                continue

            signals: list[TrendSignal] = []
            for window in windows:
                signals.extend(
                    self._source.fetch([keyword], window, self._region)
                )

            score = score_signals(signals)
            if score == 0.0:
                continue

            strategy = classify_strategy(score)
            suggestions.append(
                TopicSuggestion(
                    topic=keyword,
                    angle=build_angle(keyword, strategy),
                    keywords=[keyword],
                    strategy=strategy,
                    score=round(score, 4),
                    reasoning=build_reasoning(score, strategy),
                )
            )

        return sorted(suggestions, key=lambda s: s.score, reverse=True)[:limit]
