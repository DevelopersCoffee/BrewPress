import pytest
from brewpress.models import BlogJob
from brewpress.models.engagement_models import (
    PublishDecision, VersioningInfo, EngagementScoreData
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
