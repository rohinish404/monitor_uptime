import enum
from pydantic import BaseModel, HttpUrl, ConfigDict
from datetime import datetime

class WebsiteStatus(str, enum.Enum):
    UP = "up"
    DOWN = "down"
    UNKNOWN = "unknown"

class WebsiteCreate(BaseModel):
    url: HttpUrl
    name: str | None = None
    check_interval_seconds: int = 300
    expected_status_code: int = 200

class WebhookCreate(BaseModel):
    url: HttpUrl
    name: str | None = None


class StatusCheckResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    website_id: int
    timestamp: datetime
    response_time_ms: float | None
    status: str
    error_message: str | None

    