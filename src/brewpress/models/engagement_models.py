from pydantic import BaseModel, Field
from typing import Optional, List, Dict
from datetime import datetime, UTC
from enum import Enum

class PublishDecision(str, Enum):
    APPROVED = "approved"
    PUBLISH_WITH_IMPROVEMENTS = "publish_with_improvements"
    REVISION_NEEDED = "revision_needed"

class VersioningInfo(BaseModel):
    prompt_version: str = "v1.0"
    tool_version: Dict[str, str] = Field(default_factory=dict)
    model: str = "gemini-2.0-flash"
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))

class ExecutionData(BaseModel):
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
    hook_style: Optional[str] = None  # pain, curiosity, data
    cta_type: Optional[str] = None  # action, engagement, sharing
    estimated_read_time: Optional[int] = None
    code_complexity: Optional[str] = None  # beginner, intermediate, advanced

class EngagementScoreData(BaseModel):
    structural_score: int = 0
    technical_score: int = 0
    readability_score: Optional[int] = None
    final_score: int = 0
    fixer_iterations_applied: int = 0
    fixer_actions: List[str] = Field(default_factory=list)
    failed_rules: List[str] = Field(default_factory=list)
    decision: PublishDecision = PublishDecision.REVISION_NEEDED
    confidence: float = 0.0

class PublishingData(BaseModel):
    wp_post_id: Optional[int] = None
    wp_slug: str = ""
    wp_status: Optional[str] = None  # draft, published
    idempotent_key: str = ""
    publish_timestamp: Optional[datetime] = None
    url: Optional[str] = None

class PostPublishMetrics(BaseModel):
    collected: bool = False
    ctr: Optional[float] = None
    avg_read_time: Optional[float] = None
    bounce_rate: Optional[float] = None
    likes: Optional[int] = None
    shares: Optional[int] = None
    comments: Optional[int] = None
    engagement_percentile: Optional[float] = None

class OverrideData(BaseModel):
    approved: bool = False
    reason: Optional[str] = None
    approved_by: Optional[str] = None
    timestamp: Optional[datetime] = None
    audit_log: List[str] = Field(default_factory=list)
