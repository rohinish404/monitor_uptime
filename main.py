from fastapi import Depends, FastAPI, HTTPException, BackgroundTasks
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Enum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from pydantic import BaseModel, HttpUrl
from datetime import datetime, timezone
import httpx
import enum
import asyncio
from contextlib import asynccontextmanager
import logging 

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
# Database setup
SQLALCHEMY_DATABASE_URL = "sqlite:///./website_monitor.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Models
class WebsiteStatus(str, enum.Enum):
    UP = "up"
    DOWN = "down"
    UNKNOWN = "unknown"

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

# Pydantic models for API
class WebsiteCreate(BaseModel):
    url: HttpUrl
    name: str | None = None
    check_interval_seconds: int = 300
    expected_status_code: int = 200

class WebhookCreate(BaseModel):
    url: HttpUrl
    name: str | None = None

# Create database tables
Base.metadata.create_all(bind=engine)

@asynccontextmanager
async def lifespan(app: FastAPI):
    asyncio.create_task(monitor_websites())
    yield

app = FastAPI(lifespan=lifespan)


# Dependencies
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Monitor service
async def check_website(website_id: int, db: Session = Depends(get_db)):
    website = db.query(Website).filter(Website.id == website_id).first()
    if not website:
        return
    
    async with httpx.AsyncClient() as client:
        start_time = datetime.now(timezone.utc)
        try:
            response = await client.get(website.url, timeout=10.0)
            response_time = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
            
            new_status = WebsiteStatus.UP if response.status_code == 200 else WebsiteStatus.DOWN
            
            # Create status check record
            status_check = StatusCheck(
                website_id=website.id,
                response_time_ms=response_time,
                status=new_status
            )
            db.add(status_check)
            
            # Update website status if changed
            if website.current_status != new_status:
                website.last_status_change = datetime.now(timezone.utc)
                website.current_status = new_status
                await send_discord_notification(website, new_status)
            
            website.last_checked = datetime.now(timezone.utc)
            db.commit()
            
        except Exception as e:
            status_check = StatusCheck(
                website_id=website.id,
                status=WebsiteStatus.DOWN,
                error_message=str(e)
            )
            db.add(status_check)
            
            if website.current_status != WebsiteStatus.DOWN:
                website.last_status_change = datetime.now(timezone.utc)
                website.current_status = WebsiteStatus.DOWN
                await send_discord_notification(website, WebsiteStatus.DOWN)
            
            website.last_checked = datetime.now(timezone.utc)
            db.commit()

async def send_discord_notification(website: Website, status: WebsiteStatus):
    webhooks = SessionLocal().query(WebhookConfig).all()
    if not webhooks:
        return
    
    color = 65280 if status == WebsiteStatus.UP else 16711680  # Green for UP, Red for DOWN
    message = {
        "embeds": [{
            "title": f"Website Status Change: {website.name or website.url}",
            "description": f"Status changed to: {status}",
            "color": color,
            "fields": [
                {
                    "name": "URL",
                    "value": website.url
                },
                {
                    "name": "Time",
                    "value": datetime.now(timezone.utc).isoformat()
                }
            ]
        }]
    }
    
    async with httpx.AsyncClient() as client:
        for webhook in webhooks:
            try:
                await client.post(str(webhook.url), json=message)
            except Exception as e:
                print(f"Failed to send Discord notification: {e}")

# Background task to check all websites
async def monitor_websites():
    while True:
        logger.info("Running website monitoring check...")
        db = SessionLocal()
        try:
            websites = db.query(Website).all()
            for website in websites:
                if not website.last_checked or \
                   (datetime.now(timezone.utc) - website.last_checked.replace(tzinfo=timezone.utc)).total_seconds() >= website.check_interval_seconds:
                    logger.info(f"Checking website: {website.url}")
                    await check_website(website.id, db)
        finally:
            db.close()
        await asyncio.sleep(10)  # Check every 10 seconds for websites that need monitoring

# Start background monitoring on startup

# API Endpoints
@app.post("/sites")
async def add_site(website: WebsiteCreate, db: Session = Depends(get_db)):

    db_website = Website(
        url=str(website.url),
        name=website.name,
        check_interval_seconds=website.check_interval_seconds
    )
    db.add(db_website)
    db.commit()
    db.refresh(db_website)
    return db_website

@app.get("/sites")
async def list_sites(db: Session = Depends(get_db)):
    return db.query(Website).all()

@app.delete("/sites/{website_id}")
async def remove_site(website_id: int, db: Session = Depends(get_db)):
    website = db.query(Website).filter(Website.id == website_id).first()
    if not website:
        raise HTTPException(status_code=404, detail="Website not found")
    db.delete(website)
    db.commit()
    return {"status": "success"}

@app.post("/webhook")
async def add_webhook(webhook: WebhookCreate, db: Session = Depends(get_db)):
    db_webhook = WebhookConfig(url=str(webhook.url), name=webhook.name)
    db.add(db_webhook)
    db.commit()
    db.refresh(db_webhook)
    return db_webhook

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

