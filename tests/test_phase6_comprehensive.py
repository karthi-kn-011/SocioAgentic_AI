import pytest
import datetime
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from backend.app.database.database import Base, get_db
from backend.app.database.models import (
    Post, ScheduledPost, PostWorkflowStatus, ScheduleStatus,
    ApprovalRequest, ApprovalStatus, PublishLog, PlatformType
)
from backend.app.services.schedule_service import ScheduleService
from backend.app.services.publishing_service import PublishingService
from backend.app.services.approval_service import ApprovalService
from backend.app.main import app

TEST_DB_URL = "sqlite:///./test_phase6_comprehensive_temp.db"
engine = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def override_get_db():
    db = TestingSession()
    try:
        yield db
    finally:
        db.close()

@pytest.fixture(autouse=True)
def setup_database():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    app.dependency_overrides[get_db] = override_get_db
    yield
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)
    if os.path.exists("./test_phase6_comprehensive_temp.db"):
        try:
            os.remove("./test_phase6_comprehensive_temp.db")
        except OSError:
            pass

# -------------------------------------------------------------
# Test Suite 1: Review & Approvals Transitions
# -------------------------------------------------------------

def test_pending_to_approved_transition():
    client = TestClient(app)
    with TestingSession() as db:
        post = Post(
            topic="Audit Approvals",
            raw_content="Content",
            target_platforms=["TWITTER"],
            platform_contents={"TWITTER": "Twitter post content"},
            status=PostWorkflowStatus.AWAITING_HUMAN_APPROVAL.value,
        )
        db.add(post)
        db.commit()
        db.refresh(post)

        app_req = ApprovalRequest(
            post_id=post.id,
            status=ApprovalStatus.PENDING.value,
            requested_at=datetime.datetime.now(datetime.timezone.utc)
        )
        db.add(app_req)
        db.commit()
        db.refresh(app_req)
        req_id = app_req.id

    # 1. Verify it shows up in Pending API
    res = client.get("/api/v1/approvals/pending")
    assert res.status_code == 200
    pending_items = res.json()
    assert any(item["id"] == req_id for item in pending_items)

    # 2. Approve via API
    res_app = client.post(f"/api/v1/approvals/{req_id}/approve", json={"reviewer": "Alice QA"})
    assert res_app.status_code == 200
    assert res_app.json()["approval_status"] == "APPROVED"

    # 3. Verify it disappeared from Pending API
    res_pending_after = client.get("/api/v1/approvals/pending")
    assert res_pending_after.status_code == 200
    assert not any(item["id"] == req_id for item in res_pending_after.json())

    # 4. Verify it is in History API with APPROVED state
    res_history = client.get("/api/v1/approvals/history")
    assert res_history.status_code == 200
    hist_items = [i for i in res_history.json() if i["id"] == req_id]
    assert len(hist_items) == 1
    assert hist_items[0]["status"] == "APPROVED"
    assert hist_items[0]["reviewer"] == "Alice QA"


def test_pending_to_rejected_transition_with_reason():
    client = TestClient(app)
    with TestingSession() as db:
        post = Post(
            topic="Reject Post Audit",
            raw_content="Content",
            target_platforms=["TWITTER"],
            platform_contents={"TWITTER": "Draft content"},
            status=PostWorkflowStatus.AWAITING_HUMAN_APPROVAL.value,
        )
        db.add(post)
        db.commit()
        db.refresh(post)

        app_req = ApprovalRequest(
            post_id=post.id,
            status=ApprovalStatus.PENDING.value,
            requested_at=datetime.datetime.now(datetime.timezone.utc)
        )
        db.add(app_req)
        db.commit()
        db.refresh(app_req)
        req_id = app_req.id

    # 1. Reject without reason must fail (422 validation error or 400 bad request)
    res_fail = client.post(f"/api/v1/approvals/{req_id}/reject", json={"rejection_reason": ""})
    assert res_fail.status_code in (400, 422)

    # 2. Reject with valid reason
    res_rej = client.post(f"/api/v1/approvals/{req_id}/reject", json={
        "rejection_reason": "Tone too aggressive for audience.",
        "reviewer": "Bob Lead"
    })
    assert res_rej.status_code == 200
    assert res_rej.json()["approval_status"] == "REJECTED"

    # 3. Disappears from Pending
    res_pending = client.get("/api/v1/approvals/pending")
    assert not any(i["id"] == req_id for i in res_pending.json())

    # 4. Appears in History with rejection reason
    res_hist = client.get("/api/v1/approvals/history")
    found = [i for i in res_hist.json() if i["id"] == req_id]
    assert len(found) == 1
    assert found[0]["status"] == "REJECTED"
    assert found[0]["rejection_reason"] == "Tone too aggressive for audience."


# -------------------------------------------------------------
# Test Suite 2: Scheduling, Content Guardrails & Cancellation
# -------------------------------------------------------------

def test_scheduling_missing_platform_content_rejected():
    client = TestClient(app)
    with TestingSession() as db:
        post = Post(
            topic="Strict Guardrails",
            raw_content="Content",
            target_platforms=["TWITTER", "LINKEDIN"],
            platform_contents={"TWITTER": "Valid Twitter content"}, # LINKEDIN missing!
            status=PostWorkflowStatus.APPROVED.value,
        )
        db.add(post)
        db.commit()
        db.refresh(post)
        post_id = post.id

    # Attempt scheduling for LINKEDIN should fail with 400
    tomorrow = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=1)).isoformat()
    res = client.post("/api/v1/schedules", json={
        "post_id": post_id,
        "scheduled_at": tomorrow,
        "timezone": "UTC",
        "target_platforms": ["LINKEDIN"]
    })
    assert res.status_code == 400
    assert "No platform-specific content found for 'LINKEDIN'" in res.json()["detail"]


def test_cannot_cancel_already_published_schedule():
    client = TestClient(app)
    with TestingSession() as db:
        post = Post(
            topic="Published Protection",
            raw_content="Content",
            target_platforms=["TWITTER"],
            platform_contents={"TWITTER": "Twitter content"},
            status=PostWorkflowStatus.PUBLISHED.value,
        )
        db.add(post)
        db.commit()
        db.refresh(post)

        sched = ScheduledPost(
            post_id=post.id,
            platform="TWITTER",
            target_platforms=["TWITTER"],
            job_id="job_published_test",
            idempotency_key="key_published_test",
            scheduled_at=datetime.datetime.now(datetime.timezone.utc),
            status=ScheduleStatus.PUBLISHED.value
        )
        db.add(sched)
        db.commit()
        db.refresh(sched)
        sched_id = sched.id

    # DELETE /api/v1/schedules/{id} must reject cancelling published post
    res = client.delete(f"/api/v1/schedules/{sched_id}")
    assert res.status_code == 400
    assert "already published" in res.json()["detail"].lower()


# -------------------------------------------------------------
# Test Suite 3: Publishing Execution, Multi-platform & History
# -------------------------------------------------------------

def test_immediate_publish_success_flow():
    client = TestClient(app)
    post_id = None
    sched_id = None
    with TestingSession() as db:
        post = Post(
            topic="Immediate Publish Flow",
            raw_content="Content",
            target_platforms=["TWITTER"],
            platform_contents={"TWITTER": "Immediate dispatch content"},
            status=PostWorkflowStatus.SCHEDULED.value,
        )
        db.add(post)
        db.commit()
        db.refresh(post)
        post_id = post.id

        sched = ScheduledPost(
            post_id=post.id,
            platform="TWITTER",
            target_platforms=["TWITTER"],
            job_id="job_publish_now_test",
            idempotency_key="key_publish_now_test",
            scheduled_at=datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=2),
            status=ScheduleStatus.SCHEDULED.value
        )
        db.add(sched)
        db.commit()
        db.refresh(sched)
        sched_id = sched.id

    # 1. Trigger Publish Now
    res_pub = client.post(f"/api/v1/schedules/{sched_id}/publish-now")
    assert res_pub.status_code == 200
    assert "published successfully" in res_pub.json()["message"].lower()

    # 2. Verify schedule state updated to PUBLISHED
    with TestingSession() as db:
        sched_updated = db.query(ScheduledPost).filter(ScheduledPost.id == sched_id).first()
        assert sched_updated.status == ScheduleStatus.PUBLISHED.value
        assert sched_updated.published_at is not None

        post_updated = db.query(Post).filter(Post.id == post_id).first()
        assert post_updated.status == PostWorkflowStatus.PUBLISHED.value

    # 3. Verify Publication Logs API returns execution audit trail
    res_logs = client.get(f"/api/v1/schedules/{sched_id}/logs")
    assert res_logs.status_code == 200
    logs = res_logs.json()
    assert len(logs) >= 1
    assert logs[0]["status"] in ("SUCCESS", "SIMULATED")
    assert logs[0]["provider"] == "MockPublisher"
