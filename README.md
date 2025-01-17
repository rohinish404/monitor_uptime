# Website Uptime Monitor with Discord Notifications

A simple service that monitors website availability and sends notifications through Discord webhooks when a site goes down or recovers.

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

Install dependencies using [uv](https://docs.astral.sh/uv/).

```bash
  uv install
```

Start the server via uvicorn.

```bash
  uvicorn main:app --reload
```




