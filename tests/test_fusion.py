import pytest
from app.vision.fusion import MultimodalFusion

def test_multimodal_timeline_fusion():
    audio_segments = [
        {"start": 0.0, "end": 3.0, "text": "Drinking cold water every morning"},
        {"start": 3.0, "end": 6.5, "text": "burns 500 calories instantly."}
    ]
    ocr_entries = [
        {"timestamp": 1.5, "text": "SHOCKING WEIGHT LOSS HACK"},
        {"timestamp": 4.0, "text": "500 CALORIES BURNED"}
    ]

    transcript = MultimodalFusion.fuse_timeline(
        video_id="test_video_123",
        title="Weight Loss Hack",
        author="HealthInfluencer",
        caption="Try this today!",
        duration_seconds=7.0,
        audio_segments=audio_segments,
        ocr_entries=ocr_entries
    )

    assert transcript.video_id == "test_video_123"
    assert "Drinking cold water" in transcript.full_audio_text
    assert len(transcript.all_ocr_texts) == 2
    assert len(transcript.segments) > 0

    # Ensure at least one segment contains fused audio and OCR
    has_audio = any(s.audio_text for s in transcript.segments)
    has_ocr = any(s.ocr_text for s in transcript.segments)
    assert has_audio and has_ocr
