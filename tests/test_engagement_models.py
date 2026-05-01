import pytest
from pydantic import ValidationError
from brewpress.models import BlogJob
from brewpress.models.engagement_models import (
    PublishDecision, VersioningInfo, EngagementScoreData,
    LearningData, ExecutionData, PublishingData, PostPublishMetrics,
    OverrideData, HookStyle, CTAType, CodeComplexity
)

def test_blogjob_has_engagement_fields():
    job = BlogJob(
        title="Test",
        draft_body_md="# Test\nContent"
    )
    assert hasattr(job, 'versioning')
    assert hasattr(job, 'engagement_data')
    assert hasattr(job, 'publishing')
    assert job.engagement_data.decision == PublishDecision.REVISION_NEEDED

def test_engagement_score_data_defaults():
    data = EngagementScoreData()
    assert data.structural_score == 0
    assert data.technical_score == 0
    assert data.fixer_actions == []
    assert data.decision == PublishDecision.REVISION_NEEDED

def test_versioning_info_has_timestamp():
    info = VersioningInfo()
    assert info.timestamp is not None
    assert info.model == "gemini-2.0-flash"


# ============================================================================
# NEW TESTS: Frozen immutability
# ============================================================================

def test_engagement_models_are_frozen():
    """Verify all engagement models are immutable (frozen=True)."""
    # Test VersioningInfo
    info = VersioningInfo()
    with pytest.raises((AttributeError, ValueError)):
        info.model_version = "v2.0"

    # Test ExecutionData
    exec_data = ExecutionData()
    with pytest.raises((AttributeError, ValueError)):
        exec_data.retry_count = 5

    # Test LearningData
    learning = LearningData()
    with pytest.raises((AttributeError, ValueError)):
        learning.estimated_read_time = 10

    # Test EngagementScoreData
    score_data = EngagementScoreData()
    with pytest.raises((AttributeError, ValueError)):
        score_data.structural_score = 50

    # Test PublishingData
    pub_data = PublishingData()
    with pytest.raises((AttributeError, ValueError)):
        pub_data.wp_post_id = 123

    # Test PostPublishMetrics
    metrics = PostPublishMetrics()
    with pytest.raises((AttributeError, ValueError)):
        metrics.collected = True

    # Test OverrideData
    override = OverrideData()
    with pytest.raises((AttributeError, ValueError)):
        override.approved = True


# ============================================================================
# NEW TESTS: Score validation (Field ge=0, le=100)
# ============================================================================

def test_score_validation():
    """Verify score fields enforce bounds: 0 <= score <= 100."""
    # Valid boundary values
    data = EngagementScoreData(structural_score=0, technical_score=100, final_score=50)
    assert data.structural_score == 0
    assert data.technical_score == 100
    assert data.final_score == 50

    # Negative structural_score should fail
    with pytest.raises(ValidationError) as exc_info:
        EngagementScoreData(structural_score=-1)
    assert "greater than or equal to 0" in str(exc_info.value)

    # Negative technical_score should fail
    with pytest.raises(ValidationError) as exc_info:
        EngagementScoreData(technical_score=-1)
    assert "greater than or equal to 0" in str(exc_info.value)

    # Score > 100 should fail
    with pytest.raises(ValidationError) as exc_info:
        EngagementScoreData(final_score=101)
    assert "less than or equal to 100" in str(exc_info.value)

    # structural_score > 100 should fail
    with pytest.raises(ValidationError) as exc_info:
        EngagementScoreData(structural_score=150)
    assert "less than or equal to 100" in str(exc_info.value)

    # technical_score > 100 should fail
    with pytest.raises(ValidationError) as exc_info:
        EngagementScoreData(technical_score=200)
    assert "less than or equal to 100" in str(exc_info.value)


# ============================================================================
# NEW TESTS: Enum values
# ============================================================================

def test_enum_values():
    """Verify enum classes exist with correct values."""
    # Test HookStyle enum
    assert HookStyle.PAIN.value == "pain"
    assert HookStyle.CURIOSITY.value == "curiosity"
    assert HookStyle.DATA.value == "data"

    # Test CTAType enum
    assert CTAType.ACTION.value == "action"
    assert CTAType.ENGAGEMENT.value == "engagement"
    assert CTAType.SHARING.value == "sharing"

    # Test CodeComplexity enum
    assert CodeComplexity.BEGINNER.value == "beginner"
    assert CodeComplexity.INTERMEDIATE.value == "intermediate"
    assert CodeComplexity.ADVANCED.value == "advanced"


def test_learning_data_uses_enums():
    """Verify LearningData accepts enum values."""
    learning = LearningData(
        hook_style=HookStyle.PAIN,
        cta_type=CTAType.ACTION,
        code_complexity=CodeComplexity.BEGINNER
    )
    assert learning.hook_style == HookStyle.PAIN
    assert learning.cta_type == CTAType.ACTION
    assert learning.code_complexity == CodeComplexity.BEGINNER

    # Test with string values (Pydantic should coerce)
    learning2 = LearningData(
        hook_style="curiosity",
        cta_type="engagement",
        code_complexity="advanced"
    )
    assert learning2.hook_style == HookStyle.CURIOSITY
    assert learning2.cta_type == CTAType.ENGAGEMENT
    assert learning2.code_complexity == CodeComplexity.ADVANCED


# ============================================================================
# NEW TESTS: Edge cases
# ============================================================================

def test_score_edge_cases():
    """Verify boundary values 0 and 100 are accepted."""
    # All scores at 0 boundary
    data_min = EngagementScoreData(
        structural_score=0, technical_score=0, final_score=0
    )
    assert data_min.structural_score == 0
    assert data_min.technical_score == 0
    assert data_min.final_score == 0

    # All scores at 100 boundary
    data_max = EngagementScoreData(
        structural_score=100, technical_score=100, final_score=100
    )
    assert data_max.structural_score == 100
    assert data_max.technical_score == 100
    assert data_max.final_score == 100

    # Mid-range values
    data_mid = EngagementScoreData(
        structural_score=50, technical_score=75, final_score=25
    )
    assert data_mid.structural_score == 50
    assert data_mid.technical_score == 75
    assert data_mid.final_score == 25
