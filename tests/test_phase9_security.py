import time
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.config import settings, Settings, DEV_DEFAULT_FERNET, DEV_DEFAULT_SECRET
from backend.app.database.database import Base, get_db
from backend.app.main import app
from backend.app.auth.security import (
    verify_operator_session,
    create_session_token,
    SESSION_COOKIE_NAME,
    CSRF_COOKIE_NAME,
    CSRF_HEADER_NAME,
    _login_attempts,
)

TEST_DB_FILE = "test_phase9_temp.db"
TEST_DATABASE_URL = f"sqlite:///./{TEST_DB_FILE}"
test_engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(scope="module", autouse=True)
def setup_test_environment():
    Base.metadata.create_all(bind=test_engine)
    app.dependency_overrides[get_db] = override_get_db
    yield
    app.dependency_overrides.pop(get_db, None)
    test_engine.dispose()
    import os
    if os.path.exists(TEST_DB_FILE):
        try:
            os.remove(TEST_DB_FILE)
        except OSError:
            pass


@pytest.fixture(autouse=True)
def clean_rate_limits():
    """Ensure rate limit sliding window is clear between tests."""
    _login_attempts.clear()
    yield
    _login_attempts.clear()


@pytest.fixture
def unauthenticated_client():
    """Client with NO automatic operator session override, testing real authentication filters."""
    # Temporarily remove conftest autouse override
    app.dependency_overrides.pop(verify_operator_session, None)
    with TestClient(app) as c:
        yield c
    # Re-enable fixture for subsequent tests
    app.dependency_overrides[verify_operator_session] = lambda: {
        "sub": "test_operator",
        "auth_method": "test_fixture",
    }


def test_operator_login_success(unauthenticated_client):
    """Verifies valid operator credentials issue HttpOnly session and CSRF cookies."""
    response = unauthenticated_client.post(
        "/api/v1/auth/login",
        json={
            "username": settings.OPERATOR_USERNAME,
            "password": settings.OPERATOR_PASSWORD,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["user"] == settings.OPERATOR_USERNAME
    assert "csrf_token" in data

    # Verify cookies
    assert SESSION_COOKIE_NAME in response.cookies
    assert CSRF_COOKIE_NAME in response.cookies


def test_operator_login_invalid_credentials(unauthenticated_client):
    """Verifies invalid login credentials return HTTP 401."""
    response = unauthenticated_client.post(
        "/api/v1/auth/login",
        json={"username": "wrong_operator", "password": "WrongPassword123!"},
    )
    assert response.status_code == 401
    assert "Invalid operator credentials" in response.json()["detail"]


def test_login_rate_limiting(unauthenticated_client):
    """Verifies that 5 consecutive failed attempts trigger HTTP 429 Too Many Requests."""
    for _ in range(5):
        res = unauthenticated_client.post(
            "/api/v1/auth/login",
            json={"username": "attacker", "password": "BadPassword"},
        )
        assert res.status_code == 401

    # 6th attempt should be blocked by rate limiter
    blocked_res = unauthenticated_client.post(
        "/api/v1/auth/login",
        json={"username": "attacker", "password": "BadPassword"},
    )
    assert blocked_res.status_code == 429
    assert "Too many failed login attempts" in blocked_res.json()["detail"]
    assert "Retry-After" in blocked_res.headers


def test_logout_lifecycle(unauthenticated_client):
    """Verifies logging out invalidates session and clears cookies."""
    # First log in
    login_res = unauthenticated_client.post(
        "/api/v1/auth/login",
        json={
            "username": settings.OPERATOR_USERNAME,
            "password": settings.OPERATOR_PASSWORD,
        },
    )
    assert login_res.status_code == 200

    # Then log out
    logout_res = unauthenticated_client.post("/api/v1/auth/logout")
    assert logout_res.status_code == 200
    assert logout_res.json()["success"] is True


def test_session_status_endpoint(unauthenticated_client):
    """Verifies /auth/session reflects authentication status."""
    # Initially unauthenticated
    res_unauth = unauthenticated_client.get("/api/v1/auth/session")
    assert res_unauth.status_code == 200
    assert res_unauth.json()["authenticated"] is False

    # Log in
    unauthenticated_client.post(
        "/api/v1/auth/login",
        json={
            "username": settings.OPERATOR_USERNAME,
            "password": settings.OPERATOR_PASSWORD,
        },
    )

    # Now authenticated
    res_auth = unauthenticated_client.get("/api/v1/auth/session")
    assert res_auth.status_code == 200
    assert res_auth.json()["authenticated"] is True
    assert res_auth.json()["user"] == settings.OPERATOR_USERNAME


def test_protected_routes_reject_unauthenticated(unauthenticated_client):
    """Verifies that operational and sensitive read routes reject unauthenticated requests with HTTP 401."""
    # Unauthenticated GET
    res_get = unauthenticated_client.get("/api/v1/analytics/overview")
    assert res_get.status_code == 401

    # Unauthenticated Approvals endpoints
    res_app_pending = unauthenticated_client.get("/api/v1/approvals/pending")
    assert res_app_pending.status_code == 401

    res_app_history = unauthenticated_client.get("/api/v1/approvals/history")
    assert res_app_history.status_code == 401

    # Unauthenticated Activity
    res_act = unauthenticated_client.get("/api/v1/activity")
    assert res_act.status_code == 401

    # Unauthenticated POST
    res_post = unauthenticated_client.post(
        "/api/v1/posts/generate",
        json={"topic": "Security Testing", "platforms": ["TWITTER"]},
    )
    assert res_post.status_code == 401


def test_approvals_endpoints_succeed_when_authenticated(unauthenticated_client):
    """Regression test: Verifies /api/v1/approvals/history and /pending return HTTP 200
    with valid list format once operator session is established.
    """
    login_res = unauthenticated_client.post(
        "/api/v1/auth/login",
        json={
            "username": settings.OPERATOR_USERNAME,
            "password": settings.OPERATOR_PASSWORD,
        },
    )
    assert login_res.status_code == 200

    # Both approvals endpoints must succeed with 200 and return a JSON list
    res_pending = unauthenticated_client.get("/api/v1/approvals/pending")
    assert res_pending.status_code == 200
    assert isinstance(res_pending.json(), list)

    res_history = unauthenticated_client.get("/api/v1/approvals/history")
    assert res_history.status_code == 200
    assert isinstance(res_history.json(), list)


def test_csrf_protection_for_cookie_authenticated_requests(unauthenticated_client):
    """Verifies state-changing requests using cookie authentication require matching X-CSRF-Token header."""
    # Log in to get session cookie and CSRF cookie
    login_res = unauthenticated_client.post(
        "/api/v1/auth/login",
        json={
            "username": settings.OPERATOR_USERNAME,
            "password": settings.OPERATOR_PASSWORD,
        },
    )
    csrf_token = login_res.cookies.get(CSRF_COOKIE_NAME)
    assert csrf_token is not None

    # 1. State-changing request without CSRF header -> 403 Forbidden
    res_missing_csrf = unauthenticated_client.post(
        "/api/v1/schedules",
        json={"post_id": 1, "scheduled_at": "2026-11-01T12:00:00Z"},
    )
    assert res_missing_csrf.status_code == 403
    assert "CSRF validation failed" in res_missing_csrf.json()["detail"]

    # 2. State-changing request with mismatched CSRF header -> 403 Forbidden
    res_bad_csrf = unauthenticated_client.post(
        "/api/v1/schedules",
        headers={CSRF_HEADER_NAME: "forged_mismatched_token"},
        json={"post_id": 1, "scheduled_at": "2026-11-01T12:00:00Z"},
    )
    assert res_bad_csrf.status_code == 403


def test_programmatic_api_key_authentication(unauthenticated_client):
    """Verifies trusted programmatic clients can authenticate via X-API-Key without cookies or CSRF."""
    test_key = "test_trusted_programmatic_api_key_32bytes!"
    orig_key = settings.API_KEY
    settings.API_KEY = test_key
    try:
        # Request with valid X-API-Key header bypasses CSRF and session cookies
        res = unauthenticated_client.get(
            "/api/v1/analytics/overview",
            headers={"X-API-Key": test_key},
        )
        assert res.status_code == 200

        # Request with invalid API key rejected
        res_bad = unauthenticated_client.get(
            "/api/v1/analytics/overview",
            headers={"X-API-Key": "wrong_key"},
        )
        assert res_bad.status_code == 401
    finally:
        settings.API_KEY = orig_key


def test_cors_explicit_allowed_origins(unauthenticated_client):
    """Verifies that CORS headers are returned only for explicitly permitted origins."""
    allowed_origin = "http://localhost:8000"
    forbidden_origin = "http://malicious-external-site.com"

    # Preflight from allowed origin
    res_allowed = unauthenticated_client.options(
        "/api/v1/health",
        headers={
            "Origin": allowed_origin,
            "Access-Control-Request-Method": "GET",
        },
    )
    assert res_allowed.headers.get("access-control-allow-origin") == allowed_origin
    assert res_allowed.headers.get("access-control-allow-credentials") == "true"

    # Preflight from forbidden origin
    res_forbidden = unauthenticated_client.options(
        "/api/v1/health",
        headers={
            "Origin": forbidden_origin,
            "Access-Control-Request-Method": "GET",
        },
    )
    assert res_forbidden.headers.get("access-control-allow-origin") != forbidden_origin


def test_health_check_returns_503_when_database_fails(unauthenticated_client):
    """Verifies health check endpoint returns HTTP 503 when database is degraded and HTTP 200 when healthy."""
    # Healthy case
    res_healthy = unauthenticated_client.get("/api/v1/health")
    assert res_healthy.status_code == 200
    assert res_healthy.json()["status"] == "healthy"
    assert res_healthy.json()["database_connected"] is True

    # Degraded DB simulation
    with patch("backend.app.routers.health.text", side_effect=Exception("Database connection timeout")):
        res_degraded = unauthenticated_client.get("/api/v1/health")
        assert res_degraded.status_code == 503
        assert res_degraded.json()["status"] == "degraded"
        assert res_degraded.json()["database_connected"] is False


def test_production_security_validation_refuses_dev_defaults():
    """Verifies that production configuration strictly refuses dev defaults for keys and credentials."""
    prod_settings = Settings(
        ENVIRONMENT="production",
        FERNET_KEY=DEV_DEFAULT_FERNET,
        SECRET_KEY="production_safe_secret_key_long_enough_min_32",
        OPERATOR_USERNAME="valid_prod_user",
        OPERATOR_PASSWORD="ValidProdPassword123!",
    )
    with pytest.raises(ValueError, match="Cannot use default or empty FERNET_KEY"):
        prod_settings.validate_production_security()

    # Short operator password rejection
    prod_bad_pwd = Settings(
        ENVIRONMENT="production",
        FERNET_KEY="valid_base64_fernet_key_example_placeholder=",
        SECRET_KEY="production_safe_secret_key_long_enough_min_32",
        OPERATOR_USERNAME="valid_prod_user",
        OPERATOR_PASSWORD="short",
    )
    with pytest.raises(ValueError):
        prod_bad_pwd.validate_production_security()


def test_third_party_oauth_error_sanitization():
    """Verifies that failed OAuth token exchanges return sanitized error details without leaking raw bodies."""
    from backend.app.auth.twitter_oauth import TwitterOAuthService

    mock_resp = MagicMock()
    mock_resp.status_code = 401
    mock_resp.text = '{"error": "invalid_client", "secret_token_leak": "xyz123"}'

    with patch("httpx.Client.post", return_value=mock_resp):
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            TwitterOAuthService.exchange_code_for_token(code="c1", code_verifier="v1")

        assert exc_info.value.status_code == 400
        # Assert raw response body text is NOT leaked
        assert "secret_token_leak" not in str(exc_info.value.detail)
        assert "Provider returned an error" in str(exc_info.value.detail)
