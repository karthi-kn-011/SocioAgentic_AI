import os
import logging
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from ..config import settings

logger = logging.getLogger("Database")

# Determine engine connection arguments (SQLite requires check_same_thread=False)
connect_args = {}
if settings.DATABASE_URL.startswith("sqlite"):
    connect_args["check_same_thread"] = False

engine = create_engine(
    settings.DATABASE_URL,
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
