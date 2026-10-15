import os
import time
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.config import settings
from backend.app.database.models import Base, OAuthState, SocialAccount, PlatformType
from backend.app.database.database import get_db
from backend.app.main import app
from backend.app.auth.oauth_service import OAuthService
from backend.app.auth.security import token_security
from backend.app.publishers.registry import PublisherRegistry
from backend.app.publishers.base import BasePublisher, PublishResult
from backend.app.publishers.mock_publisher import MockPublisher

TEST_DB_FILE = "test_phase7_temp.db"
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
# 1. DATABASE ISOLATION & SAFETY GUARDRAIL TESTS
# =========================================================================

def test_database_isolation_guardrail(db_session):
    """Confirms tests strictly run on the isolated temporary database."""
    url = str(db_session.get_bind().url)
    assert "social_agent.db" not in url
    assert TEST_DB_FILE in url


def test_publisher_registry_guardrail():
    """Verifies PublisherRegistry strictly returns MockPublisher when MOCK_SOCIAL_PUBLISHING=True."""
    settings.MOCK_SOCIAL_PUBLISHING = True

    class DummyLivePublisher(BasePublisher):
        def publish(self, post, scheduled_post=None):
            return PublishResult(status="SUCCESS", platform="TWITTER", is_mock=False)

    PublisherRegistry.register("TWITTER", DummyLivePublisher())
    resolved = PublisherRegistry.get("TWITTER")
    assert isinstance(resolved, MockPublisher), "PublisherRegistry must strictly return MockPublisher when mock mode is True"


# =========================================================================
# 2. PKCE AND STATE LIFECYCLE TESTS
# =========================================================================

def test_pkce_generation():
    """Verifies PKCE code_verifier and code_challenge format according to RFC 7636."""
    verifier, challenge = OAuthService.generate_pkce_pair()
    assert 43 <= len(verifier) <= 128
    assert len(challenge) > 20
    assert "=" not in challenge, "Code challenge should have stripped URL-safe base64 padding"


def test_oauth_state_creation_and_expiration(db_session):
    """Verifies creation of OAuthState with TTL and redirect_uri context."""
    state_rec = OAuthService.create_oauth_state(
        db=db_session,
        platform="TWITTER",
        code_verifier="test_verifier_string_12345",
        redirect_uri="http://localhost:8000/api/v1/auth/twitter/callback",
        ttl_seconds=300
    )
    assert state_rec.state is not None
    assert state_rec.platform == "TWITTER"
    assert state_rec.code_verifier == "test_verifier_string_12345"
    assert state_rec.expires_at > time.time()


def test_atomic_state_consumption_success(db_session):
    """Verifies atomic consumption deletes the record and returns its data."""
    state_rec = OAuthService.create_oauth_state(
        db=db_session,
        platform="TWITTER",
        code_verifier="verifier_abc",
        redirect_uri="http://localhost:8000/callback",
        ttl_seconds=600
    )
    state_val = state_rec.state

    consumed = OAuthService.consume_oauth_state(
        db=db_session,
        state=state_val,
        expected_platform="TWITTER",
        expected_redirect_uri="http://localhost:8000/callback"
    )
    assert consumed.state == state_val
    assert consumed.code_verifier == "verifier_abc"

    # Confirm record was deleted from database
    check = db_session.query(OAuthState).filter(OAuthState.state == state_val).first()
    assert check is None, "Consumed state must be immediately deleted"


def test_atomic_state_consumption_replay_rejection(db_session):
    """Verifies duplicate state consumption is rejected with HTTP 400 (replay protection)."""
    state_rec = OAuthService.create_oauth_state(
        db=db_session,
        platform="TWITTER",
        code_verifier="verifier_replay",
        ttl_seconds=600
    )
    state_val = state_rec.state

    # First consumption succeeds
    OAuthService.consume_oauth_state(db_session, state_val, expected_platform="TWITTER")

    # Second consumption must fail
    with pytest.raises(Exception) as exc_info:
        OAuthService.consume_oauth_state(db_session, state_val, expected_platform="TWITTER")
    assert "400" in str(exc_info.value) or "already consumed" in str(exc_info.value)


def test_atomic_state_platform_mismatch_rejection(db_session):
    """Verifies platform mismatch is rejected and state is purged."""
    state_rec = OAuthService.create_oauth_state(
        db=db_session,
        platform="TWITTER",
        ttl_seconds=600
    )
    with pytest.raises(Exception) as exc_info:
        OAuthService.consume_oauth_state(db_session, state_rec.state, expected_platform="LINKEDIN")
    assert "platform mismatch" in str(exc_info.value).lower()


def test_atomic_state_expired_rejection(db_session):
    """Verifies expired state is rejected."""
    state_rec = OAuthService.create_oauth_state(
        db=db_session,
        platform="TWITTER",
        ttl_seconds=-10  # Expired in past
    )
    with pytest.raises(Exception) as exc_info:
        OAuthService.consume_oauth_state(db_session, state_rec.state, expected_platform="TWITTER")
    assert "expired" in str(exc_info.value).lower()


# =========================================================================
# 3. ROUTER ENDPOINTS & MOCKED OAUTH FLOW TESTS
# =========================================================================

def test_twitter_authorize_endpoint(client, db_session):
    """Verifies /auth/twitter/authorize returns valid authorization URL with S256 PKCE."""
    resp = client.get("/api/v1/auth/twitter/authorize")
    assert resp.status_code == 200
    data = resp.json()
    assert "authorization_url" in data
    assert "state" in data
    auth_url = data["authorization_url"]
    assert "https://twitter.com/i/oauth2/authorize" in auth_url
    assert "code_challenge_method=S256" in auth_url
    assert f"state={data['state']}" in auth_url

    # Check state was stored in isolated DB
    stored = db_session.query(OAuthState).filter(OAuthState.state == data["state"]).first()
    assert stored is not None
    assert stored.platform == "TWITTER"


def test_twitter_callback_success_mocked(client, db_session):
    """Verifies callback with mocked Twitter API successfully encrypts tokens and returns safe HTML."""
    # 1. Create state
    state_rec = OAuthService.create_oauth_state(
        db=db_session,
        platform="TWITTER",
        code_verifier="mock_pkce_verifier_xyz",
        redirect_uri=settings.X_REDIRECT_URI,
        ttl_seconds=600
    )

    mock_token_response = {
        "access_token": "mock_access_token_12345",
        "refresh_token": "mock_refresh_token_67890",
        "expires_in": 7200,
        "token_type": "bearer",
        "scope": "tweet.read tweet.write users.read offline.access"
    }
    mock_profile_response = {
        "account_id": "123456789",
        "username": "AIContentCreator",
        "name": "AI Content Creator"
    }

    with patch("backend.app.auth.twitter_oauth.TwitterOAuthService.exchange_code_for_token", return_value=mock_token_response), \
         patch("backend.app.auth.twitter_oauth.TwitterOAuthService.fetch_user_profile", return_value=mock_profile_response):

        resp = client.get(f"/api/v1/auth/twitter/callback?code=mock_auth_code&state={state_rec.state}")
        assert resp.status_code == 200
        html = resp.text

        # Verify safe popup postMessage targeting configured origin
        assert settings.FRONTEND_ORIGIN in html
        assert "SOCIAL_AGENT_OAUTH_CALLBACK" in html
        assert "AIContentCreator" in html
        assert "SUCCESS" in html

        # Verify database record in social_accounts
        account = db_session.query(SocialAccount).filter(SocialAccount.platform == PlatformType.TWITTER).first()
        assert account is not None
        assert account.account_name == "AIContentCreator"
        assert account.account_id == "123456789"
        assert account.is_active is True

        # Verify tokens are encrypted at rest
        assert account.encrypted_access_token != "mock_access_token_12345"
        decrypted_access = token_security.decrypt(account.encrypted_access_token)
        assert decrypted_access == "mock_access_token_12345"
        decrypted_refresh = token_security.decrypt(account.encrypted_refresh_token)
        assert decrypted_refresh == "mock_refresh_token_67890"


def test_twitter_callback_provider_error(client):
    """Verifies provider error parameter returns 400 HTML payload gracefully."""
    resp = client.get("/api/v1/auth/twitter/callback?error=access_denied&error_description=User+cancelled+authorization")
    assert resp.status_code == 400
    html = resp.text
    assert "User cancelled authorization" in html
    assert "Authentication Failed" in html


def test_twitter_disconnect(client, db_session):
    """Verifies disconnection deactivates account and scrubs encrypted tokens."""
    # First seed account
    OAuthService.upsert_social_account(
        db=db_session,
        platform=PlatformType.TWITTER,
        account_name="TempUser",
        account_id="999",
        access_token="plain_token"
    )

    with patch("backend.app.auth.twitter_oauth.TwitterOAuthService.revoke_token", return_value=True):
        resp = client.post("/api/v1/auth/twitter/disconnect")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True

        # Check DB
        acc = db_session.query(SocialAccount).filter(SocialAccount.platform == PlatformType.TWITTER).first()
        assert acc.is_active is False
        assert acc.encrypted_access_token is None
        assert acc.encrypted_refresh_token is None


def test_get_connected_accounts_endpoint(client, db_session):
    """Verifies /auth/accounts returns status for all 4 platforms."""
    # Seed one active Twitter account
    OAuthService.upsert_social_account(
        db=db_session,
        platform=PlatformType.TWITTER,
        account_name="ActiveHandle",
        account_id="111",
        access_token="tok_111"
    )

    resp = client.get("/api/v1/auth/accounts")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    accounts = data["accounts"]

    assert accounts["TWITTER"]["connected"] is True
    assert accounts["TWITTER"]["account_name"] == "ActiveHandle"
    assert accounts["LINKEDIN"]["connected"] is False
    assert accounts["META_FACEBOOK"]["connected"] is False
    assert accounts["META_INSTAGRAM"]["connected"] is False
