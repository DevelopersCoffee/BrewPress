from pydantic import BaseModel, ConfigDict, Field
from typing import Optional, List, Dict
from datetime import datetime, UTC
from enum import Enum

class PublishDecision(str, Enum):
    APPROVED = "approved"
    PUBLISH_WITH_IMPROVEMENTS = "publish_with_improvements"
    REVISION_NEEDED = "revision_needed"

class HookStyle(str, Enum):
    PAIN = "pain"
    CURIOSITY = "curiosity"
    DATA = "data"

class CTAType(str, Enum):
    ACTION = "action"
    ENGAGEMENT = "engagement"
    SHARING = "sharing"

class CodeComplexity(str, Enum):
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"

class VersioningInfo(BaseModel):
    model_config = ConfigDict(frozen=True)
    prompt_version: str = "v1.0"
    tool_version: Dict[str, str] = Field(default_factory=dict)
    model: str = "gemini-2.0-flash"
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))

class ExecutionData(BaseModel):
    model_config = ConfigDict(frozen=True)

    retry_count: int = 0
    max_retries: int = 2
    failed_components: List[str] = Field(default_factory=list)
    fallback_applied: bool = False
    partial_success: bool = False
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    duration_ms: int = 0
    fixer_iterations: int = 0

class LearningData(BaseModel):
    model_config = ConfigDict(frozen=True)

    hook_style: Optional[HookStyle] = None
    cta_type: Optional[CTAType] = None
    estimated_read_time: Optional[int] = None
    code_complexity: Optional[CodeComplexity] = None

class EngagementScoreData(BaseModel):
    model_config = ConfigDict(frozen=True)

    structural_score: int = Field(default=0, ge=0, le=100)
    technical_score: int = Field(default=0, ge=0, le=100)
    readability_score: Optional[int] = None
    final_score: int = Field(default=0, ge=0, le=100)
    fixer_iterations_applied: int = 0
    fixer_actions: List[str] = Field(default_factory=list)
    failed_rules: List[str] = Field(default_factory=list)
    decision: PublishDecision = PublishDecision.REVISION_NEEDED
    confidence: float = 0.0

class PublishingData(BaseModel):
    model_config = ConfigDict(frozen=True)

    wp_post_id: Optional[int] = None
    wp_slug: str = ""
    wp_status: Optional[str] = None
    idempotent_key: str = ""
    publish_timestamp: Optional[datetime] = None
    url: Optional[str] = None

class PostPublishMetrics(BaseModel):
    model_config = ConfigDict(frozen=True)

    collected: bool = False
    ctr: Optional[float] = None
    avg_read_time: Optional[float] = None
    bounce_rate: Optional[float] = None
    likes: Optional[int] = None
    shares: Optional[int] = None
    comments: Optional[int] = None
    engagement_percentile: Optional[float] = None

class OverrideData(BaseModel):
    model_config = ConfigDict(frozen=True)

    approved: bool = False
    reason: Optional[str] = None
    approved_by: Optional[str] = None
    timestamp: Optional[datetime] = None
    audit_log: List[str] = Field(default_factory=list)
