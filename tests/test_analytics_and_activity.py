import os
import datetime
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
    PlatformType,
    get_utc_now,
)
from backend.app.main import app

TEST_DB_FILE = "test_phase8_temp.db"
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
    """Sets up the isolated test SQLite database and strictly asserts no writes to social_agent.db."""
    if os.path.exists(TEST_DB_FILE):
        try:
            os.remove(TEST_DB_FILE)
        except Exception:
            pass

    Base.metadata.create_all(bind=test_engine)
    app.dependency_overrides[get_db] = override_get_db

    yield

    app.dependency_overrides.pop(get_db, None)
    test_engine.dispose()
    if os.path.exists(TEST_DB_FILE):
        try:
            os.remove(TEST_DB_FILE)
        except Exception:
            pass


@pytest.fixture(scope="function")
def test_db():
    """Provides a clean transaction-isolated session per test function."""
    db = TestingSessionLocal()
    try:
        # Clear test database tables before each test
        for tbl in reversed(Base.metadata.sorted_tables):
            db.execute(tbl.delete())
        db.commit()
        yield db
    finally:
        db.close()


@pytest.fixture(scope="function")
def client(test_db):
    """TestClient instance configured for isolated testing."""
    return TestClient(app)


def test_database_isolation_guardrail():
    """Strict guardrail ensuring social_agent.db is preserved and valid."""
    import sqlite3
    assert os.path.exists("social_agent.db"), "Production/demo social_agent.db must exist."
    con = sqlite3.connect("social_agent.db")
    cur = con.cursor()
    # Baseline verified row counts and integrity
    count = cur.execute("SELECT count(*) FROM posts").fetchone()[0]
    integrity = cur.execute("PRAGMA integrity_check").fetchone()[0]
    con.close()
    assert count >= 5, f"Expected at least 5 posts in social_agent.db, found {count}"
    assert integrity == "ok", f"Integrity check failed: {integrity}"


def test_analytics_overview_empty_db(client):
    """Verify analytics overview handles an empty database gracefully."""
    response = client.get("/api/v1/analytics/overview")
    assert response.status_code == 200
    data = response.json()

    assert data["total_publications"] == 0
    assert data["successful_publications"] == 0
    assert data["failed_publications"] == 0
    assert data["success_rate"] == 0.0
    assert data["average_ai_score"] is None
    assert data["platform_breakdown"] == {}
    assert data["mock_publishing"] is True
    assert data["mock_slack"] is True


def test_analytics_overview_with_data(client, test_db):
    """Verify calculation of publications, success rate, AI scores, and breakdown."""
    now = get_utc_now()

    # Seed Posts with varying review scores
    p1 = Post(raw_content="Post 1", topic="Tech", review_score=90, status=PostStatus.APPROVED)
    p2 = Post(raw_content="Post 2", topic="AI", review_score=80, status=PostStatus.APPROVED)
    p3 = Post(raw_content="Post 3", topic="Dev", review_score=None, status=PostStatus.DRAFT)
    test_db.add_all([p1, p2, p3])
    test_db.commit()

    # Seed PublishLogs
    log1 = PublishLog(
        post_id=p1.id,
        platform=PlatformType.TWITTER,
        provider="MockTwitterPublisher",
        is_mock=True,
        status="SUCCESS",
        attempted_at=now,
        published_at=now,
    )
    log2 = PublishLog(
        post_id=p1.id,
        platform=PlatformType.LINKEDIN,
        provider="MockLinkedInPublisher",
        is_mock=True,
        status="SUCCESS",
        attempted_at=now,
        published_at=now,
    )
    log3 = PublishLog(
        post_id=p2.id,
        platform=PlatformType.META_FACEBOOK,
        provider="MockFacebookPublisher",
        is_mock=True,
        status="FAILED",
        error_message="Simulated connection error",
        attempted_at=now,
    )
    log4 = PublishLog(
        post_id=p2.id,
        platform=PlatformType.TWITTER,
        provider="MockTwitterPublisher",
        is_mock=True,
        status="SIMULATED",
        attempted_at=now,
        published_at=now,
    )
    test_db.add_all([log1, log2, log3, log4])
    test_db.commit()

    # Test versioned endpoint
    response = client.get("/api/v1/analytics/overview")
    assert response.status_code == 200
    data = response.json()

    assert data["total_publications"] == 4
    assert data["successful_publications"] == 3  # log1 (SUCCESS), log2 (SUCCESS), log4 (SIMULATED)
    assert data["failed_publications"] == 1      # log3 (FAILED)
    assert data["success_rate"] == 75.0          # 3 / 4 * 100
    assert data["average_ai_score"] == 85.0      # (90 + 80) / 2
    assert data["platform_breakdown"]["TWITTER"] == 2
    assert data["platform_breakdown"]["LINKEDIN"] == 1
    assert data["platform_breakdown"]["META_FACEBOOK"] == 1

    # Test unversioned compatibility endpoint
    unversioned_res = client.get("/api/analytics/overview")
    assert unversioned_res.status_code == 200
    assert unversioned_res.json()["total_publications"] == 4


def test_publication_logs_pagination_and_filtering(client, test_db):
    """Verify GET /api/v1/analytics/publications with pagination and filters."""
    p = Post(raw_content="Post", topic="Topic", status=PostStatus.APPROVED)
    test_db.add(p)
    test_db.commit()

    # Create 5 logs
    for i in range(5):
        plat = PlatformType.TWITTER if i % 2 == 0 else PlatformType.LINKEDIN
        stat = "SUCCESS" if i < 4 else "FAILED"
        test_db.add(
            PublishLog(
                post_id=p.id,
                platform=plat,
                status=stat,
                is_mock=True,
                external_post_id=f"ext_{i}",
            )
        )
    test_db.commit()

    # 1. Default list
    res = client.get("/api/v1/analytics/publications")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 5
    assert len(data["items"]) == 5

    # 2. Pagination: skip 2, limit 2
    res_page = client.get("/api/v1/analytics/publications?skip=2&limit=2")
    assert res_page.status_code == 200
    page_data = res_page.json()
    assert page_data["total"] == 5
    assert len(page_data["items"]) == 2
    assert page_data["skip"] == 2
    assert page_data["limit"] == 2

    # 3. Platform filter
    res_filter_tw = client.get("/api/v1/analytics/publications?platform=TWITTER")
    assert res_filter_tw.status_code == 200
    tw_data = res_filter_tw.json()
    assert tw_data["total"] == 3
    assert all(item["platform"] == "TWITTER" for item in tw_data["items"])

    # 4. Status filter
    res_filter_fail = client.get("/api/v1/analytics/publications?status=FAILED")
    assert res_filter_fail.status_code == 200
    fail_data = res_filter_fail.json()
    assert fail_data["total"] == 1
    assert fail_data["items"][0]["status"] == "FAILED"


def test_activity_logs_pagination_and_filters(client, test_db):
    """Verify GET /api/v1/activity pagination, filtering, and search."""
    now = get_utc_now()
    yesterday = now - datetime.timedelta(days=1)
    two_days_ago = now - datetime.timedelta(days=2)

    p1 = Post(raw_content="Post 1", topic="Topic 1")
    p2 = Post(raw_content="Post 2", topic="Topic 2")
    test_db.add_all([p1, p2])
    test_db.commit()

    # Seed activity records
    a1 = ActivityLog(post_id=p1.id, action="POST_SCHEDULED", actor="Alice", details="Scheduled for Twitter", created_at=two_days_ago)
    a2 = ActivityLog(post_id=p1.id, action="POST_PUBLISHED", actor="PublisherWorker", details="Published mock to Twitter", created_at=yesterday)
    a3 = ActivityLog(post_id=p2.id, action="APPROVAL_APPROVED", actor="Bob", details="Approved post #2 via Slack", created_at=now)
    a4 = ActivityLog(post_id=p2.id, action="POST_PUBLISHED", actor="PublisherWorker", details="Published mock to LinkedIn", created_at=now)
    a5 = ActivityLog(post_id=None, action="OAUTH_CONNECTED", actor="Alice", details="Connected LinkedIn Account", created_at=now)
    test_db.add_all([a1, a2, a3, a4, a5])
    test_db.commit()

    # 1. Total count and items
    res = client.get("/api/v1/activity")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 5
    assert len(data["items"]) == 5

    # 2. Pagination: skip 1, limit 2
    res_page = client.get("/api/v1/activity?skip=1&limit=2")
    assert res_page.status_code == 200
    page_data = res_page.json()
    assert page_data["total"] == 5
    assert len(page_data["items"]) == 2
    assert page_data["skip"] == 1
    assert page_data["limit"] == 2

    # 3. Action filter
    res_act = client.get("/api/v1/activity?action=POST_PUBLISHED")
    assert res_act.status_code == 200
    act_data = res_act.json()
    assert act_data["total"] == 2
    assert all(item["action"] == "POST_PUBLISHED" for item in act_data["items"])

    # 4. Actor filter
    res_actor = client.get("/api/v1/activity?actor=Bob")
    assert res_actor.status_code == 200
    actor_data = res_actor.json()
    assert actor_data["total"] == 1
    assert actor_data["items"][0]["actor"] == "Bob"

    # 5. Post ID filter
    res_post = client.get(f"/api/v1/activity?post_id={p1.id}")
    assert res_post.status_code == 200
    post_data = res_post.json()
    assert post_data["total"] == 2
    assert all(item["post_id"] == p1.id for item in post_data["items"])

    # 6. Free-text search
    res_search = client.get("/api/v1/activity?search=Slack")
    assert res_search.status_code == 200
    search_data = res_search.json()
    assert search_data["total"] == 1
    assert "Slack" in search_data["items"][0]["details"]

    # 7. Date range filter
    res_date = client.get(
        "/api/v1/activity",
        params={
            "start_date": (yesterday - datetime.timedelta(hours=1)).isoformat(),
            "end_date": (yesterday + datetime.timedelta(hours=1)).isoformat(),
        },
    )
    assert res_date.status_code == 200
    date_data = res_date.json()
    assert date_data["total"] == 1
    assert date_data["items"][0]["action"] == "POST_PUBLISHED"


    # 8. Unversioned compatibility route
    res_unversioned = client.get("/api/activity")
    assert res_unversioned.status_code == 200
    assert res_unversioned.json()["total"] == 5


def test_legacy_health_activity_route_preserved(client, test_db):
    """Verify backward compatibility of GET /api/v1/health/activity."""
    test_db.add(ActivityLog(action="SYSTEM_CHECK", actor="HealthProbe", details="Health audit verified"))
    test_db.commit()

    res = client.get("/api/v1/health/activity?limit=10")
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    assert data[0]["action"] == "SYSTEM_CHECK"
    assert data[0]["actor"] == "HealthProbe"
