from typing import Generic, TypeVar, Optional, Any
from pydantic import BaseModel, Field

T = TypeVar("T")

class StandardResponse(BaseModel, Generic[T]):
    success: bool = True
    message: Optional[str] = None
    data: Optional[T] = None

class ErrorResponse(BaseModel):
    success: bool = False
    error: str
    code: str = "BAD_REQUEST"
    details: Optional[Any] = None

class HealthStatus(BaseModel):
    status: str = "healthy"
    service: str
    environment: str
    database_connected: bool
    mock_publishing: bool
    mock_slack: bool
    version: str = "1.0.0"
