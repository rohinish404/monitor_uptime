from sqlalchemy import Column, Integer, String, Float, DateTime
from schemas import WebsiteStatus
from datetime import datetime, timezone
from database import Base

class Website(Base):
    __tablename__ = "websites"
    
    id = Column(Integer, primary_key=True)
    url = Column(String, unique=True, index=True)
    name = Column(String, nullable=True)
    check_interval_seconds = Column(Integer, default=300)
    current_status = Column(String, default=WebsiteStatus.UNKNOWN)
    last_checked = Column(DateTime(timezone=True), nullable=True)
    last_status_change = Column(DateTime(timezone=True), nullable=True)

class StatusCheck(Base):
    __tablename__ = "status_checks"
    
    id = Column(Integer, primary_key=True)
    website_id = Column(Integer)
    timestamp = Column(DateTime(timezone=True), default=datetime.now(timezone.utc))
    response_time_ms = Column(Float, nullable=True)
    status = Column(String)
    error_message = Column(String, nullable=True)

class WebhookConfig(Base):
    __tablename__ = "webhook_configs"
    
    id = Column(Integer, primary_key=True)
    url = Column(String, unique=True)
    name = Column(String, nullable=True)