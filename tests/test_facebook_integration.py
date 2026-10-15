import os
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
from backend.app.auth.facebook_oauth import FacebookOAuthService, GRAPH_API_VERSION
from backend.app.auth.security import token_security
from backend.app.publishers.registry import PublisherRegistry
from backend.app.publishers.facebook_publisher import FacebookPublisher
from backend.app.publishers.mock_publisher import MockPublisher

TEST_DB_FILE = "test_phase74_temp.db"
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


def test_facebook_build_authorization_url():
    """Verifies Facebook Login URL contains expected parameters, scopes, and Graph API version."""
    url = FacebookOAuthService.build_authorization_url(
        state="test_fb_state_123",
        redirect_uri="http://localhost:8000/api/v1/auth/facebook/callback"
    )
    assert f"https://www.facebook.com/{GRAPH_API_VERSION}/dialog/oauth" in url
    assert "response_type=code" in url
    assert "state=test_fb_state_123" in url
    assert "pages_manage_posts" in url
    assert "pages_show_list" in url
    assert "pages_read_engagement" in url


def test_facebook_page_feed_payload_formatting():
    """Verifies Facebook feed publication payload formatting."""
    payload = FacebookOAuthService.format_page_feed_payload("Community update: exciting product updates live!")
    assert payload["message"] == "Community update: exciting product updates live!"


# =========================================================================
# 2. FACEBOOK OAUTH ENDPOINT TESTS
# =========================================================================

def test_facebook_authorize_endpoint(client, db_session):
    """Verifies /auth/facebook/authorize returns valid authorization URL and persists state."""
    resp = client.get("/api/v1/auth/facebook/authorize")
    assert resp.status_code == 200
    data = resp.json()
    assert "authorization_url" in data
    assert "state" in data
    assert f"https://www.facebook.com/{GRAPH_API_VERSION}/dialog/oauth" in data["authorization_url"]

    # Verify state record in DB
    state_rec = db_session.query(OAuthState).filter(OAuthState.state == data["state"]).first()
    assert state_rec is not None
    assert state_rec.platform == "META_FACEBOOK"


def test_facebook_callback_success_mocked(client, db_session):
    """Verifies callback with mocked user token exchange, long-lived token exchange, and page retrieval."""
    state_rec = OAuthService.create_oauth_state(
        db=db_session,
        platform="META_FACEBOOK",
        redirect_uri=settings.META_REDIRECT_URI,
        ttl_seconds=600,
    )

    mock_short_lived_token = {"access_token": "mock_short_user_tok", "expires_in": 7200}
    mock_long_lived_token = {"access_token": "mock_long_user_tok", "expires_in": 5184000}
    mock_managed_pages = [
        {
            "id": "100987654321",
            "name": "ACME Official Facebook Page",
            "access_token": "mock_page_access_token_super_secret",
            "category": "Technology Company",
            "tasks": ["MANAGE", "CREATE_CONTENT"],
        }
    ]

    with patch("backend.app.auth.facebook_oauth.FacebookOAuthService.exchange_code_for_user_token", return_value=mock_short_lived_token), \
         patch("backend.app.auth.facebook_oauth.FacebookOAuthService.exchange_for_long_lived_user_token", return_value=mock_long_lived_token), \
         patch("backend.app.auth.facebook_oauth.FacebookOAuthService.fetch_managed_pages", return_value=mock_managed_pages):

        resp = client.get(f"/api/v1/auth/facebook/callback?code=mock_fb_code&state={state_rec.state}")
        assert resp.status_code == 200
        html = resp.text

        # Verify safe popup response targeting FRONTEND_ORIGIN
        assert settings.FRONTEND_ORIGIN in html
        assert "SOCIAL_AGENT_OAUTH_CALLBACK" in html
        assert "ACME Official Facebook Page" in html
        assert "SUCCESS" in html

        # Verify account in DB
        account = db_session.query(SocialAccount).filter(SocialAccount.platform == PlatformType.META_FACEBOOK).first()
        assert account is not None
        assert account.account_name == "ACME Official Facebook Page"
        assert account.account_id == "100987654321"
        assert account.is_active is True

        # Verify encrypted Page access token at rest
        assert account.encrypted_access_token != "mock_page_access_token_super_secret"
        decrypted_page_tok = token_security.decrypt(account.encrypted_access_token)
        assert decrypted_page_tok == "mock_page_access_token_super_secret"


def test_facebook_callback_no_managed_pages(client, db_session):
    """Verifies that an authenticated user with 0 managed pages receives a helpful error."""
    state_rec = OAuthService.create_oauth_state(
        db=db_session,
        platform="META_FACEBOOK",
        redirect_uri=settings.META_REDIRECT_URI,
        ttl_seconds=600,
    )

    mock_short_lived_token = {"access_token": "mock_short_user_tok", "expires_in": 7200}
    mock_long_lived_token = {"access_token": "mock_long_user_tok", "expires_in": 5184000}

    with patch("backend.app.auth.facebook_oauth.FacebookOAuthService.exchange_code_for_user_token", return_value=mock_short_lived_token), \
         patch("backend.app.auth.facebook_oauth.FacebookOAuthService.exchange_for_long_lived_user_token", return_value=mock_long_lived_token), \
         patch("backend.app.auth.facebook_oauth.FacebookOAuthService.fetch_managed_pages", return_value=[]):

        resp = client.get(f"/api/v1/auth/facebook/callback?code=mock_fb_code&state={state_rec.state}")
        assert resp.status_code == 400
        html = resp.text
        assert "No managed Facebook Pages found" in html
        assert "Authentication Failed" in html


def test_facebook_callback_provider_error(client):
    """Verifies provider error in callback query params returns error HTML payload."""
    resp = client.get("/api/v1/auth/facebook/callback?error=access_denied&error_description=Permissions+declined")
    assert resp.status_code == 400
    html = resp.text
    assert "Permissions declined" in html
    assert "Authentication Failed" in html


def test_facebook_callback_atomic_consumption_replay_rejection(client, db_session):
    """Verifies that duplicate callback requests with the same state are rejected."""
    state_rec = OAuthService.create_oauth_state(
        db=db_session,
        platform="META_FACEBOOK",
        redirect_uri=settings.META_REDIRECT_URI,
        ttl_seconds=600,
    )
    state_val = state_rec.state

    mock_short = {"access_token": "tok_short"}
    mock_long = {"access_token": "tok_long"}
    mock_pages = [{"id": "p1", "name": "Page 1", "access_token": "page_tok_1"}]

    with patch("backend.app.auth.facebook_oauth.FacebookOAuthService.exchange_code_for_user_token", return_value=mock_short), \
         patch("backend.app.auth.facebook_oauth.FacebookOAuthService.exchange_for_long_lived_user_token", return_value=mock_long), \
         patch("backend.app.auth.facebook_oauth.FacebookOAuthService.fetch_managed_pages", return_value=mock_pages):

        # First request succeeds
        resp1 = client.get(f"/api/v1/auth/facebook/callback?code=c1&state={state_val}")
        assert resp1.status_code == 200

        # Second request with identical state must be rejected
        resp2 = client.get(f"/api/v1/auth/facebook/callback?code=c2&state={state_val}")
        assert resp2.status_code == 400
        assert "already consumed" in resp2.text or "Invalid" in resp2.text


def test_facebook_disconnect_endpoint(client, db_session):
    """Verifies /auth/facebook/disconnect deactivates account and scrubs tokens."""
    OAuthService.upsert_social_account(
        db=db_session,
        platform=PlatformType.META_FACEBOOK,
        account_name="Facebook Page 100",
        account_id="100",
        access_token="plain_page_token",
    )

    resp = client.post("/api/v1/auth/facebook/disconnect")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True

    # Confirm in DB
    acc = db_session.query(SocialAccount).filter(SocialAccount.platform == PlatformType.META_FACEBOOK).first()
    assert acc.is_active is False
    assert acc.encrypted_access_token is None
    assert acc.encrypted_refresh_token is None


# =========================================================================
# 3. PUBLISHER GUARDRAIL & STATUS TESTS
# =========================================================================

def test_facebook_publisher_mock_mode_guardrail():
    """Verifies FacebookPublisher delegates strictly to MockPublisher when MOCK_SOCIAL_PUBLISHING=True."""
    settings.MOCK_SOCIAL_PUBLISHING = True
    publisher = FacebookPublisher()

    dummy_post = MagicMock()
    dummy_post.platform = "META_FACEBOOK"
    dummy_post.get_platform_content.return_value = "Community post content for Facebook."

    res = publisher.publish(post=dummy_post)
    assert res.is_mock is True
    assert res.provider == "MockPublisher"
    assert res.status in ("SUCCESS", "SIMULATED")


def test_facebook_publisher_live_mode_missing_account():
    """Verifies that in live mode (mock=False), missing connected Page safely returns FAILED."""
    settings.MOCK_SOCIAL_PUBLISHING = False
    try:
        publisher = FacebookPublisher()
        dummy_post = MagicMock()
        dummy_post.platform = "META_FACEBOOK"
        dummy_post.get_platform_content.return_value = "Valid Facebook content"

        res = publisher.publish(post=dummy_post)
        assert res.status == "FAILED"
        assert res.is_mock is False
        assert "No active connected Facebook Page found" in (res.error_message or "")
    finally:
        settings.MOCK_SOCIAL_PUBLISHING = True  # Restore safe mock mode


def test_accounts_status_reports_x_linkedin_and_facebook(client, db_session):
    """Verifies /auth/accounts reports accurate status for X, LinkedIn, and Facebook simultaneously."""
    # Seed X
    OAuthService.upsert_social_account(
        db=db_session,
        platform=PlatformType.TWITTER,
        account_name="BrandX",
        account_id="tw_101",
        access_token="tok_x",
    )
    # Seed LinkedIn
    OAuthService.upsert_social_account(
        db=db_session,
        platform=PlatformType.LINKEDIN,
        account_name="BrandLeader",
        account_id="urn:li:person:li_202",
        access_token="tok_li",
    )
    # Seed Facebook Page
    OAuthService.upsert_social_account(
        db=db_session,
        platform=PlatformType.META_FACEBOOK,
        account_name="BrandOfficialFB",
        account_id="fb_303",
        access_token="tok_fb_page",
    )

    resp = client.get("/api/v1/auth/accounts")
    assert resp.status_code == 200
    accounts = resp.json()["accounts"]

    assert accounts["TWITTER"]["connected"] is True
    assert accounts["TWITTER"]["account_name"] == "BrandX"

    assert accounts["LINKEDIN"]["connected"] is True
    assert accounts["LINKEDIN"]["account_name"] == "BrandLeader"

    assert accounts["META_FACEBOOK"]["connected"] is True
    assert accounts["META_FACEBOOK"]["account_name"] == "BrandOfficialFB"

    # Instagram is still not connected
    assert accounts["META_INSTAGRAM"]["connected"] is False
