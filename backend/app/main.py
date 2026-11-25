import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.exceptions import RequestValidationError

from .config import settings
from .database.database import init_db
from .auth.security import verify_operator_session
from .routers import (
    health_router,
    posts_router,
    approvals_router,
    schedules_router,
    auth_router,
    slack_router,
    analytics_router,
    activity_router,
)
from .scheduler import start_scheduler, stop_scheduler
from .schemas.common import ErrorResponse



# Configure structured logging
logging.basicConfig(
    level=logging.INFO if not settings.DEBUG else logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("SocialAgent")

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager for startup and shutdown events."""
    logger.info(f"Starting {settings.APP_NAME} in [{settings.ENVIRONMENT}] mode...")
    try:
        init_db()
    except Exception as e:
        logger.warning(f"Database init warning: {e}")
    if not os.environ.get("VERCEL"):
        try:
            start_scheduler()
        except Exception as e:
            logger.warning(f"Scheduler start warning: {e}")
    yield
    if not os.environ.get("VERCEL"):
        try:
            stop_scheduler()
        except Exception as e:
            pass
    logger.info(f"Shutting down {settings.APP_NAME}...")

app = FastAPI(
    title=settings.APP_NAME,
    description="Professional, production-oriented AI Social Media Management Platform.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# CORS configuration - Restrict to explicit allowed origins with credentials
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global Exception Handlers for Consistent Error Responses
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logger.warning(f"Validation error on {request.url.path}: {exc.errors()}")
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=ErrorResponse(
            success=False,
            error="Validation Error",
            code="VALIDATION_ERROR",
            details=exc.errors()
        ).model_dump()
    )

@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    logger.exception(f"Unhandled server error on {request.url.path}: {exc}")
    # Never leak sensitive traces to client
    detail_msg = str(exc) if settings.DEBUG else "An unexpected internal server error occurred."
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=ErrorResponse(
            success=False,
            error=detail_msg,
            code="INTERNAL_SERVER_ERROR"
        ).model_dump()
    )

# Include API Routers with appropriate authorization boundaries
# Public / Webhook Routers:
app.include_router(health_router, prefix="/api/v1")
app.include_router(auth_router, prefix="/api/v1")
app.include_router(auth_router, prefix="/api")  # Unversioned compatibility mount
app.include_router(slack_router, prefix="/api/v1")
app.include_router(slack_router, prefix="/api")  # Unversioned compatibility mount

# Protected Operational Routers:
app.include_router(posts_router, prefix="/api/v1", dependencies=[Depends(verify_operator_session)])
app.include_router(approvals_router, prefix="/api/v1", dependencies=[Depends(verify_operator_session)])
app.include_router(approvals_router, prefix="/api", dependencies=[Depends(verify_operator_session)])
app.include_router(schedules_router, prefix="/api/v1", dependencies=[Depends(verify_operator_session)])
app.include_router(schedules_router, prefix="/api", dependencies=[Depends(verify_operator_session)])
app.include_router(analytics_router, prefix="/api/v1", dependencies=[Depends(verify_operator_session)])
app.include_router(analytics_router, prefix="/api", dependencies=[Depends(verify_operator_session)])
app.include_router(activity_router, prefix="/api/v1", dependencies=[Depends(verify_operator_session)])
app.include_router(activity_router, prefix="/api", dependencies=[Depends(verify_operator_session)])



# Mount Static Frontend
candidates = [
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "frontend")),
    os.path.abspath(os.path.join(os.getcwd(), "frontend")),
    os.path.abspath("frontend"),
]
frontend_dir = next((c for c in candidates if os.path.exists(c)), candidates[0])
if os.path.exists(frontend_dir):
    app.mount("/static", StaticFiles(directory=frontend_dir), name="static")

@app.get("/", include_in_schema=False)
async def serve_index():
    index_path = os.path.join(frontend_dir, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {
        "service": settings.APP_NAME,
        "status": "online",
        "docs": "/docs",
        "api_health": "/api/v1/health"
    }
