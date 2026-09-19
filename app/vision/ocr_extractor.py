import logging
import asyncio
from pathlib import Path
from typing import List, Tuple, Dict, Any
from app.config import settings

logger = logging.getLogger(__name__)

class OCRExtractor:
    def __init__(self):
        self.use_gpu = settings.OCR_USE_GPU
        self._reader = None

    def _load_reader(self):
        if self._reader is None:
            import easyocr
            try:
                logger.info(f"Loading EasyOCR reader (GPU={self.use_gpu})...")
                self._reader = easyocr.Reader(['en'], gpu=self.use_gpu)
            except Exception as e:
                logger.warning(f"Failed to load EasyOCR on GPU: {e}, falling back to CPU")
                self.use_gpu = False
                self._reader = easyocr.Reader(['en'], gpu=False)

    async def extract_text_from_frames(self, frames: List[Tuple[float, Path]]) -> List[Dict[str, Any]]:
        """
        Runs OCR on keyframes and deduplicates text overlays.
        Returns: [{"timestamp": 1.5, "text": "Detected text overlay"}, ...]
        """
        def _sync_ocr():
            try:
                self._load_reader()
            except Exception as e:
                logger.error(f"Error initializing OCR reader: {e}")
                return []

            results = []
            last_text = ""

            for timestamp, frame_path in frames:
                try:
                    ocr_res = self._reader.readtext(str(frame_path), detail=0, paragraph=True)
                    joined = " ".join([t.strip() for t in ocr_res if len(t.strip()) > 3])
                    
                    # Deduplicate consecutive identical text
                    if joined and joined != last_text:
                        results.append({
                            "timestamp": timestamp,
                            "text": joined
                        })
                        last_text = joined
                except Exception as e:
                    logger.debug(f"OCR error on frame {frame_path}: {e}")
                    # If GPU ran out of memory mid-run, fallback to CPU
                    if "out of memory" in str(e).lower() or "cuda" in str(e).lower():
                        logger.warning("CUDA OOM in OCR, switching reader to CPU...")
                        try:
                            import easyocr
                            self.use_gpu = False
                            self._reader = easyocr.Reader(['en'], gpu=False)
                        except Exception:
                            pass

            return results

        loop = asyncio.get_running_loop()
        try:
            return await loop.run_in_executor(None, _sync_ocr)
        except Exception as e:
            logger.error(f"OCR pipeline error: {e}")
            return []
