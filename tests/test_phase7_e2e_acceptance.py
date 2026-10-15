import os
import json
import time
import asyncio
import datetime
import urllib.parse
from unittest.mock import patch, MagicMock
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.config import settings
from backend.app.database.database import Base, get_db
from backend.app.database.models import (
    Post,
    PostStatus,
    ApprovalRequest,
    ApprovalStatus,
    ScheduledPost,
    PublishLog,
    ActivityLog,
    SocialAccount,
    OAuthState,
    get_utc_now
)
from backend.app.main import app
from backend.app.services.content_service import ContentService
from backend.app.services.approval_service import ApprovalService
from backend.app.services.schedule_service import ScheduleService
from backend.app.services.publishing_service import PublishingService
from backend.app.services.slack_service import SlackService
from backend.app.schemas.post import GeneratePostRequest

TEST_DB_FILE = "test_phase7_e2e_temp.db"
TEST_DATABASE_URL = f"sqlite:///./{TEST_DB_FILE}"
test_engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

TEST_SIGNING_SECRET = "test_e2e_slack_secret_987"


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(scope="module", autouse=True)
def setup_test_environment():
    """Sets up the isolated test SQLite database and strictly asserts no access to social_agent.db."""
    if os.path.exists(TEST_DB_FILE):
        try:
            os.remove(TEST_DB_FILE)
        except Exception:
            pass

    Base.metadata.create_all(bind=test_engine)
    app.dependency_overrides[get_db] = override_get_db

    orig_mock_social = settings.MOCK_SOCIAL_PUBLISHING
    orig_mock_slack = settings.SLACK_MOCK_MODE
    orig_secret = settings.SLACK_SIGNING_SECRET

    settings.MOCK_SOCIAL_PUBLISHING = True
    settings.SLACK_MOCK_MODE = True
    settings.SLACK_SIGNING_SECRET = TEST_SIGNING_SECRET

    yield

    settings.MOCK_SOCIAL_PUBLISHING = orig_mock_social
    settings.SLACK_MOCK_MODE = orig_mock_slack
    settings.SLACK_SIGNING_SECRET = orig_secret

    app.dependency_overrides.pop(get_db, None)
    Base.metadata.drop_all(bind=test_engine)
    test_engine.dispose()
    if os.path.exists(TEST_DB_FILE):
        try:
            os.remove(TEST_DB_FILE)
        except Exception:
            pass


@pytest.fixture(autouse=True)
def verify_test_isolation():
    """Hard assertion ensuring the active database is never touched."""
    engine_url = str(test_engine.url)
    assert "social_agent.db" not in engine_url, (
        f"CRITICAL SAFETY VIOLATION: Test targeting active database: {engine_url}"
    )


@pytest.fixture
def db_session():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def client():
    return TestClient(app)


def sign_slack_payload(payload_dict: dict, secret: str = TEST_SIGNING_SECRET, ts_offset: int = 0):
    form_body = urllib.parse.urlencode({"payload": json.dumps(payload_dict)}).encode("utf-8")
    timestamp = str(int(time.time()) + ts_offset)
    signature = SlackService.generate_signature(secret, timestamp, form_body)
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "X-Slack-Request-Timestamp": timestamp,
        "X-Slack-Signature": signature
    }
    return form_body, headers


# ==============================================================================
# End-to-End Acceptance Gate Tests
# ==============================================================================

def test_full_lifecycle_generation_to_slack_to_schedule_to_publish(db_session, client):
    """Verifies the unbroken end-to-end lifecycle:
    1. Content Generation (Mock Provider)
    2. Auto-dispatch of Slack notification card
    3. Slack interactive approval callback with HMAC verification
    4. Scheduling post to calendar slot
    5. Cancellation and rescheduling
    6. Mock publishing execution with audit verification
    """
    # 1. Content Generation
    gen_req = GeneratePostRequest(
        topic="Autonomous AI Systems in 2026",
        theme="Artificial Intelligence",
        platforms=["TWITTER", "LINKEDIN"],
        tone="Thought Leadership",
        provider="mock"
    )
    post_result = asyncio.run(ContentService.generate_post(gen_req, db_session))
    assert post_result.post_id is not None
    assert str(post_result.status).upper() == "AWAITING_HUMAN_APPROVAL"

    # 2. Verify Post & ApprovalRequest in DB
    post = db_session.query(Post).filter(Post.id == post_result.post_id).first()
    assert post is not None
    approval = db_session.query(ApprovalRequest).filter(ApprovalRequest.post_id == post.id).first()
    assert approval is not None
    assert approval.status == ApprovalStatus.PENDING.value
    assert approval.channel == "slack"
    assert approval.message_ts.startswith("mock_ts_")

    # 3. Slack Interactive Approval with HMAC verification
    slack_payload = {
        "type": "block_actions",
        "user": {"id": "U12345", "username": "e2e_reviewer"},
        "actions": [{"action_id": "approve_post", "value": str(approval.id)}],
        "response_url": "https://hooks.slack.com/actions/e2e"
    }
    form_body, headers = sign_slack_payload(slack_payload)
    res_slack = client.post("/api/v1/slack/interactions", content=form_body, headers=headers)
    assert res_slack.status_code == 200
    assert res_slack.json()["replace_original"] is True
    assert "APPROVED" in res_slack.json()["text"]

    db_session.refresh(approval)
    db_session.refresh(post)
    assert approval.status == ApprovalStatus.APPROVED.value
    assert post.status == PostStatus.APPROVED

    # Duplicate Slack click (Idempotency)
    res_slack_dup = client.post("/api/v1/slack/interactions", content=form_body, headers=headers)
    assert res_slack_dup.status_code == 200
    assert res_slack_dup.json()["replace_original"] is True

    # 4. Schedule Post
    future_time = get_utc_now() + datetime.timedelta(hours=2)
    schedule_payload = {
        "post_id": post.id,
        "scheduled_at": future_time.isoformat(),
        "platforms": ["TWITTER", "LINKEDIN"],
        "timezone": "UTC"
    }
    res_sched = client.post("/api/v1/schedules", json=schedule_payload)
    assert res_sched.status_code == 201
    sched_data = res_sched.json()
    schedule_id = sched_data["id"] if "id" in sched_data else sched_data["schedules"][0]["id"]

    # 5. Cancel Schedule
    res_cancel = client.delete(f"/api/v1/schedules/{schedule_id}?cancel_all=true")
    assert res_cancel.status_code == 200

    # Verify cancelled schedule
    sched_record = db_session.query(ScheduledPost).filter(ScheduledPost.id == schedule_id).first()
    assert sched_record.status == "CANCELLED"

    # 6. Reschedule Post
    new_future_time = get_utc_now() + datetime.timedelta(hours=4)
    res_resched = client.post("/api/v1/schedules", json={
        "post_id": post.id,
        "scheduled_at": new_future_time.isoformat(),
        "platforms": ["TWITTER"],
        "timezone": "UTC"
    })
    assert res_resched.status_code == 201
    new_sched_data = res_resched.json()
    new_sched_id = new_sched_data["id"] if "id" in new_sched_data else new_sched_data["schedules"][0]["id"]

    # 7. Publish Now (Mock Publishing Guardrail)
    res_pub = client.post(f"/api/v1/schedules/{new_sched_id}/publish-now")
    assert res_pub.status_code == 200
    pub_data = res_pub.json()
    assert pub_data["success"] is True

    # Verify PublishLog and Post status
    pub_log = db_session.query(PublishLog).filter(PublishLog.post_id == post.id).first()
    assert pub_log is not None
    assert pub_log.status in ("SUCCESS", "SIMULATED")


def test_connected_accounts_endpoint_reports_all_platforms(client):
    """Verifies GET /api/v1/auth/accounts reports consistent structure for all four social platforms."""
    res = client.get("/api/v1/auth/accounts")
    assert res.status_code == 200
    data = res.json()
    assert "accounts" in data
    accounts = data["accounts"]
    # Keys in response are uppercase platform constants
    assert "TWITTER" in accounts
    assert "LINKEDIN" in accounts
    assert "META_FACEBOOK" in accounts
    assert "META_INSTAGRAM" in accounts

    for plat_key, acc in accounts.items():
        assert "connected" in acc
        assert "account_name" in acc


def test_oauth_security_guardrails(client, db_session):
    """Verifies that invalid, replayed, or expired OAuth callbacks are strictly rejected."""
    # 1. Non-existent state
    res1 = client.get("/api/v1/auth/twitter/callback?code=mock_code&state=non_existent_state")
    assert res1.status_code == 400
    assert "error" in res1.text.lower() or "invalid" in res1.text.lower()

    # 2. Expired state
    expired_state = OAuthState(
        state="expired_test_state_tok",
        platform="TWITTER",
        code_verifier="test_verifier_abc",
        redirect_uri="http://localhost:8000/api/v1/auth/twitter/callback",
        expires_at=time.time() - 60.0
    )
    db_session.add(expired_state)
    db_session.commit()

    res2 = client.get(f"/api/v1/auth/twitter/callback?code=mock_code&state={expired_state.state}")
    assert res2.status_code == 400
    assert "expired" in res2.text.lower() or "error" in res2.text.lower()

    # 3. Platform mismatch
    mismatch_state = OAuthState(
        state="mismatch_test_state_tok",
        platform="LINKEDIN",
        code_verifier="test_verifier_xyz",
        redirect_uri="http://localhost:8000/api/v1/auth/linkedin/callback",
        expires_at=time.time() + 600.0
    )
    db_session.add(mismatch_state)
    db_session.commit()

    # Attempting to use LinkedIn state for Twitter callback
    res3 = client.get(f"/api/v1/auth/twitter/callback?code=mock_code&state={mismatch_state.state}")
    assert res3.status_code == 400
    assert "platform mismatch" in res3.text.lower() or "error" in res3.text.lower()


def test_slack_security_guardrails(client):
    """Verifies that invalid Slack signatures and stale timestamps are rejected."""
    payload = {"type": "block_actions", "actions": [{"action_id": "approve_post", "value": "1"}]}

    # 1. Missing headers
    res1 = client.post("/api/v1/slack/interactions", content=b"payload={}")
    assert res1.status_code == 400

    # 2. Stale timestamp (replay attack)
    form_body, headers = sign_slack_payload(payload, ts_offset=-350)
    res2 = client.post("/api/v1/slack/interactions", content=form_body, headers=headers)
    assert res2.status_code == 403
    assert "stale" in res2.json()["detail"].lower()

    # 3. Invalid signature
    form_body, headers = sign_slack_payload(payload)
    headers["X-Slack-Signature"] = "v0=bad_hex_signature_abcdef123456"
    res3 = client.post("/api/v1/slack/interactions", content=form_body, headers=headers)
    assert res3.status_code == 401
    assert "Invalid Slack request signature" in res3.json()["detail"]
