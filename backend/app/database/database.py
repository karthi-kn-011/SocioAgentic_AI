import os
import logging
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from ..config import settings

logger = logging.getLogger("Database")

# Support Vercel serverless writable /tmp directory for SQLite
db_url = settings.DATABASE_URL
if os.environ.get("VERCEL") and db_url.startswith("sqlite"):
    import shutil
    db_path = "/tmp/social_agent.db"
    local_db = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "social_agent.db"))
    if os.path.exists(local_db) and not os.path.exists(db_path):
        try:
            shutil.copy2(local_db, db_path)
        except Exception as e:
            logger.warning(f"Failed to copy local database to /tmp: {e}")
    db_url = f"sqlite:///{db_path}"

# Determine engine connection arguments (SQLite requires check_same_thread=False)
connect_args = {}
if db_url.startswith("sqlite"):
    connect_args["check_same_thread"] = False

engine = create_engine(
    db_url,
    connect_args=connect_args,
    echo=False,
    pool_pre_ping=True
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    """FastAPI dependency for yielding database session."""
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db():
    """Initializes tables in database if they don't already exist."""
    # Import all models to ensure they register on Base.metadata
    from . import models  # noqa: F401
    logger.info(f"Creating database tables using engine ({settings.DATABASE_URL.split('://')[0]})...")
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables initialized successfully.")
