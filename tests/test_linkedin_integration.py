import os
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.config import settings
from backend.app.database.models import Base, OAuthState, SocialAccount, PlatformType, Post
from backend.app.database.database import get_db
from backend.app.main import app
from backend.app.auth.oauth_service import OAuthService
from backend.app.auth.linkedin_oauth import LinkedInOAuthService
from backend.app.auth.security import token_security
from backend.app.publishers.registry import PublisherRegistry
from backend.app.publishers.linkedin_publisher import LinkedInPublisher
from backend.app.publishers.mock_publisher import MockPublisher

TEST_DB_FILE = "test_phase73_temp.db"
TEST_DATABASE_URL = f"sqlite:///./{TEST_DB_FILE}"

test_engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False}
)
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture(scope="session", autouse=True)
def setup_test_database():
    """Ensures test database is created, verified as isolated, and cleaned up after test run."""
    assert "social_agent.db" not in TEST_DATABASE_URL, "CRITICAL SAFETY VIOLATION: Test targeting active database!"
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)
    if os.path.exists(TEST_DB_FILE):
        try:
            os.remove(TEST_DB_FILE)
        except Exception:
            pass


@pytest.fixture
def db_session():
    """Provides an isolated database session for each test and rolls back changes."""
    session = TestSessionLocal()
    # Explicit isolation assertion
    engine_url = str(session.get_bind().url)
    assert "social_agent.db" not in engine_url, f"SAFETY VIOLATION: Database session points to {engine_url}"
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(db_session):
    """Provides a FastAPI TestClient bound to the isolated test database."""
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


# =========================================================================
# 1. DATABASE ISOLATION & UNIT TESTS
# =========================================================================

def test_database_isolation_guardrail(db_session):
    """Confirms tests strictly run on the isolated temporary database."""
    url = str(db_session.get_bind().url)
    assert "social_agent.db" not in url
    assert TEST_DB_FILE in url


def test_linkedin_build_authorization_url():
    """Verifies LinkedIn authorization URL contains expected parameters and scopes."""
    url = LinkedInOAuthService.build_authorization_url(
        state="test_li_state_123",
        redirect_uri="http://localhost:8000/api/v1/auth/linkedin/callback"
    )
    assert "https://www.linkedin.com/oauth/v2/authorization" in url
    assert "response_type=code" in url
    assert "state=test_li_state_123" in url
    assert "redirect_uri=http%3A%2F%2Flocalhost%3A8000%2Fapi%2Fv1%2Fauth%2Flinkedin%2Fcallback" in url
    assert "w_member_social" in url
    assert "openid" in url


def test_linkedin_post_payload_formatting():
    """Verifies LinkedIn Posts REST API payload structure."""
    payload = LinkedInOAuthService.format_post_payload(
        author_urn="urn:li:person:abcdef1234",
        commentary="Excited to share our latest product update with the community!"
    )
    assert payload["author"] == "urn:li:person:abcdef1234"
    assert payload["commentary"] == "Excited to share our latest product update with the community!"
    assert payload["visibility"] == "PUBLIC"
    assert payload["distribution"]["feedDistribution"] == "MAIN_FEED"
    assert payload["lifecycleState"] == "PUBLISHED"


# =========================================================================
# 2. LINKEDIN OAUTH ENDPOINT TESTS
# =========================================================================

def test_linkedin_authorize_endpoint(client, db_session):
    """Verifies /auth/linkedin/authorize returns valid authorization URL and persists state."""
    resp = client.get("/api/v1/auth/linkedin/authorize")
    assert resp.status_code == 200
    data = resp.json()
    assert "authorization_url" in data
    assert "state" in data
    assert "https://www.linkedin.com/oauth/v2/authorization" in data["authorization_url"]

    # Verify state record in DB
    state_rec = db_session.query(OAuthState).filter(OAuthState.state == data["state"]).first()
    assert state_rec is not None
    assert state_rec.platform == "LINKEDIN"


def test_linkedin_callback_success_mocked(client, db_session):
    """Verifies callback with mocked LinkedIn token exchange and profile retrieval."""
    # Create valid OAuthState
    state_rec = OAuthService.create_oauth_state(
        db=db_session,
        platform="LINKEDIN",
        redirect_uri=settings.LINKEDIN_REDIRECT_URI,
        ttl_seconds=600,
    )

    mock_token_resp = {
        "access_token": "mock_li_access_token_9999",
        "expires_in": 5184000,
        "refresh_token": "mock_li_refresh_token_8888",
        "scope": "openid profile email w_member_social",
    }
    mock_profile_resp = {
        "account_id": "urn:li:person:782bbcs283",
        "username": "Jane Doe",
        "email": "jane@example.com",
        "sub": "782bbcs283",
    }

    with patch("backend.app.auth.linkedin_oauth.LinkedInOAuthService.exchange_code_for_token", return_value=mock_token_resp), \
         patch("backend.app.auth.linkedin_oauth.LinkedInOAuthService.fetch_user_profile", return_value=mock_profile_resp):

        resp = client.get(f"/api/v1/auth/linkedin/callback?code=mock_li_code&state={state_rec.state}")
        assert resp.status_code == 200
        html = resp.text

        # Verify safe popup response targeting FRONTEND_ORIGIN
        assert settings.FRONTEND_ORIGIN in html
        assert "SOCIAL_AGENT_OAUTH_CALLBACK" in html
        assert "Jane Doe" in html
        assert "SUCCESS" in html

        # Verify account in DB
        account = db_session.query(SocialAccount).filter(SocialAccount.platform == PlatformType.LINKEDIN).first()
        assert account is not None
        assert account.account_name == "Jane Doe"
        assert account.account_id == "urn:li:person:782bbcs283"
        assert account.is_active is True

        # Verify encrypted tokens at rest
        assert account.encrypted_access_token != "mock_li_access_token_9999"
        decrypted = token_security.decrypt(account.encrypted_access_token)
        assert decrypted == "mock_li_access_token_9999"


def test_linkedin_callback_provider_error(client):
    """Verifies error in callback query params returns error HTML payload."""
    resp = client.get("/api/v1/auth/linkedin/callback?error=user_cancelled_login&error_description=User+declined")
    assert resp.status_code == 400
    html = resp.text
    assert "User declined" in html
    assert "Authentication Failed" in html


def test_linkedin_callback_atomic_consumption_replay_rejection(client, db_session):
    """Verifies that duplicate callback requests with the same state are rejected."""
    state_rec = OAuthService.create_oauth_state(
        db=db_session,
        platform="LINKEDIN",
        redirect_uri=settings.LINKEDIN_REDIRECT_URI,
        ttl_seconds=600,
    )
    state_val = state_rec.state

    mock_token_resp = {"access_token": "tok_1", "expires_in": 3600}
    mock_profile_resp = {"account_id": "urn:li:person:p1", "username": "Member1"}

    with patch("backend.app.auth.linkedin_oauth.LinkedInOAuthService.exchange_code_for_token", return_value=mock_token_resp), \
         patch("backend.app.auth.linkedin_oauth.LinkedInOAuthService.fetch_user_profile", return_value=mock_profile_resp):

        # First request succeeds
        resp1 = client.get(f"/api/v1/auth/linkedin/callback?code=c1&state={state_val}")
        assert resp1.status_code == 200

        # Second request with identical state must be rejected
        resp2 = client.get(f"/api/v1/auth/linkedin/callback?code=c2&state={state_val}")
        assert resp2.status_code == 400
        assert "already consumed" in resp2.text or "Invalid" in resp2.text


def test_linkedin_disconnect_endpoint(client, db_session):
    """Verifies /auth/linkedin/disconnect deactivates account and scrubs tokens."""
    OAuthService.upsert_social_account(
        db=db_session,
        platform=PlatformType.LINKEDIN,
        account_name="Jane Doe",
        account_id="urn:li:person:782bbcs283",
        access_token="plain_li_token",
    )

    resp = client.post("/api/v1/auth/linkedin/disconnect")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True

    # Confirm in DB
    acc = db_session.query(SocialAccount).filter(SocialAccount.platform == PlatformType.LINKEDIN).first()
    assert acc.is_active is False
    assert acc.encrypted_access_token is None
    assert acc.encrypted_refresh_token is None


# =========================================================================
# 3. PUBLISHER GUARDRAIL & STATUS TESTS
# =========================================================================

def test_linkedin_publisher_mock_mode_guardrail():
    """Verifies LinkedInPublisher delegates strictly to MockPublisher when MOCK_SOCIAL_PUBLISHING=True."""
    settings.MOCK_SOCIAL_PUBLISHING = True
    publisher = LinkedInPublisher()

    dummy_post = MagicMock()
    dummy_post.platform = "LINKEDIN"
    dummy_post.get_platform_content.return_value = "Thought leadership piece on AI innovations."

    res = publisher.publish(post=dummy_post)
    assert res.is_mock is True
    assert res.provider == "MockPublisher"
    assert res.status in ("SUCCESS", "SIMULATED")


def test_linkedin_publisher_live_mode_missing_account():
    """Verifies that in live mode (mock=False), missing connected account safely returns FAILED."""
    settings.MOCK_SOCIAL_PUBLISHING = False
    try:
        publisher = LinkedInPublisher()
        dummy_post = MagicMock()
        dummy_post.platform = "LINKEDIN"
        dummy_post.get_platform_content.return_value = "Valid LinkedIn content"

        # Database has no active LinkedIn account in this test session
        res = publisher.publish(post=dummy_post)
        assert res.status == "FAILED"
        assert res.is_mock is False
        assert "No active connected LinkedIn account found" in (res.error_message or "")
    finally:
        settings.MOCK_SOCIAL_PUBLISHING = True  # Restore safe mock mode


def test_accounts_status_reports_both_x_and_linkedin(client, db_session):
    """Verifies /auth/accounts reports accurate status for both X and LinkedIn simultaneously."""
    # Seed X account as active
    OAuthService.upsert_social_account(
        db=db_session,
        platform=PlatformType.TWITTER,
        account_name="BrandX",
        account_id="tw_101",
        access_token="tok_x",
    )
    # Seed LinkedIn account as active
    OAuthService.upsert_social_account(
        db=db_session,
        platform=PlatformType.LINKEDIN,
        account_name="BrandLeader",
        account_id="urn:li:person:li_202",
        access_token="tok_li",
    )

    resp = client.get("/api/v1/auth/accounts")
    assert resp.status_code == 200
    accounts = resp.json()["accounts"]

    assert accounts["TWITTER"]["connected"] is True
    assert accounts["TWITTER"]["account_name"] == "BrandX"

    assert accounts["LINKEDIN"]["connected"] is True
    assert accounts["LINKEDIN"]["account_name"] == "BrandLeader"

    assert accounts["META_FACEBOOK"]["connected"] is False
    assert accounts["META_INSTAGRAM"]["connected"] is False
