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
from backend.app.auth.instagram_oauth import InstagramOAuthService
from backend.app.auth.facebook_oauth import GRAPH_API_VERSION
from backend.app.auth.security import token_security
from backend.app.publishers.registry import PublisherRegistry
from backend.app.publishers.instagram_publisher import InstagramPublisher
from backend.app.publishers.mock_publisher import MockPublisher

TEST_DB_FILE = "test_phase75_temp.db"
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


def test_instagram_build_authorization_url():
    """Verifies Instagram consent URL contains expected parameters, scopes, and redirect URI."""
    url = InstagramOAuthService.build_authorization_url(
        state="test_ig_state_123",
        redirect_uri="http://localhost:8000/api/v1/auth/instagram/callback"
    )
    assert f"https://www.facebook.com/{GRAPH_API_VERSION}/dialog/oauth" in url
    assert "response_type=code" in url
    assert "state=test_ig_state_123" in url
    assert "instagram_basic" in url
    assert "instagram_content_publish" in url
    assert "pages_show_list" in url


def test_instagram_media_url_validation():
    """Verifies that Instagram media URL validator rejects empty or non-HTTP URLs and accepts valid URLs."""
    # 1. Empty / None -> Rejected
    ok, err = InstagramOAuthService.validate_media_url(None)
    assert ok is False
    assert "strictly requires a publicly accessible image or video URL" in err

    ok, err = InstagramOAuthService.validate_media_url("   ")
    assert ok is False
    assert "strictly requires a publicly accessible image or video URL" in err

    # 2. Invalid scheme -> Rejected
    ok, err = InstagramOAuthService.validate_media_url("ftp://example.com/pic.png")
    assert ok is False
    assert "Invalid media URL scheme" in err

    ok, err = InstagramOAuthService.validate_media_url("file:///C:/local/image.png")
    assert ok is False
    assert "Invalid media URL scheme" in err

    # 3. Valid public HTTPS URL -> Accepted
    ok, err = InstagramOAuthService.validate_media_url("https://cdn.example.com/media/visual_brief.jpg")
    assert ok is True
    assert err is None


# =========================================================================
# 2. INSTAGRAM OAUTH ENDPOINT TESTS
# =========================================================================

def test_instagram_authorize_endpoint(client, db_session):
    """Verifies /auth/instagram/authorize returns valid authorization URL and persists state."""
    resp = client.get("/api/v1/auth/instagram/authorize")
    assert resp.status_code == 200
    data = resp.json()
    assert "authorization_url" in data
    assert "state" in data
    assert "instagram_content_publish" in data["authorization_url"]

    # Verify state record in DB
    state_rec = db_session.query(OAuthState).filter(OAuthState.state == data["state"]).first()
    assert state_rec is not None
    assert state_rec.platform == "META_INSTAGRAM"


def test_instagram_callback_success_mocked(client, db_session):
    """Verifies callback with mocked Meta token exchange, Page query, and Instagram Business discovery."""
    state_rec = OAuthService.create_oauth_state(
        db=db_session,
        platform="META_INSTAGRAM",
        redirect_uri=settings.INSTAGRAM_REDIRECT_URI,
        ttl_seconds=600,
    )

    mock_short_token = {"access_token": "mock_short_user_tok", "expires_in": 7200}
    mock_long_token = {"access_token": "mock_long_user_tok", "expires_in": 5184000}
    mock_pages = [
        {
            "id": "100111222333",
            "name": "ACME Brand Page",
            "access_token": "mock_page_token_for_instagram",
        }
    ]
    mock_ig_account = {
        "id": "17841400998877665",
        "username": "acme_brand_official",
        "name": "ACME Brand Official",
        "profile_picture_url": "https://cdn.example.com/pic.jpg",
    }

    with patch("backend.app.auth.facebook_oauth.FacebookOAuthService.exchange_code_for_user_token", return_value=mock_short_token), \
         patch("backend.app.auth.facebook_oauth.FacebookOAuthService.exchange_for_long_lived_user_token", return_value=mock_long_token), \
         patch("backend.app.auth.facebook_oauth.FacebookOAuthService.fetch_managed_pages", return_value=mock_pages), \
         patch("backend.app.auth.instagram_oauth.InstagramOAuthService.fetch_linked_instagram_account", return_value=mock_ig_account):

        resp = client.get(f"/api/v1/auth/instagram/callback?code=mock_ig_code&state={state_rec.state}")
        assert resp.status_code == 200
        html = resp.text

        # Verify safe popup response targeting FRONTEND_ORIGIN
        assert settings.FRONTEND_ORIGIN in html
        assert "SOCIAL_AGENT_OAUTH_CALLBACK" in html
        assert "@acme_brand_official" in html
        assert "SUCCESS" in html

        # Verify account in DB
        account = db_session.query(SocialAccount).filter(SocialAccount.platform == PlatformType.META_INSTAGRAM).first()
        assert account is not None
        assert account.account_name == "@acme_brand_official"
        assert account.account_id == "17841400998877665"
        assert account.is_active is True

        # Verify encrypted Page access token at rest
        assert account.encrypted_access_token != "mock_page_token_for_instagram"
        decrypted_tok = token_security.decrypt(account.encrypted_access_token)
        assert decrypted_tok == "mock_page_token_for_instagram"


def test_instagram_callback_no_linked_account_error(client, db_session):
    """Verifies that authenticating with Facebook Pages lacking a linked Instagram Business account returns a clear error."""
    state_rec = OAuthService.create_oauth_state(
        db=db_session,
        platform="META_INSTAGRAM",
        redirect_uri=settings.INSTAGRAM_REDIRECT_URI,
        ttl_seconds=600,
    )

    mock_short_token = {"access_token": "mock_short_user_tok"}
    mock_long_token = {"access_token": "mock_long_user_tok"}
    mock_pages = [{"id": "page_unlinked", "name": "Unlinked Page", "access_token": "unlinked_tok"}]

    with patch("backend.app.auth.facebook_oauth.FacebookOAuthService.exchange_code_for_user_token", return_value=mock_short_token), \
         patch("backend.app.auth.facebook_oauth.FacebookOAuthService.exchange_for_long_lived_user_token", return_value=mock_long_token), \
         patch("backend.app.auth.facebook_oauth.FacebookOAuthService.fetch_managed_pages", return_value=mock_pages), \
         patch("backend.app.auth.instagram_oauth.InstagramOAuthService.fetch_linked_instagram_account", return_value=None):

        resp = client.get(f"/api/v1/auth/instagram/callback?code=mock_ig_code&state={state_rec.state}")
        assert resp.status_code == 400
        html = resp.text
        assert "No linked Instagram Business account found" in html
        assert "Authentication Failed" in html


def test_instagram_callback_provider_error(client):
    """Verifies provider error in callback query params returns error HTML payload."""
    resp = client.get("/api/v1/auth/instagram/callback?error=access_denied&error_description=User+declined+permissions")
    assert resp.status_code == 400
    html = resp.text
    assert "User declined permissions" in html
    assert "Authentication Failed" in html


def test_instagram_callback_atomic_consumption_replay_rejection(client, db_session):
    """Verifies duplicate callback requests with identical state are rejected."""
    state_rec = OAuthService.create_oauth_state(
        db=db_session,
        platform="META_INSTAGRAM",
        redirect_uri=settings.INSTAGRAM_REDIRECT_URI,
        ttl_seconds=600,
    )
    state_val = state_rec.state

    mock_short = {"access_token": "tok_short"}
    mock_long = {"access_token": "tok_long"}
    mock_pages = [{"id": "p1", "name": "P1", "access_token": "p_tok"}]
    mock_ig = {"id": "ig_1", "username": "ig_user_1"}

    with patch("backend.app.auth.facebook_oauth.FacebookOAuthService.exchange_code_for_user_token", return_value=mock_short), \
         patch("backend.app.auth.facebook_oauth.FacebookOAuthService.exchange_for_long_lived_user_token", return_value=mock_long), \
         patch("backend.app.auth.facebook_oauth.FacebookOAuthService.fetch_managed_pages", return_value=mock_pages), \
         patch("backend.app.auth.instagram_oauth.InstagramOAuthService.fetch_linked_instagram_account", return_value=mock_ig):

        resp1 = client.get(f"/api/v1/auth/instagram/callback?code=c1&state={state_val}")
        assert resp1.status_code == 200

        resp2 = client.get(f"/api/v1/auth/instagram/callback?code=c2&state={state_val}")
        assert resp2.status_code == 400
        assert "already consumed" in resp2.text or "Invalid" in resp2.text


def test_instagram_disconnect_endpoint(client, db_session):
    """Verifies /auth/instagram/disconnect deactivates account and scrubs tokens."""
    OAuthService.upsert_social_account(
        db=db_session,
        platform=PlatformType.META_INSTAGRAM,
        account_name="@brand_ig",
        account_id="17841400",
        access_token="plain_ig_token",
    )

    resp = client.post("/api/v1/auth/instagram/disconnect")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True

    acc = db_session.query(SocialAccount).filter(SocialAccount.platform == PlatformType.META_INSTAGRAM).first()
    assert acc.is_active is False
    assert acc.encrypted_access_token is None
    assert acc.encrypted_refresh_token is None


# =========================================================================
# 3. PUBLISHER GUARDRAIL & MEDIA VALIDATION TESTS
# =========================================================================

def test_instagram_publisher_mock_mode_guardrail():
    """Verifies InstagramPublisher delegates strictly to MockPublisher when MOCK_SOCIAL_PUBLISHING=True."""
    settings.MOCK_SOCIAL_PUBLISHING = True
    publisher = InstagramPublisher()

    dummy_post = MagicMock()
    dummy_post.platform = "META_INSTAGRAM"
    dummy_post.get_platform_content.return_value = "Visual carousel brief with hashtags."

    res = publisher.publish(post=dummy_post)
    assert res.is_mock is True
    assert res.provider == "MockPublisher"
    assert res.status in ("SUCCESS", "SIMULATED")


def test_instagram_publisher_live_mode_rejects_text_only():
    """Verifies that in live mode (mock=False), text-only posts without media are strictly rejected."""
    settings.MOCK_SOCIAL_PUBLISHING = False
    try:
        publisher = InstagramPublisher()
        dummy_post = MagicMock()
        dummy_post.platform = "META_INSTAGRAM"
        dummy_post.media_url = None
        dummy_post.image_url = None
        dummy_post.platform_contents = {"META_INSTAGRAM": "Text-only post without image URL."}
        dummy_post.get_platform_content.return_value = "Text-only post without image URL."

        res = publisher.publish(post=dummy_post)
        assert res.status == "FAILED"
        assert res.is_mock is False
        assert "Instagram strictly requires a publicly accessible image or video URL" in (res.error_message or "")
    finally:
        settings.MOCK_SOCIAL_PUBLISHING = True


def test_instagram_publisher_live_mode_missing_account_with_valid_media():
    """Verifies that with valid media URL, missing account in DB returns clean FAILED result."""
    settings.MOCK_SOCIAL_PUBLISHING = False
    try:
        publisher = InstagramPublisher()
        dummy_post = MagicMock()
        dummy_post.platform = "META_INSTAGRAM"
        dummy_post.media_url = "https://cdn.example.com/posts/banner.jpg"
        dummy_post.get_platform_content.return_value = "Caption with valid media URL."

        res = publisher.publish(post=dummy_post)
        assert res.status == "FAILED"
        assert res.is_mock is False
        assert "No active connected Instagram Business account found" in (res.error_message or "")
    finally:
        settings.MOCK_SOCIAL_PUBLISHING = True


def test_instagram_publisher_live_mode_container_workflow_mocked(db_session):
    """Verifies the complete 2-step media container workflow in live mode with mocked Graph API calls."""
    # Seed active Instagram account
    OAuthService.upsert_social_account(
        db=db_session,
        platform=PlatformType.META_INSTAGRAM,
        account_name="@test_brand_ig",
        account_id="178414009999",
        access_token="valid_page_token",
    )

    settings.MOCK_SOCIAL_PUBLISHING = False
    try:
        publisher = InstagramPublisher()
        dummy_post = MagicMock()
        dummy_post.platform = "META_INSTAGRAM"
        dummy_post.media_url = "https://cdn.example.com/posts/banner.jpg"
        dummy_post.get_platform_content.return_value = "Product launch caption #innovation"

        with patch("backend.app.auth.instagram_oauth.InstagramOAuthService.create_media_container", return_value="container_12345"), \
             patch("backend.app.auth.instagram_oauth.InstagramOAuthService.check_container_status", return_value={"status_code": "FINISHED"}), \
             patch("backend.app.auth.instagram_oauth.InstagramOAuthService.publish_media_container", return_value="ig_media_post_67890"):

            res = publisher.publish(post=dummy_post, db=db_session)
            assert res.status == "SUCCESS"
            assert res.is_mock is False
            assert res.external_post_id == "ig_media_post_67890"
            assert res.response_payload["creation_id"] == "container_12345"
            assert res.response_payload["media_id"] == "ig_media_post_67890"
    finally:
        settings.MOCK_SOCIAL_PUBLISHING = True


def test_accounts_status_reports_all_four_platforms(client, db_session):
    """Verifies /auth/accounts reports accurate status for X, LinkedIn, Facebook, and Instagram simultaneously."""
    OAuthService.upsert_social_account(db=db_session, platform=PlatformType.TWITTER, account_name="BrandX", account_id="tw_1", access_token="t_x")
    OAuthService.upsert_social_account(db=db_session, platform=PlatformType.LINKEDIN, account_name="BrandLI", account_id="li_1", access_token="t_li")
    OAuthService.upsert_social_account(db=db_session, platform=PlatformType.META_FACEBOOK, account_name="BrandFB", account_id="fb_1", access_token="t_fb")
    OAuthService.upsert_social_account(db=db_session, platform=PlatformType.META_INSTAGRAM, account_name="@BrandIG", account_id="ig_1", access_token="t_ig")

    resp = client.get("/api/v1/auth/accounts")
    assert resp.status_code == 200
    accounts = resp.json()["accounts"]

    assert accounts["TWITTER"]["connected"] is True
    assert accounts["LINKEDIN"]["connected"] is True
    assert accounts["META_FACEBOOK"]["connected"] is True
    assert accounts["META_INSTAGRAM"]["connected"] is True
    assert accounts["META_INSTAGRAM"]["account_name"] == "@BrandIG"
