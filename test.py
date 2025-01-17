import pytest
from unittest.mock import Mock, patch, AsyncMock
import httpx
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from main import (
    Base, Website, StatusCheck, WebhookConfig, WebsiteStatus,
    check_website, send_discord_notification, app, validate_url,
    URLValidationError, WebhookDeliveryError
)

SQLALCHEMY_TEST_DATABASE_URL = "sqlite:///./test_website_monitor.db"
engine = create_engine(SQLALCHEMY_TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(scope="function")
def db_session():
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)

@pytest.fixture
def test_website(db_session):
    website = Website(
        url="https://example.com",
        name="Example Site",
        check_interval_seconds=300,
        current_status=WebsiteStatus.UNKNOWN
    )
    db_session.add(website)
    db_session.commit()
    db_session.refresh(website)
    return website

@pytest.fixture
def test_webhook(db_session):
    webhook = WebhookConfig(
        url="https://discord.com/api/webhooks/test",
        name="Test Webhook"
    )
    db_session.add(webhook)
    db_session.commit()
    db_session.refresh(webhook)
    return webhook

@pytest.mark.asyncio
async def test_check_website_success(db_session, test_website):
    mock_response = Mock()
    mock_response.status_code = 200
    
    with patch('httpx.AsyncClient.get', new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_response
        
        await check_website(test_website.id, db_session)
        
        updated_website = db_session.query(Website).filter_by(id=test_website.id).first()
        assert updated_website.current_status == WebsiteStatus.UP
        assert updated_website.last_checked is not None
        
        status_check = db_session.query(StatusCheck).filter_by(website_id=test_website.id).first()
        assert status_check is not None
        assert status_check.status == WebsiteStatus.UP
        assert status_check.error_message is None

@pytest.mark.asyncio
async def test_check_website_failure(db_session, test_website):

    with patch('httpx.AsyncClient.get', new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = httpx.RequestError("Connection failed")
        
        await check_website(test_website.id, db_session)
        
        updated_website = db_session.query(Website).filter_by(id=test_website.id).first()
        assert updated_website.current_status == WebsiteStatus.DOWN
        assert updated_website.last_checked is not None
        
        status_check = db_session.query(StatusCheck).filter_by(website_id=test_website.id).first()
        assert status_check is not None
        assert status_check.status == WebsiteStatus.DOWN
        assert "Connection failed" in status_check.error_message

@pytest.mark.asyncio
async def test_check_website_timeout(db_session, test_website):
    with patch('httpx.AsyncClient.get', new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = httpx.TimeoutException("Timeout")
        
        await check_website(test_website.id, db_session)
        
        updated_website = db_session.query(Website).filter_by(id=test_website.id).first()
        assert updated_website.current_status == WebsiteStatus.DOWN
        
        status_check = db_session.query(StatusCheck).filter_by(website_id=test_website.id).first()
        assert status_check is not None
        assert status_check.status == WebsiteStatus.DOWN
        assert "Timeout" in status_check.error_message

@pytest.mark.asyncio
async def test_discord_notification(db_session, test_website, test_webhook):
    with patch('httpx.AsyncClient.post', new_callable=AsyncMock) as mock_post:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response
        
        test_website.current_status = WebsiteStatus.DOWN
        await send_discord_notification(test_website, WebsiteStatus.DOWN, db_session)
        
        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args[1]
        assert "Website Down Alert" in call_kwargs['json']['content']
        assert test_website.url in call_kwargs['json']['content']

@pytest.mark.asyncio
async def test_discord_notification_failure(db_session, test_website, test_webhook):
    with patch('httpx.AsyncClient.post', new_callable=AsyncMock) as mock_post:
        mock_post.side_effect = httpx.RequestError("Failed to send notification")
        
        with pytest.raises(WebhookDeliveryError):
            await send_discord_notification(test_website, WebsiteStatus.DOWN, db_session)

def test_url_validation():
    assert validate_url("https://example.com") == True
    assert validate_url("http://test.com") == True
    
    with pytest.raises(URLValidationError):
        validate_url("not-a-url")
    
    with pytest.raises(URLValidationError):
        validate_url("ftp://example.com")

@pytest.mark.asyncio
async def test_api_endpoints():
    client = TestClient(app)
    
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
    
    response = client.get("/sites")
    assert response.status_code == 200
    assert len(response.json()) > 0
    
    response = client.get(f"/sites/{site_id}/history")
    assert response.status_code == 200
    
    response = client.delete(f"/sites/{site_id}")
    assert response.status_code == 200