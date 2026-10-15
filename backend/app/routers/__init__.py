from .health import router as health_router
from .posts import router as posts_router
from .approvals import router as approvals_router
from .schedules import router as schedules_router

__all__ = ["health_router", "posts_router", "approvals_router", "schedules_router"]

