from .health import router as health_router
from .posts import router as posts_router
from .approvals import router as approvals_router
from .schedules import router as schedules_router
from .auth import router as auth_router
from .slack import router as slack_router

__all__ = ["health_router", "posts_router", "approvals_router", "schedules_router", "auth_router", "slack_router"]

