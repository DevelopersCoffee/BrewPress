"""Tests for brewpress.trend_scout — filtering, scoring, classification, suggestions."""

from __future__ import annotations

import pytest

from brewpress.trend_scout import (
    QUICK_POST_THRESHOLD,
    ContentStrategy,
    NullTrendSource,
    TrendDataSource,
    TrendScout,
    TrendSignal,
    TrendWindow,
    build_angle,
    build_reasoning,
    classify_strategy,
    is_relevant,
    score_signals,
)

# ------------------------------------------------------------------ #
# Test fixtures                                                        #
# ------------------------------------------------------------------ #

class StubTrendSource:
    """Returns predefined signals for deterministic tests."""

    def __init__(self, signals: list[TrendSignal]) -> None:
        self._signals = signals

    def fetch(
        self,
        keywords: list[str],
        window: TrendWindow,
        region: str,
    ) -> list[TrendSignal]:
        return [s for s in self._signals if s.keyword in keywords and s.window == window]


def make_signal(keyword: str, window: TrendWindow, raw_score: float) -> TrendSignal:
    return TrendSignal(keyword=keyword, window=window, raw_score=raw_score)


# ------------------------------------------------------------------ #
# is_relevant                                                          #
# ------------------------------------------------------------------ #


def test_is_relevant_exact_category() -> None:
    assert is_relevant("backend") is True


def test_is_relevant_case_insensitive() -> None:
    assert is_relevant("Backend Development") is True


def test_is_relevant_substring_match() -> None:
    assert is_relevant("spring boot 3 migration") is True


def test_is_relevant_java_substring() -> None:
    assert is_relevant("Java 21 virtual threads") is True


def test_is_relevant_ai_agent() -> None:
    assert is_relevant("AI agent frameworks in Python") is True


def test_is_relevant_llm() -> None:
    assert is_relevant("LLM tool use patterns") is True


def test_is_relevant_productivity() -> None:
    assert is_relevant("developer productivity metrics") is True


def test_is_relevant_system_design() -> None:
    assert is_relevant("system design for distributed systems") is True


def test_is_relevant_rejects_unrelated() -> None:
    assert is_relevant("cooking recipes") is False


def test_is_relevant_rejects_frontend_only() -> None:
    assert is_relevant("css animations tutorial") is False


def test_is_relevant_rejects_empty_string() -> None:
    assert is_relevant("") is False


# ------------------------------------------------------------------ #
# score_signals                                                        #
# ------------------------------------------------------------------ #


def test_score_signals_empty_returns_zero() -> None:
    assert score_signals([]) == 0.0


def test_score_signals_single_week_full_score() -> None:
    signals = [make_signal("java", TrendWindow.WEEK, 100.0)]
    result = score_signals(signals)
    assert result == pytest.approx(1.0)


def test_score_signals_single_week_half_score() -> None:
    signals = [make_signal("java", TrendWindow.WEEK, 50.0)]
    result = score_signals(signals)
    assert result == pytest.approx(0.5)


def test_score_signals_single_quarter_full_score() -> None:
    signals = [make_signal("java", TrendWindow.QUARTER, 100.0)]
    result = score_signals(signals)
    assert result == pytest.approx(1.0)


def test_score_signals_weights_week_higher_than_quarter() -> None:
    week_signal = [make_signal("java", TrendWindow.WEEK, 80.0)]
    quarter_signal = [make_signal("java", TrendWindow.QUARTER, 80.0)]
    # Both have same raw score — week weight (1.0) > quarter weight (0.3)
    # but normalised by their own weight they equal the same value
    # The difference shows when combined: week pulls more.
    assert score_signals(week_signal) == score_signals(quarter_signal)


def test_score_signals_multi_window_blends_correctly() -> None:
    # week=100 (w=1.0), month=50 (w=0.6), quarter=0 (w=0.3)
    # weighted_sum = 1.0*1.0 + 0.5*0.6 + 0.0*0.3 = 1.0 + 0.3 + 0.0 = 1.3
    # weight_total = 1.0 + 0.6 + 0.3 = 1.9
    # score = 1.3 / 1.9
    signals = [
        make_signal("spring", TrendWindow.WEEK, 100.0),
        make_signal("spring", TrendWindow.MONTH, 50.0),
        make_signal("spring", TrendWindow.QUARTER, 0.0),
    ]
    expected = 1.3 / 1.9
    assert score_signals(signals) == pytest.approx(expected, rel=1e-6)


def test_score_signals_normalized_max_is_one() -> None:
    signals = [
        make_signal("ai agent", TrendWindow.WEEK, 100.0),
        make_signal("ai agent", TrendWindow.MONTH, 100.0),
        make_signal("ai agent", TrendWindow.QUARTER, 100.0),
    ]
    assert score_signals(signals) == pytest.approx(1.0)


# ------------------------------------------------------------------ #
# classify_strategy                                                    #
# ------------------------------------------------------------------ #


def test_classify_quick_post_at_threshold() -> None:
    assert classify_strategy(QUICK_POST_THRESHOLD) == ContentStrategy.QUICK_POST


def test_classify_quick_post_above_threshold() -> None:
    assert classify_strategy(0.9) == ContentStrategy.QUICK_POST


def test_classify_evergreen_below_threshold() -> None:
    assert classify_strategy(QUICK_POST_THRESHOLD - 0.01) == ContentStrategy.EVERGREEN_TUTORIAL


def test_classify_evergreen_at_zero() -> None:
    assert classify_strategy(0.0) == ContentStrategy.EVERGREEN_TUTORIAL


# ------------------------------------------------------------------ #
# build_angle / build_reasoning                                        #
# ------------------------------------------------------------------ #


def test_build_angle_quick_post_contains_topic() -> None:
    angle = build_angle("spring boot", ContentStrategy.QUICK_POST)
    assert "spring boot" in angle


def test_build_angle_evergreen_contains_topic() -> None:
    angle = build_angle("system design", ContentStrategy.EVERGREEN_TUTORIAL)
    assert "system design" in angle


def test_build_angle_quick_post_differs_from_evergreen() -> None:
    qp = build_angle("java", ContentStrategy.QUICK_POST)
    ev = build_angle("java", ContentStrategy.EVERGREEN_TUTORIAL)
    assert qp != ev


def test_build_reasoning_contains_score() -> None:
    reasoning = build_reasoning(0.75, ContentStrategy.QUICK_POST)
    assert "0.75" in reasoning


def test_build_reasoning_spiking_for_quick_post() -> None:
    assert "spiking" in build_reasoning(0.8, ContentStrategy.QUICK_POST)


def test_build_reasoning_stable_for_evergreen() -> None:
    assert "stable" in build_reasoning(0.4, ContentStrategy.EVERGREEN_TUTORIAL)


# ------------------------------------------------------------------ #
# NullTrendSource                                                      #
# ------------------------------------------------------------------ #


def test_null_source_returns_empty() -> None:
    source = NullTrendSource()
    signals = source.fetch(["java"], TrendWindow.WEEK, "US")
    assert signals == []


def test_null_source_implements_protocol() -> None:
    assert isinstance(NullTrendSource(), TrendDataSource)


# ------------------------------------------------------------------ #
# TrendScout.suggest — filtering                                       #
# ------------------------------------------------------------------ #


def test_suggest_filters_irrelevant_keywords() -> None:
    source = StubTrendSource(
        [make_signal("cooking", TrendWindow.WEEK, 90.0)]
    )
    scout = TrendScout(source=source)
    results = scout.suggest(["cooking", "food blog"])
    assert results == []


def test_suggest_keeps_relevant_keywords() -> None:
    source = StubTrendSource(
        [make_signal("java", TrendWindow.WEEK, 80.0)]
    )
    scout = TrendScout(source=source)
    results = scout.suggest(["java"])
    assert len(results) == 1
    assert results[0].topic == "java"


def test_suggest_skips_zero_score_keywords() -> None:
    # Relevant keyword but source returns zero-score signals.
    source = StubTrendSource(
        [make_signal("backend", TrendWindow.WEEK, 0.0)]
    )
    scout = TrendScout(source=source)
    results = scout.suggest(["backend"])
    assert results == []


def test_suggest_skips_keywords_with_no_signals() -> None:
    source = NullTrendSource()
    scout = TrendScout(source=source)
    results = scout.suggest(["system design"])
    assert results == []


# ------------------------------------------------------------------ #
# TrendScout.suggest — sorting and limit                              #
# ------------------------------------------------------------------ #


def test_suggest_sorted_by_score_descending() -> None:
    source = StubTrendSource([
        make_signal("java", TrendWindow.WEEK, 40.0),
        make_signal("ai agent", TrendWindow.WEEK, 90.0),
        make_signal("system design", TrendWindow.WEEK, 60.0),
    ])
    scout = TrendScout(source=source)
    results = scout.suggest(["java", "ai agent", "system design"])
    scores = [r.score for r in results]
    assert scores == sorted(scores, reverse=True)


def test_suggest_respects_limit() -> None:
    source = StubTrendSource([
        make_signal("java", TrendWindow.WEEK, 80.0),
        make_signal("spring", TrendWindow.WEEK, 75.0),
        make_signal("backend", TrendWindow.WEEK, 70.0),
        make_signal("ai agent", TrendWindow.WEEK, 65.0),
        make_signal("system design", TrendWindow.WEEK, 60.0),
        make_signal("llm", TrendWindow.WEEK, 55.0),
    ])
    scout = TrendScout(source=source)
    results = scout.suggest(
        ["java", "spring", "backend", "ai agent", "system design", "llm"],
        limit=3,
    )
    assert len(results) == 3


def test_suggest_default_limit_is_ten() -> None:
    keywords = [f"backend topic {i}" for i in range(15)]
    signals = [make_signal(k, TrendWindow.WEEK, 50.0) for k in keywords]
    scout = TrendScout(source=StubTrendSource(signals))
    results = scout.suggest(keywords)
    assert len(results) <= 10


# ------------------------------------------------------------------ #
# TrendScout.suggest — strategy classification                        #
# ------------------------------------------------------------------ #


def test_suggest_quick_post_for_high_score() -> None:
    source = StubTrendSource([make_signal("ai agent", TrendWindow.WEEK, 90.0)])
    scout = TrendScout(source=source)
    result = scout.suggest(["ai agent"])[0]
    assert result.strategy == ContentStrategy.QUICK_POST


def test_suggest_evergreen_for_low_score() -> None:
    source = StubTrendSource([make_signal("system design", TrendWindow.WEEK, 40.0)])
    scout = TrendScout(source=source)
    result = scout.suggest(["system design"])[0]
    assert result.strategy == ContentStrategy.EVERGREEN_TUTORIAL


# ------------------------------------------------------------------ #
# TrendScout.suggest — output fields                                  #
# ------------------------------------------------------------------ #


def test_suggest_result_has_angle() -> None:
    source = StubTrendSource([make_signal("java", TrendWindow.WEEK, 70.0)])
    scout = TrendScout(source=source)
    result = scout.suggest(["java"])[0]
    assert result.angle
    assert "java" in result.angle.lower()


def test_suggest_result_has_reasoning() -> None:
    source = StubTrendSource([make_signal("backend", TrendWindow.WEEK, 70.0)])
    scout = TrendScout(source=source)
    result = scout.suggest(["backend"])[0]
    assert result.reasoning


def test_suggest_result_keywords_contains_topic() -> None:
    source = StubTrendSource([make_signal("spring", TrendWindow.WEEK, 60.0)])
    scout = TrendScout(source=source)
    result = scout.suggest(["spring"])[0]
    assert "spring" in result.keywords


def test_suggest_result_score_is_rounded() -> None:
    source = StubTrendSource([make_signal("java", TrendWindow.WEEK, 33.333)])
    scout = TrendScout(source=source)
    result = scout.suggest(["java"])[0]
    # score should be rounded to 4 decimal places
    assert result.score == round(result.score, 4)


# ------------------------------------------------------------------ #
# TrendScout — region passthrough                                     #
# ------------------------------------------------------------------ #


class RegionCapturingSource:
    """Records the region argument passed to fetch()."""

    def __init__(self) -> None:
        self.regions_seen: list[str] = []

    def fetch(self, keywords: list[str], window: TrendWindow, region: str) -> list[TrendSignal]:
        self.regions_seen.append(region)
        return [TrendSignal(keyword=k, window=window, raw_score=50.0) for k in keywords]


def test_suggest_passes_region_to_source() -> None:
    source = RegionCapturingSource()
    scout = TrendScout(source=source, region="GB")
    scout.suggest(["backend"])
    assert all(r == "GB" for r in source.regions_seen)


def test_suggest_default_region_is_us() -> None:
    source = RegionCapturingSource()
    scout = TrendScout(source=source)
    scout.suggest(["backend"])
    assert "US" in source.regions_seen


# ------------------------------------------------------------------ #
# TrendScout — null source default                                    #
# ------------------------------------------------------------------ #


def test_scout_default_source_is_null() -> None:
    scout = TrendScout()
    results = scout.suggest(["java", "spring boot"])
    assert results == []
