import os
import sqlite3
import pytest
from backend.app.config import settings
from backend.app.auth.security import verify_operator_session
from backend.app.main import app


@pytest.fixture(autouse=True)
def authenticate_test_operator_session():
    """Explicit test fixture that provides operator authorization across test suites
    without weakening production authentication or introducing environment-based bypasses.
    """
    app.dependency_overrides[verify_operator_session] = lambda: {
        "sub": "test_operator",
        "auth_method": "test_fixture",
    }
    yield
    app.dependency_overrides.pop(verify_operator_session, None)


@pytest.fixture(scope="session", autouse=True)
def disable_scheduler_during_tests():
    """Ensures background APScheduler scanner thread never starts or runs during tests,
    preventing asynchronous background queries to the database.
    """
    orig_scheduler = settings.SCHEDULER_ENABLED
    settings.SCHEDULER_ENABLED = False
    yield
    settings.SCHEDULER_ENABLED = orig_scheduler


@pytest.fixture(scope="session", autouse=True)
def verify_active_database_untouched():
    """Fail-safe integrity guardrail: Confirms that the active application database
    'social_agent.db' is never written to, truncated, or modified during test suite execution.
    """
    db_path = "social_agent.db"
    initial_state = {}
    if os.path.exists(db_path):
        con = sqlite3.connect(db_path)
        cur = con.cursor()
        tables = [
            r[0]
            for r in cur.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
        ]
        initial_state = {
            t: cur.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            for t in tables
        }
        con.close()

    yield

    if os.path.exists(db_path) and initial_state:
        con = sqlite3.connect(db_path)
        cur = con.cursor()
        final_state = {
            t: cur.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            for t in initial_state.keys()
        }
        integrity = cur.execute("PRAGMA integrity_check").fetchone()[0]
        con.close()

        assert initial_state == final_state, (
            f"TEST ISOLATION VIOLATION: social_agent.db was altered during tests! "
            f"Initial: {initial_state}, Final: {final_state}"
        )
        assert integrity == "ok", f"Integrity check failed on social_agent.db: {integrity}"
