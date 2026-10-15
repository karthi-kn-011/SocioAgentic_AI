import os
import json
import time
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
    ActivityLog,
    get_utc_now
)
from backend.app.main import app
from backend.app.services.slack_service import (
    SlackService,
    get_slack_signing_secret
)

TEST_DB_FILE = "test_phase76_temp.db"
TEST_DATABASE_URL = f"sqlite:///./{TEST_DB_FILE}"
test_engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

TEST_SIGNING_SECRET = "test_slack_signing_secret_xyz123"


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

    # Store original settings
    orig_mock = settings.SLACK_MOCK_MODE
    orig_secret = settings.SLACK_SIGNING_SECRET
    orig_token = settings.SLACK_BOT_TOKEN
    settings.SLACK_SIGNING_SECRET = TEST_SIGNING_SECRET

    yield

    # Teardown
    settings.SLACK_MOCK_MODE = orig_mock
    settings.SLACK_SIGNING_SECRET = orig_secret
    settings.SLACK_BOT_TOKEN = orig_token

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
    """Fail-safe assertion: Ensure production social_agent.db is NEVER accessed."""
    engine_url = str(test_engine.url)
    assert "social_agent.db" not in engine_url, (
        f"CRITICAL SAFETY VIOLATION: Test is targeting the production database: {engine_url}"
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


def create_sample_post_and_approval(db, status=ApprovalStatus.PENDING.value):
    """Helper to create a Post and ApprovalRequest for test cases."""
    now = get_utc_now()
    post = Post(
        topic="AI in Healthcare",
        theme="Health Tech",
        tone="Insightful",
        raw_content="Exploring the impact of transformer models on radiology diagnosis workflows.",
        platform_contents={"TWITTER": "Exploring transformers in radiology #HealthTech"},
        target_platforms=["TWITTER", "LINKEDIN"],
        status=PostStatus.AWAITING_HUMAN_APPROVAL if status == ApprovalStatus.PENDING.value else PostStatus.APPROVED,
        review_score=92,
        review_passed=True,
        generation_version=1
    )
    db.add(post)
    db.flush()

    approval = ApprovalRequest(
        post_id=post.id,
        channel="web",
        status=status,
        requested_at=now
    )
    db.add(approval)
    db.commit()
    db.refresh(post)
    db.refresh(approval)
    return post, approval


def generate_signed_request_data(payload_dict: dict, secret: str = TEST_SIGNING_SECRET, ts_offset: int = 0):
    """Builds signed form-encoded body and corresponding Slack headers."""
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
# 1. Signature & Cryptographic Unit Tests
# ==============================================================================

def test_signature_generation_and_verification():
    """Verifies that SlackService computes and verifies valid HMAC-SHA256 signatures."""
    body = b'payload=%7B%22type%22%3A%22block_actions%22%7D'
    ts = str(int(time.time()))
    sig = SlackService.generate_signature(TEST_SIGNING_SECRET, ts, body)

    assert sig.startswith("v0=")
    assert SlackService.verify_slack_signature(TEST_SIGNING_SECRET, body, ts, sig) is True


def test_signature_verification_rejects_wrong_secret():
    """Verifies that signature verification fails when an incorrect signing secret is used."""
    body = b'payload=%7B%22type%22%3A%22block_actions%22%7D'
    ts = str(int(time.time()))
    sig = SlackService.generate_signature("wrong_secret_abc", ts, body)

    assert SlackService.verify_slack_signature(TEST_SIGNING_SECRET, body, ts, sig) is False


def test_signature_verification_rejects_altered_body():
    """Verifies that signature verification detects body tampering."""
    body = b'payload=original_content'
    ts = str(int(time.time()))
    sig = SlackService.generate_signature(TEST_SIGNING_SECRET, ts, body)

    tampered_body = b'payload=tampered_content'
    assert SlackService.verify_slack_signature(TEST_SIGNING_SECRET, tampered_body, ts, sig) is False


def test_signature_verification_rejects_missing_inputs():
    """Verifies that missing headers or empty secrets return False."""
    assert SlackService.verify_slack_signature("", b"body", "123", "v0=sig") is False
    assert SlackService.verify_slack_signature(TEST_SIGNING_SECRET, b"body", None, "v0=sig") is False
    assert SlackService.verify_slack_signature(TEST_SIGNING_SECRET, b"body", "123", None) is False


# ==============================================================================
# 2. Replay Protection & Error Handling Tests
# ==============================================================================

def test_interactions_missing_headers_rejected(client):
    """POST /slack/interactions must return 400 Bad Request when Slack headers are missing."""
    res = client.post("/api/v1/slack/interactions", content=b"payload={}")
    assert res.status_code == 400
    assert "Missing required Slack signature headers" in res.json()["detail"]


def test_interactions_stale_timestamp_rejected(client):
    """POST /slack/interactions must return 403 Forbidden when timestamp exceeds 300s replay window."""
    payload = {"type": "block_actions", "actions": [{"action_id": "approve_post", "value": "1"}]}
    # Timestamp from 305 seconds in the past
    form_body, headers = generate_signed_request_data(payload, ts_offset=-305)

    res = client.post("/api/v1/slack/interactions", content=form_body, headers=headers)
    assert res.status_code == 403
    assert "stale" in res.json()["detail"].lower()


def test_interactions_invalid_signature_rejected(client):
    """POST /slack/interactions must return 401 Unauthorized when signature does not match."""
    payload = {"type": "block_actions", "actions": [{"action_id": "approve_post", "value": "1"}]}
    form_body, headers = generate_signed_request_data(payload)
    headers["X-Slack-Signature"] = "v0=0000000000000000000000000000000000000000000000000000000000000000"

    res = client.post("/api/v1/slack/interactions", content=form_body, headers=headers)
    assert res.status_code == 401
    assert "Invalid Slack request signature" in res.json()["detail"]


# ==============================================================================
# 3. Block Kit Builders Unit Tests
# ==============================================================================

def test_build_approval_blocks(db_session):
    """Verifies the structure of the interactive approval Block Kit payload."""
    post, approval = create_sample_post_and_approval(db_session)
    blocks = SlackService.build_approval_blocks(post, approval)

    # Validate header
    assert blocks[0]["type"] == "header"
    assert f"#{post.id}" in blocks[0]["text"]["text"]

    # Validate section fields
    section_fields = blocks[1]["fields"]
    field_texts = [f["text"] for f in section_fields]
    assert any("AI in Healthcare" in t for t in field_texts)
    assert any("TWITTER" in t for t in field_texts)

    # Validate actions block with approve and reject buttons
    actions_block = next(b for b in blocks if b["type"] == "actions")
    assert actions_block["block_id"] == f"approval_actions_{approval.id}"
    elements = actions_block["elements"]
    assert len(elements) == 2
    assert elements[0]["action_id"] == "approve_post"
    assert elements[0]["value"] == str(approval.id)
    assert elements[0]["style"] == "primary"
    assert elements[1]["action_id"] == "reject_post"
    assert elements[1]["value"] == str(approval.id)
    assert elements[1]["style"] == "danger"


def test_build_resolved_blocks(db_session):
    """Verifies that resolved Block Kit blocks do NOT contain interactive action buttons."""
    post, approval = create_sample_post_and_approval(db_session)
    resolved_blocks = SlackService.build_resolved_blocks(
        post=post,
        approval=approval,
        action="APPROVED",
        reviewer="Slack: @alice"
    )

    assert resolved_blocks[0]["type"] == "header"
    assert "Approved" in resolved_blocks[0]["text"]["text"]
    # Ensure no actions block exists
    assert not any(b["type"] == "actions" for b in resolved_blocks)


# ==============================================================================
# 4. Endpoints: Dispatch & Preview Tests
# ==============================================================================

def test_dispatch_endpoint_in_mock_mode(client, db_session):
    """Verifies POST /slack/dispatch/{approval_id} in default SLACK_MOCK_MODE=True."""
    settings.SLACK_MOCK_MODE = True
    post, approval = create_sample_post_and_approval(db_session)

    res = client.post(f"/api/v1/slack/dispatch/{approval.id}")
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["mock"] is True
    assert data["message_ts"].startswith("mock_ts_")

    # Verify DB update
    db_session.refresh(approval)
    assert approval.channel == "slack"
    assert approval.message_ts.startswith("mock_ts_")

    # Verify ActivityLog
    log = db_session.query(ActivityLog).filter(
        ActivityLog.post_id == post.id,
        ActivityLog.action == "SLACK_NOTIFICATION_DISPATCHED"
    ).first()
    assert log is not None
    assert "Mock Slack approval card dispatched" in log.details


def test_preview_endpoint(client, db_session):
    """Verifies GET /slack/preview/{approval_id} returns valid Block Kit blocks."""
    post, approval = create_sample_post_and_approval(db_session)

    res = client.get(f"/api/v1/slack/preview/{approval.id}")
    assert res.status_code == 200
    data = res.json()
    assert data["approval_id"] == approval.id
    assert data["post_id"] == post.id
    assert len(data["blocks"]) >= 4


# ==============================================================================
# 5. Interactive Actions & Idempotency Tests
# ==============================================================================

def test_slack_interactive_approval_action(client, db_session):
    """Verifies approving a post via Slack interactive button callback."""
    post, approval = create_sample_post_and_approval(db_session)

    payload = {
        "type": "block_actions",
        "user": {"id": "U12345", "username": "alice", "name": "Alice Developer"},
        "actions": [
            {
                "action_id": "approve_post",
                "block_id": f"approval_actions_{approval.id}",
                "value": str(approval.id),
                "type": "button"
            }
        ],
        "response_url": "https://hooks.slack.com/actions/T123/B456/XYZ"
    }
    form_body, headers = generate_signed_request_data(payload)

    with patch.object(SlackService, "update_slack_message", return_value={"success": True}) as mock_update:
        res = client.post("/api/v1/slack/interactions", content=form_body, headers=headers)

    assert res.status_code == 200
    res_data = res.json()
    assert res_data["replace_original"] is True
    assert "APPROVED" in res_data["text"]

    # Verify DB state
    db_session.refresh(approval)
    db_session.refresh(post)
    assert approval.status == ApprovalStatus.APPROVED.value
    assert approval.reviewer == "Slack: @alice"
    assert post.status == PostStatus.APPROVED

    # Verify ActivityLog
    log = db_session.query(ActivityLog).filter(
        ActivityLog.post_id == post.id,
        ActivityLog.action == "SLACK_INTERACTION_PROCESSED"
    ).first()
    assert log is not None
    assert "@alice approved" in log.details


def test_slack_interactive_approval_idempotency(client, db_session):
    """Verifies that duplicate approval callbacks are idempotent and do not fail or publish twice."""
    post, approval = create_sample_post_and_approval(db_session)

    payload = {
        "type": "block_actions",
        "user": {"id": "U12345", "username": "alice"},
        "actions": [{"action_id": "approve_post", "value": str(approval.id)}],
        "response_url": "https://hooks.slack.com/actions/test"
    }
    form_body, headers = generate_signed_request_data(payload)

    # First approval
    res1 = client.post("/api/v1/slack/interactions", content=form_body, headers=headers)
    assert res1.status_code == 200

    # Second approval (duplicate click)
    form_body2, headers2 = generate_signed_request_data(payload)
    res2 = client.post("/api/v1/slack/interactions", content=form_body2, headers=headers2)
    assert res2.status_code == 200
    assert res2.json()["replace_original"] is True

    # Confirm post remains in APPROVED state without duplications
    db_session.refresh(approval)
    assert approval.status == ApprovalStatus.APPROVED.value

    # Verify idempotent ignore was logged
    idempotent_log = db_session.query(ActivityLog).filter(
        ActivityLog.post_id == post.id,
        ActivityLog.action == "SLACK_INTERACTION_IDEMPOTENT_IGNORED"
    ).first()
    assert idempotent_log is not None


def test_slack_interactive_rejection_action(client, db_session):
    """Verifies rejecting a post via Slack interactive button callback."""
    post, approval = create_sample_post_and_approval(db_session)

    payload = {
        "type": "block_actions",
        "user": {"id": "U99999", "username": "bob", "name": "Bob Manager"},
        "actions": [
            {
                "action_id": "reject_post",
                "value": str(approval.id),
                "reason": "Brand voice guidelines not met on radiology theme."
            }
        ],
        "response_url": "https://hooks.slack.com/actions/test"
    }
    form_body, headers = generate_signed_request_data(payload)

    res = client.post("/api/v1/slack/interactions", content=form_body, headers=headers)
    assert res.status_code == 200
    res_data = res.json()
    assert res_data["replace_original"] is True
    assert "REJECTED" in res_data["text"]

    # Verify DB state
    db_session.refresh(approval)
    db_session.refresh(post)
    assert approval.status == ApprovalStatus.REJECTED.value
    assert approval.reviewer == "Slack: @bob"
    assert "Brand voice" in approval.rejection_reason
    assert post.status == PostStatus.REJECTED


def test_slack_interactive_rejection_idempotency(client, db_session):
    """Verifies that repeated rejection clicks are idempotent."""
    post, approval = create_sample_post_and_approval(db_session)

    payload = {
        "type": "block_actions",
        "user": {"id": "U99999", "username": "bob"},
        "actions": [{"action_id": "reject_post", "value": str(approval.id)}]
    }
    form_body1, headers1 = generate_signed_request_data(payload)
    res1 = client.post("/api/v1/slack/interactions", content=form_body1, headers=headers1)
    assert res1.status_code == 200

    form_body2, headers2 = generate_signed_request_data(payload)
    res2 = client.post("/api/v1/slack/interactions", content=form_body2, headers=headers2)
    assert res2.status_code == 200


def test_live_slack_dispatch_with_mocked_http(db_session):
    """Verifies live Slack dispatch calls external Slack API when SLACK_MOCK_MODE=False and token is present."""
    settings.SLACK_MOCK_MODE = False
    settings.SLACK_BOT_TOKEN = "xoxb-mock-token-for-test"
    post, approval = create_sample_post_and_approval(db_session)

    mock_response = MagicMock()
    mock_response.json.return_value = {"ok": True, "ts": "1729001234.567890"}

    with patch("httpx.Client.post", return_value=mock_response) as mock_post:
        result = SlackService.dispatch_approval_card(db=db_session, approval_id=approval.id)

    assert result["success"] is True
    assert result["mock"] is False
    assert result["message_ts"] == "1729001234.567890"

    # Verify httpx called with Bearer token
    mock_post.assert_called_once()
    call_kwargs = mock_post.call_args[1]
    assert call_kwargs["headers"]["Authorization"] == "Bearer xoxb-mock-token-for-test"
    assert "blocks" in call_kwargs["json"]

    # Restore mock setting
    settings.SLACK_MOCK_MODE = True
