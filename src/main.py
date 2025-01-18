from fastapi import Depends, FastAPI, HTTPException, Query, status
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from pydantic import BaseModel
from datetime import datetime, timezone
import httpx
import asyncio
from typing import List
from contextlib import asynccontextmanager
import logging 
from urllib.parse import urlparse
from sqlalchemy.exc import IntegrityError
from schemas import WebhookCreate, WebsiteCreate, WebsiteStatus, StatusCheckResponse
from database import get_db, SessionLocal, init_db
from models import Website, StatusCheck, WebhookConfig
from utils import URLValidationError, WebhookDeliveryError

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    asyncio.create_task(monitor_websites())
    yield

app = FastAPI(lifespan=lifespan)

def validate_url(url: str) -> bool:
    """
    Validate URL format and scheme
    Returns True if valid, raises URLValidationError if invalid
    """
    try:
        result = urlparse(url)
        if not all([result.scheme, result.netloc]):
            raise URLValidationError("Invalid URL format")
        if result.scheme not in ['http', 'https']:
            raise URLValidationError("URL must use HTTP or HTTPS scheme")
        return True
    except Exception as e:
        raise URLValidationError(f"Invalid URL: {str(e)}")


async def check_website(website_id: int, db: Session):
    website = db.query(Website).filter(Website.id == website_id).first()
    if not website:
        logger.error(f"Website with ID {website_id} not found")
        return
    async with httpx.AsyncClient() as client:
        start_time = datetime.now(timezone.utc)
        try:
            validate_url(website.url)
            response = await client.get(website.url, timeout=10.0)
            response_time = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
            
            new_status = WebsiteStatus.UP if response.status_code == 200 else WebsiteStatus.DOWN
            

            status_check = StatusCheck(
                website_id=website.id,
                response_time_ms=response_time,
                status=new_status,
                error_message=None if new_status == WebsiteStatus.UP else f"HTTP {response.status_code}"
            )
            db.add(status_check)
            
        except httpx.TimeoutException as e:
            logger.error(f"Timeout checking {website.url}: {str(e)}")
            status_check = StatusCheck(
                website_id=website.id,
                status=WebsiteStatus.DOWN,
                error_message=f"Timeout after 10 seconds"
            )
            db.add(status_check)
            new_status = WebsiteStatus.DOWN

        except URLValidationError as e:
            logger.error(f"Invalid URL {website.url}: {str(e)}")
            status_check = StatusCheck(
                website_id=website.id,
                status=WebsiteStatus.DOWN,
                error_message=f"Invalid URL: {str(e)}"
            )
            db.add(status_check)
            new_status = WebsiteStatus.DOWN

        except httpx.RequestError as e:
            logger.error(f"Network error checking {website.url}: {str(e)}")
            status_check = StatusCheck(
                website_id=website.id,
                status=WebsiteStatus.DOWN,
                error_message=f"Network error: {str(e)}"
            )
            db.add(status_check)
            new_status = WebsiteStatus.DOWN

        except Exception as e:
            logger.error(f"Unexpected error checking {website.url}: {str(e)}")
            status_check = StatusCheck(
                website_id=website.id,
                status=WebsiteStatus.DOWN,
                error_message=f"Unexpected error: {str(e)}"
            )
            db.add(status_check)
            new_status = WebsiteStatus.DOWN

        try:

            if website.current_status != new_status:
                website.last_status_change = datetime.now(timezone.utc)
                website.current_status = new_status
                await send_discord_notification(website, new_status, db=db)

            website.last_checked = datetime.now(timezone.utc)
            db.commit()

        except Exception as e:
            logger.error(f"Error updating website status: {str(e)}")
            db.rollback()
            raise

async def send_discord_notification(website: Website, status: WebsiteStatus, db: Session,  max_retries: int = 3):
    webhooks = db.query(WebhookConfig).all()
    if not webhooks:
        return

    last_check = db.query(StatusCheck)\
        .filter(StatusCheck.website_id == website.id)\
        .order_by(StatusCheck.timestamp.desc())\
        .first()

    site_name = website.name or website.url
    current_time = datetime.now(timezone.utc)
    formatted_time = current_time.strftime("%Y-%m-%d %H:%M:%S UTC")

    if status == WebsiteStatus.DOWN:
        message = (
            f"🔴 Website Down Alert\n"
            f"Site: {site_name} ({website.url})\n"
            f"Status: DOWN\n"
            f"Time: {formatted_time}\n"
        )
        if last_check and last_check.error_message:
            message += f"Error: {last_check.error_message}"
    else:

        downtime_duration = ""
        if website.last_status_change:
            duration_seconds = (current_time - website.last_status_change).total_seconds()
            if duration_seconds < 60:
                downtime_duration = f"{int(duration_seconds)} seconds"
            elif duration_seconds < 3600:
                downtime_duration = f"{int(duration_seconds / 60)} minutes"
            else:
                hours = int(duration_seconds / 3600)
                minutes = int((duration_seconds % 3600) / 60)
                downtime_duration = f"{hours} hours {minutes} minutes"

        message = (
            f"🟢 Website Recovery Alert\n"
            f"Site: {site_name} ({website.url})\n"
            f"Status: UP\n"
            f"Time: {formatted_time}\n"
            f"Downtime Duration: {downtime_duration}"
        )

    failed_webhooks = []
    async with httpx.AsyncClient() as client:
        for webhook in webhooks:
            retries = 0
            while retries < max_retries:
                try:
                    response = await client.post(
                        str(webhook.url),
                        json={"content": message},
                        timeout=5.0
                    )
                    response.raise_for_status()
                    logger.info(f"Successfully sent notification to webhook {webhook.name or webhook.url}")
                    break
                except httpx.TimeoutException:
                    retries += 1
                    if retries == max_retries:
                        error_msg = f"Timeout sending notification to webhook {webhook.name or webhook.url}"
                        logger.error(error_msg)
                        failed_webhooks.append((webhook, error_msg))
                except httpx.HTTPStatusError as e:
                    error_msg = f"HTTP {e.response.status_code} error sending notification to webhook {webhook.name or webhook.url}"
                    logger.error(error_msg)
                    failed_webhooks.append((webhook, error_msg))
                    break
                except Exception as e:
                    error_msg = f"Unexpected error sending notification to webhook {webhook.name or webhook.url}: {str(e)}"
                    logger.error(error_msg)
                    failed_webhooks.append((webhook, error_msg))
                    break

    if failed_webhooks:
        raise WebhookDeliveryError(f"Failed to deliver to {len(failed_webhooks)} webhooks: {', '.join(msg for _, msg in failed_webhooks)}")

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
        await asyncio.sleep(10)


@app.post("/sites")
async def add_site(website: WebsiteCreate, db: Session = Depends(get_db), max_retries: int = 3):
    
    try:
        validate_url(str(website.url))
        db_website = Website(
            url=str(website.url),
            name=website.name,
            check_interval_seconds=website.check_interval_seconds
        )
        db.add(db_website)
        db.commit()
        db.refresh(db_website)
        return db_website
    except URLValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid URL: {str(e)}"
        )
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="URL already exists"
        )
    except Exception as e:
        db.rollback()
        logger.error(f"Error adding website: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )

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


@app.get("/sites/{website_id}/history", response_model=List[StatusCheckResponse])
async def get_site_history(
    website_id: int,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, le=1000),
    db: Session = Depends(get_db)
):
    website = db.query(Website).filter(Website.id == website_id).first()
    if not website:
        raise HTTPException(status_code=404, detail="Website not found")
    
    status_checks = db.query(StatusCheck)\
        .filter(StatusCheck.website_id == website_id)\
        .order_by(StatusCheck.timestamp.desc())\
        .offset(skip)\
        .limit(limit)\
        .all()
    
    return status_checks

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

