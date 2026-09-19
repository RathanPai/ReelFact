import logging
import asyncio
from pathlib import Path
from typing import List, Dict, Any
from app.config import settings

logger = logging.getLogger(__name__)

class AudioTranscriber:
    def __init__(self):
        self.model_size = settings.WHISPER_MODEL
        self.device = settings.WHISPER_DEVICE
        self.compute_type = settings.WHISPER_COMPUTE_TYPE
        self._model = None

    def _load_model(self):
        if self._model is None:
            try:
                from faster_whisper import WhisperModel
                logger.info(f"Loading faster-whisper model '{self.model_size}' on {self.device} ({self.compute_type})...")
                self._model = WhisperModel(
                    self.model_size,
                    device=self.device,
                    compute_type=self.compute_type
                )
            except Exception as e:
                logger.warning(f"Failed to load Whisper on {self.device}: {e}, falling back to CPU float32")
                from faster_whisper import WhisperModel
                self._model = WhisperModel(self.model_size, device="cpu", compute_type="int8")

    async def transcribe(self, audio_path: Path) -> List[Dict[str, Any]]:
        """
        Transcribes audio file and returns list of timestamped segments:
        [{"start": 0.0, "end": 2.5, "text": "hello world"}, ...]
        """
        def _sync_transcribe():
            self._load_model()
            segments, info = self._model.transcribe(
                str(audio_path),
                beam_size=5,
                word_timestamps=True,
                vad_filter=True
            )
            
            output_segments = []
            for seg in segments:
                output_segments.append({
                    "start": float(seg.start),
                    "end": float(seg.end),
                    "text": seg.text.strip(),
                })
            return output_segments

        loop = asyncio.get_running_loop()
        try:
            return await loop.run_in_executor(None, _sync_transcribe)
        except Exception as e:
            logger.error(f"Whisper transcription error: {e}")
            return []
