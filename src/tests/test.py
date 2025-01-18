import pytest
from unittest.mock import Mock, patch, AsyncMock
import httpx
import logging
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base
from models import Website, StatusCheck, WebhookConfig
from utils import URLValidationError, WebhookDeliveryError
from schemas import WebsiteStatus
from main import (
    check_website, send_discord_notification, app, validate_url,
)


SQLALCHEMY_TEST_DATABASE_URL = "sqlite:///./test_website_monitor.db"
engine = create_engine(SQLALCHEMY_TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


logger = logging.getLogger(__name__)

@pytest.fixture(scope="function")
def db_session():
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        logger.info("Test database cleaned up")

@pytest.fixture
def test_website(db_session):
    """Fixture for creating a test website"""
    website = Website(
        url="https://example.com",
        name="Example Site",
        check_interval_seconds=300,
        current_status=WebsiteStatus.UNKNOWN
    )
    try:
        db_session.add(website)
        db_session.commit()
        db_session.refresh(website)
        logger.info(f"Test website created with ID: {website.id}")
        return website
    except Exception as e:
        logger.error(f"Failed to create test website: {str(e)}")
        raise

@pytest.fixture
def test_webhook(db_session):
    webhook = WebhookConfig(
        url="https://discord.com/api/webhooks/test",
        name="Test Webhook"
    )
    try:
        db_session.add(webhook)
        db_session.commit()
        db_session.refresh(webhook)
        logger.info(f"Test webhook created with ID: {webhook.id}")
        return webhook
    except Exception as e:
        logger.error(f"Failed to create test webhook: {str(e)}")
        raise

@pytest.mark.asyncio
async def test_check_website_success(db_session, test_website):
    mock_response = Mock()
    mock_response.status_code = 200
    
    with patch('httpx.AsyncClient.get', new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_response
        
        try:
            await check_website(test_website.id, db_session)
            logger.info("Website check completed successfully")
            
            updated_website = db_session.query(Website).filter_by(id=test_website.id).first()
            assert updated_website.current_status == WebsiteStatus.UP
            assert updated_website.last_checked is not None
            
            status_check = db_session.query(StatusCheck).filter_by(website_id=test_website.id).first()
            assert status_check is not None
            assert status_check.status == WebsiteStatus.UP
            assert status_check.error_message is None
        except Exception as e:
            logger.error(f"Test failed: {str(e)}")
            raise

@pytest.mark.asyncio
async def test_check_website_failure(db_session, test_website):
    """Test website check failure"""
    with patch('httpx.AsyncClient.get', new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = httpx.RequestError("Connection failed")
        
        try:
            await check_website(test_website.id, db_session)
            logger.info("Website check failure test completed")
            
            updated_website = db_session.query(Website).filter_by(id=test_website.id).first()
            assert updated_website.current_status == WebsiteStatus.DOWN
            assert updated_website.last_checked is not None
            
            status_check = db_session.query(StatusCheck).filter_by(website_id=test_website.id).first()
            assert status_check is not None
            assert status_check.status == WebsiteStatus.DOWN
            assert "Connection failed" in status_check.error_message
        except Exception as e:
            logger.error(f"Test failed: {str(e)}")
            raise

@pytest.mark.asyncio
async def test_check_website_timeout(db_session, test_website):
    """Test website check timeout"""
    with patch('httpx.AsyncClient.get', new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = httpx.TimeoutException("Timeout")
        
        try:
            await check_website(test_website.id, db_session)
            logger.info("Website check timeout test completed")
            
            updated_website = db_session.query(Website).filter_by(id=test_website.id).first()
            assert updated_website.current_status == WebsiteStatus.DOWN
            
            status_check = db_session.query(StatusCheck).filter_by(website_id=test_website.id).first()
            assert status_check is not None
            assert status_check.status == WebsiteStatus.DOWN
            assert "Timeout" in status_check.error_message
        except Exception as e:
            logger.error(f"Test failed: {str(e)}")
            raise

@pytest.mark.asyncio
async def test_discord_notification(db_session, test_website, test_webhook):
    """Test Discord notification sending"""
    with patch('httpx.AsyncClient.post', new_callable=AsyncMock) as mock_post:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response
        
        try:
            test_website.current_status = WebsiteStatus.DOWN
            await send_discord_notification(test_website, WebsiteStatus.DOWN, db_session)
            logger.info("Discord notification test completed")
            
            mock_post.assert_called_once()
            call_kwargs = mock_post.call_args[1]
            assert "Website Down Alert" in call_kwargs['json']['content']
            assert test_website.url in call_kwargs['json']['content']
        except Exception as e:
            logger.error(f"Test failed: {str(e)}")
            raise

@pytest.mark.asyncio
async def test_discord_notification_failure(db_session, test_website, test_webhook):
    """Test Discord notification failure"""
    with patch('httpx.AsyncClient.post', new_callable=AsyncMock) as mock_post:
        mock_post.side_effect = httpx.RequestError("Failed to send notification")
        
        with pytest.raises(WebhookDeliveryError):
            await send_discord_notification(test_website, WebsiteStatus.DOWN, db_session)
            logger.error("Discord notification failure test completed")

def test_url_validation():
    """Test URL validation"""
    try:
        assert validate_url("https://example.com") == True
        assert validate_url("http://test.com") == True
        logger.info("URL validation test passed")
        
        with pytest.raises(URLValidationError):
            validate_url("not-a-url")
        
        with pytest.raises(URLValidationError):
            validate_url("ftp://example.com")
    except Exception as e:
        logger.error(f"URL validation test failed: {str(e)}")
        raise

@pytest.mark.asyncio
async def test_api_endpoints():
    """Test API endpoints"""
    client = TestClient(app)
    
    try:
        response = client.post(
            "/sites",
            json={
                "url": "https://example3.com",
                "name": "Example Site",
                "check_interval_seconds": 300,
                "expected_status_code": 200
            }
        )
        assert response.status_code == 200
        site_id = response.json()["id"]
        logger.info(f"Test site created with ID: {site_id}")
        
        response = client.get("/sites")
        assert response.status_code == 200
        assert len(response.json()) > 0
        logger.info("Retrieved all sites successfully")
        
        response = client.get(f"/sites/{site_id}/history")
        assert response.status_code == 200
        logger.info(f"Retrieved history for site {site_id}")
        
        response = client.delete(f"/sites/{site_id}")
        assert response.status_code == 200
        logger.info(f"Deleted site {site_id}")
    except Exception as e:
        logger.error(f"API endpoint test failed: {str(e)}")
        raise