import logging
from typing import List, Dict, Any, Optional
from app.claims.models import MultimodalTranscript, MultimodalSegment

logger = logging.getLogger(__name__)

class MultimodalFusion:
    @staticmethod
    def fuse_timeline(
        video_id: str,
        title: str,
        author: str,
        caption: str,
        duration_seconds: float,
        audio_segments: List[Dict[str, Any]],
        ocr_entries: List[Dict[str, Any]]
    ) -> MultimodalTranscript:
        """
        Merges audio transcripts and OCR detections into aligned temporal segments.
        """
        # Collect all timestamps
        time_points = set([0.0, duration_seconds])
        for seg in audio_segments:
            time_points.add(round(seg["start"], 1))
            time_points.add(round(seg["end"], 1))
        for o in ocr_entries:
            time_points.add(round(o["timestamp"], 1))
            time_points.add(round(o["timestamp"] + 1.5, 1))

        sorted_times = sorted(list(time_points))
        multimodal_segments: List[MultimodalSegment] = []

        all_audio_texts = []
        all_ocr_texts = []

        for i in range(len(sorted_times) - 1):
            t_start = sorted_times[i]
            t_end = sorted_times[i+1]
            if t_end - t_start < 0.2:
                continue

            # Find matching audio
            matched_audio = []
            for a in audio_segments:
                if not (a["end"] <= t_start or a["start"] >= t_end):
                    if a["text"] not in matched_audio:
                        matched_audio.append(a["text"])

            # Find matching OCR
            matched_ocr = []
            for o in ocr_entries:
                o_ts = o["timestamp"]
                if t_start <= o_ts <= t_end or (o_ts <= t_start and (o_ts + 1.5) >= t_end):
                    if o["text"] not in matched_ocr:
                        matched_ocr.append(o["text"])

            if matched_audio or matched_ocr:
                multimodal_segments.append(MultimodalSegment(
                    start=t_start,
                    end=t_end,
                    audio_text=" ".join(matched_audio),
                    ocr_text=" | ".join(matched_ocr)
                ))

        full_audio = " ".join([a["text"] for a in audio_segments])
        all_ocr = [o["text"] for o in ocr_entries]

        return MultimodalTranscript(
            video_id=video_id,
            title=title,
            caption=caption,
            author=author,
            duration_seconds=duration_seconds,
            segments=multimodal_segments,
            full_audio_text=full_audio,
            all_ocr_texts=all_ocr
        )
