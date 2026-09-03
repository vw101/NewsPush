import logging
import asyncio
from fastapi import FastAPI, Request, BackgroundTasks
from fastapi.responses import JSONResponse
from src.pipeline import NewsPipeline

logger = logging.getLogger(__name__)
app = FastAPI(title="AI Daily Pulse Feishu Bot Server")


@app.post("/feishu/event")
async def feishu_event_handler(request: Request, background_tasks: BackgroundTasks):
    """
    Feishu Open Platform Event Subscription Listener Endpoint.
    Handles URL Challenge Verification and @mention Message Events.
    """
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"msg": "invalid json"})

    # 1. Handle Feishu URL Challenge Verification
    if body.get("type") == "url_verification" or "challenge" in body:
        return JSONResponse(content={"challenge": body.get("challenge")})

    # 2. Handle Message Event
    header = body.get("header", {})
    if header.get("event_type") == "im.message.receive_v1":
        event = body.get("event", {})
        message = event.get("message", {})
        content_str = message.get("content", "")

        text = content_str.lower()
        if "新闻" in text or "news" in text:
            logger.info("Received @mention news trigger in Feishu event handler. Queuing pipeline run...")
            background_tasks.add_task(run_pipeline_task)

    return JSONResponse(content={"msg": "success"})


def run_pipeline_task():
    """Background execution of the news aggregation pipeline."""
    try:
        pipeline = NewsPipeline()
        res = pipeline.run(force_push=True)
        logger.info(f"Background news pipeline completed: {res}")
    except Exception as e:
        logger.error(f"Background news pipeline error: {e}")


def start_server(host: str = "0.0.0.0", port: int = 8000):
    import uvicorn
    logger.info(f"Starting Feishu Event Listener Server on {host}:{port}...")
    uvicorn.run(app, host=host, port=port)
