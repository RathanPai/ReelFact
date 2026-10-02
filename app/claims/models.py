from enum import Enum
from typing import List, Optional, Tuple
from pydantic import BaseModel, Field

class ClaimCategory(str, Enum):
    HEALTH_MEDICAL = "health_medical"
    SCIENCE_TECH = "science_tech"
    FINANCE_ECONOMY = "finance_economy"
    POLITICS_POLICY = "politics_policy"
    HISTORY_GEOGRAPHY = "history_geography"
    LIFESTYLE_NUTRITION = "lifestyle_nutrition"
    GENERAL = "general"

class ModalitySource(str, Enum):
    AUDIO = "audio"
    VISUAL_OCR = "visual_ocr"
    CAPTION = "caption"
    COMBINED = "combined"
    VISUAL_DEMONSTRATION = "visual_demonstration"
    CHART_GRAPHIC = "chart_graphic"
    AUDIO_VISUAL_MISMATCH = "audio_visual_mismatch"

class MultimodalSegment(BaseModel):
    start: float = Field(..., description="Start time in seconds")
    end: float = Field(..., description="End time in seconds")
    audio_text: Optional[str] = Field(default="", description="Transcribed speech in this segment")
    ocr_text: Optional[str] = Field(default="", description="Detected on-screen text overlays")
    visual_notes: Optional[str] = Field(default="", description="Visual context / scene description")

class MultimodalTranscript(BaseModel):
    video_id: str
    title: Optional[str] = ""
    caption: Optional[str] = ""
    author: Optional[str] = ""
    duration_seconds: float = 0.0
    segments: List[MultimodalSegment] = []
    full_audio_text: str = ""
    all_ocr_texts: List[str] = []

class AtomicClaim(BaseModel):
    id: str = Field(..., description="Unique claim identifier, e.g. claim_1")
    claim_text: str = Field(..., description="Concise, self-contained atomic factual assertion")
    context_in_reel: Optional[str] = Field(default="", description="Context or surrounding dialogue in the reel")
    timestamp_start: float = Field(default=0.0, description="Start time in seconds in the video")
    timestamp_end: float = Field(default=0.0, description="End time in seconds in the video")
    modality: ModalitySource = Field(default=ModalitySource.AUDIO)
    category: ClaimCategory = Field(default=ClaimCategory.GENERAL)
    importance_score: float = Field(default=1.0, description="Priority / checkability score (0.0 - 1.0)")
    search_queries: List[str] = Field(default_factory=list, description="Targeted, neutral web search queries")
    keyframe_timestamp: Optional[float] = Field(default=None, description="Timestamp of most relevant keyframe")
    keyframe_path: Optional[str] = Field(default=None, description="Relative or absolute path to keyframe image")

class ExtractedClaimsResponse(BaseModel):
    video_id: str
    claims: List[AtomicClaim] = []
    non_factual_notes: Optional[str] = Field(default="", description="Notes on opinions or entertainment elements ignored")
