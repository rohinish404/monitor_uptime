# Website Uptime Monitor with Discord Notifications

A simple service that monitors website availability and sends notifications through Discord webhooks when a site goes down or recovers.

## Demo

https://github.com/user-attachments/assets/2033802f-c5ef-478f-8abc-f0811290442a


## Features

- Real-time website monitoring
- Customizable check intervals per website
- Discord webhook notifications for status changes
- Detailed monitoring history
- RESTful API for management
- Automatic retry mechanism for webhook delivery

## Tech Stack

- FastAPI
- Discord webhooks
- Asyncio
- SQLAlchemy
- Pytest


## Run Locally

Clone the project

```bash
  git clone https://github.com/rohinish404/monitor_uptime
```

Go to the project directory

```bash
  cd monitor_uptime
```

Create venv and Install dependencies using [uv](https://docs.astral.sh/uv/).

```bash
  uv venv
  source .venv/bin/activate
  uv sync
```

Start the server via uvicorn.

```bash
  cd src
  uvicorn main:app --reload
```


## API Documentation



## Table of Contents

- [Configuration](#configuration)
- [Running the Service](#running-the-service)
- [API Documentation](#api-documentation)
- [Webhook Notifications](#webhook-notifications)
- [Error Handling](#error-handling)

## Configuration

The service uses SQLAlchemy for database operations. Make sure to configure your database connection in `database.py`. For now instead of `.env`, the database url is already present in the same file.

Environment variables (create a `.env` file):
```
DATABASE_URL=sqlite:///./monitor.db  # Example for SQLite
```

## Running the Service

1. Start the server (Make sure you're inside the src folder):
```bash
uvicorn main:app --reload
```

2. Access the API documentation:
```
http://localhost:8000/docs
```

## API Documentation

### Add Website

Add a new website to monitor.

**Endpoint:** `POST /sites`

**Request Body:**
```json
{
  "url": "https://example.com",
  "name": "Example Site",
  "check_interval_seconds": 300
}
```

**Response:**
```json
{
  "id": 1,
  "url": "https://example.com",
  "name": "Example Site",
  "check_interval_seconds": 300,
  "current_status": "UP",
  "last_checked": "2024-01-18T10:00:00Z",
  "last_status_change": "2024-01-18T10:00:00Z"
}
```

### List Websites

Get all monitored websites.

**Endpoint:** `GET /sites`

**Response:**
```json
[
  {
    "id": 1,
    "url": "https://example.com",
    "name": "Example Site",
    "check_interval_seconds": 300,
    "current_status": "UP",
    "last_checked": "2024-01-18T10:00:00Z",
    "last_status_change": "2024-01-18T10:00:00Z"
  }
]
```

### Remove Website

Remove a website from monitoring.

**Endpoint:** `DELETE /sites/{website_id}`

**Response:**
```json
{
  "status": "success"
}
```

### Get Website History

Retrieve monitoring history for a specific website.

**Endpoint:** `GET /sites/{website_id}/history`

**Query Parameters:**
- `skip`: Number of records to skip (default: 0)
- `limit`: Maximum number of records to return (default: 100, max: 1000)

**Response:**
```json
[
  {
    "id": 1,
    "website_id": 1,
    "timestamp": "2024-01-18T10:00:00Z",
    "status": "UP",
    "response_time_ms": 156.4,
    "error_message": null
  }
]
```

### Add Discord Webhook

Configure a Discord webhook for notifications.

**Endpoint:** `POST /webhook`

**Request Body:**
```json
{
  "url": "https://discord.com/api/webhooks/...",
  "name": "Main Channel"
}
```

**Response:**
```json
{
  "id": 1,
  "url": "https://discord.com/api/webhooks/...",
  "name": "Main Channel"
}
```

## Webhook Notifications

The service sends formatted notifications to Discord when website status changes:

### Down Alert
```
🔴 Website Down Alert
Site: Example Site (https://example.com)
Status: DOWN
Time: 2024-01-18 10:00:00 UTC
Error: HTTP 503
```

### Recovery Alert
```
🟢 Website Recovery Alert
Site: Example Site (https://example.com)
Status: UP
Time: 2024-01-18 10:30:00 UTC
Downtime Duration: 30 minutes
```

## Error Handling

The service includes robust error handling for:
- Invalid URLs
- Network timeouts (10-second timeout)
- Webhook delivery failures (3 retry attempts)
- Database connection issues
- Duplicate website entries

## Testing

The application includes comprehensive test coverage using pytest for both synchronous and asynchronous operations. Tests are configured to use SQLite as the test database.

### Test Coverage

- **Database Operations**: Fixtures provide clean database sessions and test entities for each test
- **Website Monitoring**:
  - Successful status checks
  - Failed connection handling
  - Timeout scenario handling
- **Discord Notifications**:
  - Successful webhook delivery
  - Failed notification handling
- **URL Validation**:
  - Valid HTTP/HTTPS URLs
  - Invalid URL format detection
- **API Endpoints**:
  - Site creation
  - Site listing
  - History retrieval
  - Site deletion

### Running Tests

```bash
cd src
pytest tests/test.py
```

## Architecture Decisions

### Asynchronous Monitoring:

- Uses Python's asyncio and httpx for non-blocking website checks
- The monitor_websites() function runs as a background task, continuously checking sites based on their intervals
- This approach prevents head-of-line blocking where a slow website check would delay others
- Efficient resource utilization since the system doesn't spawn new threads for each check

### Error Handling & Resilience:

- Comprehensive error handling for network issues, timeouts, and validation errors
- Retry mechanism for webhook notifications
- Transaction management to maintain data consistency
- Logging system for operational monitoring

### Data Storage Design

### SQLAlchemy ORM Approach:

- Uses SQLAlchemy for database abstraction and ORM capabilities
- Session management through dependency injection
- Supports multiple database backends without code changes

### Data Model Design:

- Separates concerns into distinct models (Website, StatusCheck, WebhookConfig)
- Stores temporal data (last_checked, last_status_change) for monitoring and reporting

### Storage Efficiency:

- Only stores status changes and periodic checks rather than continuous monitoring data
- Uses pagination for history retrieval to manage large datasets
- Maintains historical data for analysis while keeping current status readily available

