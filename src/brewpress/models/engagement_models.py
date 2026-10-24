from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from brewpress.config import gemini_model


class PublishDecision(StrEnum):
    APPROVED = "approved"
    PUBLISH_WITH_IMPROVEMENTS = "publish_with_improvements"
    REVISION_NEEDED = "revision_needed"


class HookStyle(StrEnum):
    PAIN = "pain"
    CURIOSITY = "curiosity"
    DATA = "data"


class CTAType(StrEnum):
    ACTION = "action"
    ENGAGEMENT = "engagement"
    SHARING = "sharing"


class CodeComplexity(StrEnum):
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"

class VersioningInfo(BaseModel):
    model_config = ConfigDict(frozen=True)
    prompt_version: str = "v1.0"
    tool_version: dict[str, str] = Field(default_factory=dict)
    model: str = Field(default_factory=gemini_model)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))

class ExecutionData(BaseModel):
    model_config = ConfigDict(frozen=True)

    retry_count: int = 0
    max_retries: int = 2
    failed_components: list[str] = Field(default_factory=list)
    fallback_applied: bool = False
    partial_success: bool = False
    start_time: datetime | None = None
    end_time: datetime | None = None
    duration_ms: int = 0
    fixer_iterations: int = 0

class LearningData(BaseModel):
    model_config = ConfigDict(frozen=True)

    hook_style: HookStyle | None = None
    cta_type: CTAType | None = None
    estimated_read_time: int | None = None
    code_complexity: CodeComplexity | None = None

class EngagementScoreData(BaseModel):
    model_config = ConfigDict(frozen=True)

    structural_score: int = Field(default=0, ge=0, le=100)
    technical_score: int = Field(default=0, ge=0, le=100)
    readability_score: int | None = Field(default=None, ge=0, le=100)
    final_score: int = Field(default=0, ge=0, le=100)
    fixer_iterations_applied: int = 0
    fixer_actions: list[str] = Field(default_factory=list)
    failed_rules: list[str] = Field(default_factory=list)
    decision: PublishDecision = PublishDecision.REVISION_NEEDED
    confidence: float = 0.0

class PublishingData(BaseModel):
    model_config = ConfigDict(frozen=True)

    wp_post_id: int | None = None
    wp_slug: str = ""
    wp_status: str | None = None
    idempotent_key: str = ""
    publish_timestamp: datetime | None = None
    url: str | None = None

class PostPublishMetrics(BaseModel):
    model_config = ConfigDict(frozen=True)

    collected: bool = False
    ctr: float | None = None
    avg_read_time: float | None = None
    bounce_rate: float | None = None
    likes: int | None = None
    shares: int | None = None
    comments: int | None = None
    engagement_percentile: float | None = None

class OverrideData(BaseModel):
    model_config = ConfigDict(frozen=True)

    approved: bool = False
    reason: str | None = None
    approved_by: str | None = None
    timestamp: datetime | None = None
    audit_log: list[str] = Field(default_factory=list)
