import os
import sqlite3
import pytest
from unittest.mock import patch, MagicMock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.config import settings, Settings
from backend.app.database.database import Base, get_db
from backend.app.database.models import (
    Post,
    ScheduledPost,
    SocialAccount,
    PlatformType,
    get_utc_now,
)
from backend.app.publishers.base import BasePublisher, PublishResult
from backend.app.publishers.mock_publisher import MockPublisher
from backend.app.publishers.facebook_publisher import FacebookPublisher
from backend.app.publishers.linkedin_publisher import LinkedInPublisher
from backend.app.publishers.instagram_publisher import InstagramPublisher
from backend.app.scheduler.scheduler import start_scheduler, stop_scheduler


TEST_ISOLATION_DB_FILE = "test_phase9_isolation_temp.db"
TEST_ISOLATION_DB_URL = f"sqlite:///./{TEST_ISOLATION_DB_FILE}"
isolation_engine = create_engine(
    TEST_ISOLATION_DB_URL,
    connect_args={"check_same_thread": False},
)
IsolationSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=isolation_engine)


@pytest.fixture(scope="module", autouse=True)
def setup_isolation_db():
    assert "social_agent.db" not in TEST_ISOLATION_DB_URL
    Base.metadata.create_all(bind=isolation_engine)
    yield
    Base.metadata.drop_all(bind=isolation_engine)
    isolation_engine.dispose()
    if os.path.exists(TEST_ISOLATION_DB_FILE):
        try:
            os.remove(TEST_ISOLATION_DB_FILE)
        except OSError:
            pass


@pytest.fixture
def isolation_db():
    session = IsolationSessionLocal()
    try:
        yield session
    finally:
        session.close()


def test_scheduler_disabled_guardrail():
    """Verify that when SCHEDULER_ENABLED is False, start_scheduler returns None
    and never starts APScheduler background workers.
    """
    with patch.object(settings, "SCHEDULER_ENABLED", False):
        sched = start_scheduler()
        assert sched is None


def test_publisher_signatures_support_injected_db():
    """Verify that BasePublisher, MockPublisher, FacebookPublisher, LinkedInPublisher,
    and InstagramPublisher all accept an optional db argument to avoid opening un-isolated sessions.
    """
    mock_pub = MockPublisher()
    fb_pub = FacebookPublisher()
    li_pub = LinkedInPublisher()
    ig_pub = InstagramPublisher()

    post = Post(
        topic="Isolation Test",
        raw_content="Content for isolation",
        target_platforms=["TWITTER"],
        platform_contents={
            "TWITTER": "Twitter test content",
            "META_FACEBOOK": "Facebook test content",
            "LINKEDIN": "LinkedIn test content",
            "META_INSTAGRAM": "Instagram test caption",
        },
    )

    # In mock mode, each publisher safely delegates or completes without error using injected db
    res_mock = mock_pub.publish(post=post, db=None)
    assert res_mock.status in ("SUCCESS", "FAILED")

    res_fb = fb_pub.publish(post=post, db=None)
    assert res_fb.status in ("SUCCESS", "FAILED")

    res_li = li_pub.publish(post=post, db=None)
    assert res_li.status in ("SUCCESS", "FAILED")

    res_ig = ig_pub.publish(post=post, db=None)
    assert res_ig.status in ("SUCCESS", "FAILED")


def test_publishers_use_injected_db_session(isolation_db):
    """Verify that publishers query the provided db session directly rather than calling SessionLocal()."""
    with patch("backend.app.publishers.facebook_publisher.SessionLocal") as mock_fb_sl, \
         patch("backend.app.publishers.linkedin_publisher.SessionLocal") as mock_li_sl, \
         patch("backend.app.publishers.instagram_publisher.SessionLocal") as mock_ig_sl:

        fb_pub = FacebookPublisher()
        li_pub = LinkedInPublisher()
        ig_pub = InstagramPublisher()

        # Disable mock publishing temporarily to reach DB lookup branch
        with patch.object(settings, "MOCK_SOCIAL_PUBLISHING", False):
            post = Post(
                topic="DB Session Injection",
                raw_content="Testing injected session usage",
                target_platforms=["META_FACEBOOK", "LINKEDIN", "META_INSTAGRAM"],
                platform_contents={
                    "META_FACEBOOK": "FB content",
                    "LINKEDIN": "LI content",
                    "META_INSTAGRAM": "IG content",
                },
            )
            post.media_url = "https://example.com/image.jpg"

            # Publishing with injected db session
            fb_pub.publish(post=post, db=isolation_db)
            li_pub.publish(post=post, db=isolation_db)
            ig_pub.publish(post=post, db=isolation_db)

            # SessionLocal must NOT have been called in any of the three publishers!
            mock_fb_sl.assert_not_called()
            mock_li_sl.assert_not_called()
            mock_ig_sl.assert_not_called()


def test_windows_engine_disposal_cleans_file_without_lock():
    """Verify that calling engine.dispose() on SQLite removes OS locks on Windows,
    permitting immediate file deletion without WinError 32.
    """
    temp_file = "test_windows_lock_check_temp.db"
    temp_url = f"sqlite:///./{temp_file}"
    eng = create_engine(temp_url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=eng)

    # Perform a query to acquire connection lock
    with eng.connect() as conn:
        conn.execute(Base.metadata.tables["posts"].select())

    # On Windows, deleting without dispose often fails with WinError 32
    # Calling dispose() must ensure connection is closed and file can be removed
    eng.dispose()
    assert os.path.exists(temp_file)
    os.remove(temp_file)
    assert not os.path.exists(temp_file)


def test_active_db_counts_and_integrity_unaffected():
    """Verify that social_agent.db retains all records and passes integrity checks."""
    active_db = "social_agent.db"
    assert os.path.exists(active_db), "social_agent.db must exist"

    con = sqlite3.connect(active_db)
    cur = con.cursor()

    # Verify oauth_states count remains exactly 5
    oauth_count = cur.execute("SELECT COUNT(*) FROM oauth_states").fetchone()[0]
    assert oauth_count == 5, f"Expected 5 oauth_states records, found {oauth_count}"

    # Verify PRAGMA integrity
    integrity = cur.execute("PRAGMA integrity_check").fetchone()[0]
    assert integrity == "ok"
    con.close()
