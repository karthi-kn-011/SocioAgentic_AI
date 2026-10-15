import pytest
import datetime
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from backend.app.database.database import Base, get_db
from backend.app.database.models import (
    Post, ScheduledPost, PostWorkflowStatus, ScheduleStatus, ApprovalRequest, ApprovalStatus, PublishLog
)
from backend.app.services.schedule_service import ScheduleService
from backend.app.services.publishing_service import PublishingService
from backend.app.main import app

TEST_DB_URL = "sqlite:///./test_cancel_resched_temp.db"
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
    if os.path.exists("./test_cancel_resched_temp.db"):
        try:
            os.remove("./test_cancel_resched_temp.db")
        except OSError:
            pass


def test_approve_schedule_cancel_schedule_again_lifecycle():
    """Requirement 1, 2, 3: Approve -> Schedule -> Cancel -> Schedule again succeeds,
    preserving the cancelled schedule in history and activating the new schedule in the calendar.
    """
    client = TestClient(app)

    with TestingSession() as db:
        post = Post(
            topic="Next Gen Automation",
            raw_content="Content",
            target_platforms=["TWITTER"],
            platform_contents={"TWITTER": "Valid Twitter variant content"},
            status=PostWorkflowStatus.APPROVED.value,
        )
        db.add(post)
        db.commit()
        db.refresh(post)

        approval = ApprovalRequest(
            post_id=post.id,
            status=ApprovalStatus.APPROVED.value,
            reviewer="Human Admin",
            reviewed_at=datetime.datetime.now(datetime.timezone.utc),
        )
        db.add(approval)
        db.commit()
        post_id = post.id

    # 1. Schedule the post
    target_time = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=2)).isoformat()
    res1 = client.post("/api/v1/schedules", json={
        "post_id": post_id,
        "scheduled_at": target_time,
        "timezone": "UTC",
        "target_platforms": ["TWITTER"]
    })
    assert res1.status_code == 201
    sched1_data = res1.json()
    sched1_id = sched1_data["id"]
    assert sched1_data["status"] == "SCHEDULED"

    # Verify calendar shows sched1
    cal_res1 = client.get("/api/v1/schedules")
    assert cal_res1.status_code == 200
    assert any(s["id"] == sched1_id and s["status"] == "SCHEDULED" for s in cal_res1.json()["data"])

    # 2. Cancel the schedule
    res_cancel = client.delete(f"/api/v1/schedules/{sched1_id}?cancel_all=true")
    assert res_cancel.status_code == 200
    cancel_data = res_cancel.json()
    assert cancel_data["success"] is True

    # Verify post status reverted to APPROVED
    with TestingSession() as db:
        p = db.query(Post).filter(Post.id == post_id).first()
        assert p.status == PostWorkflowStatus.APPROVED.value

    # Verify sched1 is CANCELLED in history
    cal_res_hist = client.get("/api/v1/schedules?include_cancelled=true")
    assert cal_res_hist.status_code == 200
    cancelled_found = next((s for s in cal_res_hist.json()["data"] if s["id"] == sched1_id), None)
    assert cancelled_found is not None
    assert cancelled_found["status"] == "CANCELLED"

    # 3. Schedule the post AGAIN (same date/time)
    res2 = client.post("/api/v1/schedules", json={
        "post_id": post_id,
        "scheduled_at": target_time,
        "timezone": "UTC",
        "target_platforms": ["TWITTER"]
    })
    assert res2.status_code == 201
    sched2_data = res2.json()
    sched2_id = sched2_data["id"]
    assert sched2_id != sched1_id
    assert sched2_data["status"] == "SCHEDULED"

    # Verify calendar displays the new active schedule
    cal_res2 = client.get("/api/v1/schedules")
    assert cal_res2.status_code == 200
    active_ids = [s["id"] for s in cal_res2.json()["data"] if s["status"] == "SCHEDULED"]
    assert sched2_id in active_ids


def test_repeated_cancellation_idempotency():
    """Requirement 4: Repeated cancellation is idempotent and does not corrupt post status."""
    client = TestClient(app)

    with TestingSession() as db:
        post = Post(
            topic="Idempotency Test",
            raw_content="Content",
            target_platforms=["TWITTER"],
            platform_contents={"TWITTER": "Twitter variant"},
            status=PostWorkflowStatus.APPROVED.value,
        )
        db.add(post)
        db.commit()
        db.refresh(post)

        approval = ApprovalRequest(
            post_id=post.id,
            status=ApprovalStatus.APPROVED.value,
            reviewer="Admin",
            reviewed_at=datetime.datetime.now(datetime.timezone.utc),
        )
        db.add(approval)
        db.commit()
        post_id = post.id

    target_time = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=2)).isoformat()
    res = client.post("/api/v1/schedules", json={
        "post_id": post_id,
        "scheduled_at": target_time,
        "timezone": "UTC",
        "target_platforms": ["TWITTER"]
    })
    sched_id = res.json()["id"]

    # First cancellation
    cancel1 = client.delete(f"/api/v1/schedules/{sched_id}")
    assert cancel1.status_code == 200

    # Second cancellation (idempotent repeat)
    cancel2 = client.delete(f"/api/v1/schedules/{sched_id}")
    assert cancel2.status_code == 200

    with TestingSession() as db:
        p = db.query(Post).filter(Post.id == post_id).first()
        assert p.status == PostWorkflowStatus.APPROVED.value


def test_multi_platform_partial_cancellation():
    """Requirement 5 & 6: Cancelling one platform does not cancel other active platform schedules,
    and post with remaining active schedule remains SCHEDULED.
    """
    client = TestClient(app)

    with TestingSession() as db:
        post = Post(
            topic="Multi Platform Partial Cancellation",
            raw_content="Content",
            target_platforms=["TWITTER", "LINKEDIN"],
            platform_contents={"TWITTER": "Tw", "LINKEDIN": "Li"},
            status=PostWorkflowStatus.APPROVED.value,
        )
        db.add(post)
        db.commit()
        db.refresh(post)

        approval = ApprovalRequest(
            post_id=post.id,
            status=ApprovalStatus.APPROVED.value,
            reviewer="Admin",
            reviewed_at=datetime.datetime.now(datetime.timezone.utc),
        )
        db.add(approval)
        db.commit()
        post_id = post.id

    target_time = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=2)).isoformat()
    res = client.post("/api/v1/schedules", json={
        "post_id": post_id,
        "scheduled_at": target_time,
        "timezone": "UTC",
        "target_platforms": ["TWITTER", "LINKEDIN"]
    })
    assert res.status_code == 201

    with TestingSession() as db:
        scheds = db.query(ScheduledPost).filter(ScheduledPost.post_id == post_id).all()
        assert len(scheds) == 2
        tw_sched = next(s for s in scheds if s.platform == "TWITTER")
        li_sched = next(s for s in scheds if s.platform == "LINKEDIN")
        tw_id = tw_sched.id
        li_id = li_sched.id

    # Cancel only Twitter without cancel_all
    cancel_tw = client.delete(f"/api/v1/schedules/{tw_id}")
    assert cancel_tw.status_code == 200

    with TestingSession() as db:
        p = db.query(Post).filter(Post.id == post_id).first()
        tw = db.query(ScheduledPost).filter(ScheduledPost.id == tw_id).first()
        li = db.query(ScheduledPost).filter(ScheduledPost.id == li_id).first()

        assert tw.status == "CANCELLED"
        assert li.status == "SCHEDULED"
        # Post status must NOT be reset to APPROVED because LinkedIn remains active!
        assert p.status == PostWorkflowStatus.SCHEDULED.value

    # Now cancel LinkedIn schedule
    cancel_li = client.delete(f"/api/v1/schedules/{li_id}")
    assert cancel_li.status_code == 200

    with TestingSession() as db:
        p = db.query(Post).filter(Post.id == post_id).first()
        li = db.query(ScheduledPost).filter(ScheduledPost.id == li_id).first()

        assert li.status == "CANCELLED"
        # Now that ALL schedules are cancelled, post status reverts to APPROVED!
        assert p.status == PostWorkflowStatus.APPROVED.value


def test_published_schedule_cannot_be_cancelled():
    """Requirement 7: Published schedules cannot be cancelled and remain unchanged."""
    client = TestClient(app)

    with TestingSession() as db:
        post = Post(
            topic="Published Protection Test",
            raw_content="Content",
            target_platforms=["TWITTER"],
            platform_contents={"TWITTER": "Tw text"},
            status=PostWorkflowStatus.PUBLISHED.value,
        )
        db.add(post)
        db.commit()
        db.refresh(post)

        sched = ScheduledPost(
            post_id=post.id,
            platform="TWITTER",
            status=ScheduleStatus.PUBLISHED.value,
            scheduled_at=datetime.datetime.now(datetime.timezone.utc),
            published_at=datetime.datetime.now(datetime.timezone.utc),
            timezone="UTC"
        )
        db.add(sched)
        db.commit()
        sched_id = sched.id

    res = client.delete(f"/api/v1/schedules/{sched_id}")
    assert res.status_code == 400
    assert "already published" in res.json()["detail"].lower()


def test_unapproved_or_rejected_cannot_be_scheduled():
    """Requirement 8: Unapproved, draft, or rejected posts cannot bypass approval rules."""
    client = TestClient(app)

    with TestingSession() as db:
        post_draft = Post(
            topic="Draft Post",
            raw_content="Content",
            target_platforms=["TWITTER"],
            platform_contents={"TWITTER": "Draft text"},
            status=PostWorkflowStatus.DRAFT.value,
        )
        post_rejected = Post(
            topic="Rejected Post",
            raw_content="Content",
            target_platforms=["TWITTER"],
            platform_contents={"TWITTER": "Rejected text"},
            status=PostWorkflowStatus.REJECTED.value,
        )
        db.add_all([post_draft, post_rejected])
        db.commit()
        draft_id = post_draft.id
        rejected_id = post_rejected.id

    target_time = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=2)).isoformat()

    res_draft = client.post("/api/v1/schedules", json={
        "post_id": draft_id,
        "scheduled_at": target_time,
        "timezone": "UTC",
        "target_platforms": ["TWITTER"]
    })
    assert res_draft.status_code == 400
    assert "only approved posts can be scheduled" in res_draft.json()["detail"].lower()

    res_rejected = client.post("/api/v1/schedules", json={
        "post_id": rejected_id,
        "scheduled_at": target_time,
        "timezone": "UTC",
        "target_platforms": ["TWITTER"]
    })
    assert res_rejected.status_code == 400
    assert "only approved posts can be scheduled" in res_rejected.json()["detail"].lower()


def test_idempotent_duplicate_request_protection():
    """Requirement 9: Identical repeated scheduling calls return active schedule idempotently without duplicate rows."""
    client = TestClient(app)

    with TestingSession() as db:
        post = Post(
            topic="Idempotency Protection",
            raw_content="Content",
            target_platforms=["TWITTER"],
            platform_contents={"TWITTER": "Tw copy"},
            status=PostWorkflowStatus.APPROVED.value,
        )
        db.add(post)
        db.commit()
        db.refresh(post)

        approval = ApprovalRequest(
            post_id=post.id,
            status=ApprovalStatus.APPROVED.value,
            reviewer="Admin",
            reviewed_at=datetime.datetime.now(datetime.timezone.utc),
        )
        db.add(approval)
        db.commit()
        post_id = post.id

    target_time = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=2)).isoformat()
    payload = {
        "post_id": post_id,
        "scheduled_at": target_time,
        "timezone": "UTC",
        "target_platforms": ["TWITTER"],
        "idempotency_key": "custom_idem_key_123"
    }

    # Call 1
    res1 = client.post("/api/v1/schedules", json=payload)
    assert res1.status_code == 201
    sched1_id = res1.json()["id"]

    # Call 2 (repeated call with same key and slot)
    res2 = client.post("/api/v1/schedules", json=payload)
    assert res2.status_code == 201
    sched2_id = res2.json()["id"]

    # Must return identical schedule id, not duplicate row
    assert sched1_id == sched2_id

    with TestingSession() as db:
        rows = db.query(ScheduledPost).filter(ScheduledPost.post_id == post_id).all()
        assert len(rows) == 1
