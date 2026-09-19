import os
import json
import uuid
import hashlib
import logging
import asyncio
from pathlib import Path
from typing import Dict, Any, Optional, Tuple
import yt_dlp
from app.config import settings

logger = logging.getLogger(__name__)

class ReelDownloader:
    def __init__(self):
        self.raw_dir = settings.RAW_DIR
        self.raw_dir.mkdir(parents=True, exist_ok=True)

    def generate_video_id(self, url: Optional[str] = None) -> str:
        """Generates a unique deterministic or random video ID."""
        if url:
            clean_url = url.split("?")[0].rstrip("/")
            return hashlib.md5(clean_url.encode()).hexdigest()[:12]
        return uuid.uuid4().hex[:12]

    async def download_reel(self, url: str) -> Tuple[str, Path, Dict[str, Any]]:
        """
        Downloads Instagram Reel or video from URL using yt-dlp.
        Returns: (video_id, video_path, metadata)
        """
        video_id = self.generate_video_id(url)
        output_template = str(self.raw_dir / f"{video_id}.%(ext)s")
        meta_path = self.raw_dir / f"{video_id}.json"

        # If already downloaded, load cached
        existing_videos = list(self.raw_dir.glob(f"{video_id}.*"))
        existing_mp4 = [f for f in existing_videos if f.suffix in [".mp4", ".mov", ".mkv", ".webm"]]
        if existing_mp4 and meta_path.exists():
            try:
                with open(meta_path, "r", encoding="utf-8") as f:
                    metadata = json.load(f)
                return video_id, existing_mp4[0], metadata
            except Exception:
                pass

        ydl_opts = {
            "outtmpl": output_template,
            "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
            "merge_output_format": "mp4",
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        }

        def _sync_download():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                return info

        loop = asyncio.get_running_loop()
        try:
            info = await loop.run_in_executor(None, _sync_download)
            
            metadata = {
                "id": video_id,
                "url": url,
                "title": info.get("title") or "Instagram Reel",
                "caption": info.get("description") or "",
                "author": info.get("uploader") or info.get("channel") or "Instagram Creator",
                "duration": info.get("duration") or 0.0,
                "thumbnail": info.get("thumbnail") or "",
            }

            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(metadata, f, indent=2)

            # Find actual output video path
            downloaded = list(self.raw_dir.glob(f"{video_id}.*"))
            mp4_files = [f for f in downloaded if f.suffix in [".mp4", ".mov", ".mkv", ".webm"]]
            if not mp4_files:
                raise FileNotFoundError(f"Video file not found after download in {self.raw_dir}")

            return video_id, mp4_files[0], metadata
        except Exception as e:
            logger.error(f"yt-dlp download failed for URL {url}: {e}")
            raise

    async def save_uploaded_file(self, file_bytes: bytes, filename: str) -> Tuple[str, Path, Dict[str, Any]]:
        """Saves a user-uploaded video file as a fallback."""
        video_id = self.generate_video_id()
        ext = Path(filename).suffix or ".mp4"
        video_path = self.raw_dir / f"{video_id}{ext}"

        with open(video_path, "wb") as f:
            f.write(file_bytes)

        metadata = {
            "id": video_id,
            "url": None,
            "title": Path(filename).stem,
            "caption": "Uploaded Video File",
            "author": "Local Upload",
            "duration": 0.0,
            "thumbnail": None
        }

        meta_path = self.raw_dir / f"{video_id}.json"
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2)

        return video_id, video_path, metadata
