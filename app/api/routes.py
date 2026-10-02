import os
import json
import logging
import asyncio
from pathlib import Path
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, BackgroundTasks, Query
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel

from app.config import settings
from app.pipeline import FactCheckPipeline
from app.agent.follow_up_agent import FollowUpAgent
from app.database.storage import (
    get_reel_dossier,
    get_reel_transcript,
    get_chat_history,
    save_chat_message,
    list_recent_reels,
    init_db
)

logger = logging.getLogger(__name__)
router = APIRouter()

# Global pipeline & in-memory progress tracker for active tasks
pipeline = FactCheckPipeline()
chat_agent = FollowUpAgent()
active_tasks: Dict[str, Dict[str, Any]] = {}

class CheckUrlRequest(BaseModel):
    url: str

class ChatMessageRequest(BaseModel):
    video_id: str
    message: str



@router.post("/check/url")
async def check_reel_url(req: CheckUrlRequest, background_tasks: BackgroundTasks):
    """Initiates fact-checking for an Instagram Reel URL."""
    url = req.url.strip()
    if not url or "instagram.com" not in url and not url.startswith("http"):
        raise HTTPException(status_code=400, detail="Please provide a valid video or Instagram Reel URL.")

    # Generate a task ID
    video_id = pipeline.downloader.generate_video_id(url)
    active_tasks[video_id] = {
        "status": "queued",
        "step": "Initializing Pipeline",
        "progress": 5,
        "video_id": video_id,
        "error": None
    }

    async def _run():
        def _callback(step_name: str, progress: int, data: Dict[str, Any]):
            active_tasks[video_id] = {
                "status": "processing" if progress < 100 else "done",
                "step": step_name,
                "progress": progress,
                "video_id": video_id,
                "error": None,
                "data": data
            }

        try:
            dossier = await pipeline.run_pipeline(url=url, status_callback=_callback)
            active_tasks[video_id]["status"] = "done"
            active_tasks[video_id]["dossier"] = dossier.model_dump()
        except Exception as e:
            logger.error(f"Pipeline error for video_id {video_id}: {e}")
            active_tasks[video_id]["status"] = "error"
            active_tasks[video_id]["error"] = str(e)

    background_tasks.add_task(_run)
    return {"video_id": video_id, "status": "queued", "message": "Fact-checking process started"}


@router.post("/check/upload")
async def check_reel_upload(
    file: UploadFile = File(...),
    background_tasks: BackgroundTasks = None
):
    """Uploads a video file and initiates fact checking."""
    content = await file.read()
    video_id = pipeline.downloader.generate_video_id()

    active_tasks[video_id] = {
        "status": "queued",
        "step": "Saving Uploaded Video",
        "progress": 5,
        "video_id": video_id,
        "error": None
    }

    async def _run():
        def _callback(step_name: str, progress: int, data: Dict[str, Any]):
            active_tasks[video_id] = {
                "status": "processing" if progress < 100 else "done",
                "step": step_name,
                "progress": progress,
                "video_id": video_id,
                "error": None,
                "data": data
            }

        try:
            dossier = await pipeline.run_pipeline(
                file_bytes=content,
                filename=file.filename or "uploaded.mp4",
                status_callback=_callback
            )
            active_tasks[video_id]["status"] = "done"
            active_tasks[video_id]["dossier"] = dossier.model_dump()
        except Exception as e:
            logger.error(f"Pipeline upload error for video_id {video_id}: {e}")
            active_tasks[video_id]["status"] = "error"
            active_tasks[video_id]["error"] = str(e)

    background_tasks.add_task(_run)
    return {"video_id": video_id, "status": "queued", "message": "Video uploaded and processing"}


@router.get("/status/{video_id}")
async def get_task_status(video_id: str):
    """Returns the current real-time processing status of a reel."""
    if video_id in active_tasks:
        return active_tasks[video_id]

    # If not active in memory, check if already completed in database
    dossier = await get_reel_dossier(video_id)
    if dossier:
        return {
            "status": "done",
            "step": "Fact-Check Complete",
            "progress": 100,
            "video_id": video_id,
            "dossier": dossier.model_dump()
        }

    return {"status": "not_found", "progress": 0, "video_id": video_id}


@router.get("/reels/{video_id}")
async def get_reel(video_id: str):
    """Returns complete dossier and transcript for a fact-checked reel."""
    dossier = await get_reel_dossier(video_id)
    if not dossier:
        raise HTTPException(status_code=404, detail="Reel dossier not found")
    
    transcript = await get_reel_transcript(video_id)
    chat_history = await get_chat_history(video_id)

    return {
        "dossier": dossier.model_dump(),
        "transcript": transcript.model_dump() if transcript else None,
        "chat_history": chat_history
    }


@router.get("/reels")
async def list_reels():
    """Lists recently fact-checked reels."""
    return await list_recent_reels()


@router.post("/chat")
async def send_chat_message(req: ChatMessageRequest):
    """Handles follow-up conversational QA for a specific reel."""
    video_id = req.video_id
    question = req.message.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    dossier = await get_reel_dossier(video_id)
    if not dossier:
        raise HTTPException(status_code=404, detail="Reel dossier not found for this session")

    transcript = await get_reel_transcript(video_id)
    chat_history = await get_chat_history(video_id)

    # Save user message
    await save_chat_message(video_id, "user", question)

    # Generate answer with follow-up conversational agent
    answer = await chat_agent.answer_question(
        video_id=video_id,
        question=question,
        dossier=dossier,
        transcript=transcript,
        chat_history=chat_history
    )

    # Save assistant message
    await save_chat_message(video_id, "assistant", answer)

    return {
        "video_id": video_id,
        "question": question,
        "answer": answer
    }


@router.get("/media/{video_id}")
async def stream_reel_video(video_id: str):
    """Serves the raw video file for the HTML5 player."""
    for ext in [".mp4", ".mov", ".mkv", ".webm"]:
        fpath = settings.RAW_DIR / f"{video_id}{ext}"
        if fpath.exists():
            return FileResponse(path=str(fpath), media_type="video/mp4")
    raise HTTPException(status_code=404, detail="Video media file not found")


@router.get("/media/frame/{video_id}/{frame_name}")
async def get_frame_image(video_id: str, frame_name: str):
    """Serves an extracted video keyframe image."""
    fpath = settings.FRAMES_DIR / video_id / frame_name
    if fpath.exists():
        return FileResponse(path=str(fpath), media_type="image/jpeg")
    raise HTTPException(status_code=404, detail="Keyframe image not found")

