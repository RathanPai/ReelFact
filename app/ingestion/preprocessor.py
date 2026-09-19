import os
import subprocess
import asyncio
import logging
from pathlib import Path
from typing import List, Tuple
from app.config import settings

logger = logging.getLogger(__name__)

class VideoPreprocessor:
    def __init__(self):
        self.audio_dir = settings.AUDIO_DIR
        self.frames_dir = settings.FRAMES_DIR
        self.audio_dir.mkdir(parents=True, exist_ok=True)
        self.frames_dir.mkdir(parents=True, exist_ok=True)

    async def extract_audio(self, video_path: Path, video_id: str) -> Path:
        """
        Extracts 16kHz mono WAV audio track from video using ffmpeg.
        """
        output_audio_path = self.audio_dir / f"{video_id}.wav"
        if output_audio_path.exists() and output_audio_path.stat().st_size > 1000:
            return output_audio_path

        cmd = [
            "ffmpeg", "-y",
            "-i", str(video_path),
            "-vn",
            "-acodec", "pcm_s16le",
            "-ar", "16000",
            "-ac", "1",
            str(output_audio_path)
        ]

        def _run_ffmpeg():
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if res.returncode != 0:
                logger.error(f"FFmpeg audio extraction error: {res.stderr.decode('utf-8', errors='ignore')}")
                raise RuntimeError(f"FFmpeg failed to extract audio: {res.stderr.decode('utf-8', errors='ignore')}")

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, _run_ffmpeg)
        return output_audio_path

    async def extract_keyframes(self, video_path: Path, video_id: str, interval_sec: float = 1.5) -> List[Tuple[float, Path]]:
        """
        Extracts keyframes at regular intervals.
        Returns: list of (timestamp_seconds, frame_path)
        """
        reel_frames_dir = self.frames_dir / video_id
        reel_frames_dir.mkdir(parents=True, exist_ok=True)

        # Check if already extracted
        existing = sorted(list(reel_frames_dir.glob("frame_*.jpg")))
        if existing:
            frames = []
            for f in existing:
                try:
                    # Filename format: frame_0001_timestamp_1.50.jpg
                    ts_str = f.stem.split("_ts_")[-1]
                    frames.append((float(ts_str), f))
                except Exception:
                    pass
            if frames:
                return frames

        # Use ffmpeg fps filter to extract frames at 1/interval_sec rate
        fps_rate = 1.0 / interval_sec
        pattern = str(reel_frames_dir / "frame_%04d.jpg")

        cmd = [
            "ffmpeg", "-y",
            "-i", str(video_path),
            "-vf", f"fps={fps_rate}",
            "-q:v", "2",
            pattern
        ]

        def _run_frame_extract():
            subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, _run_frame_extract)

        extracted_files = sorted(list(reel_frames_dir.glob("frame_*.jpg")))
        timed_frames: List[Tuple[float, Path]] = []

        for idx, f in enumerate(extracted_files):
            timestamp = idx * interval_sec
            renamed_path = reel_frames_dir / f"frame_{idx:04d}_ts_{timestamp:.2f}.jpg"
            f.rename(renamed_path)
            timed_frames.append((timestamp, renamed_path))

        return timed_frames
