from datetime import datetime
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field
from app.claims.models import AtomicClaim

class Verdict(str, Enum):
    TRUE = "TRUE"
    MOSTLY_TRUE = "MOSTLY_TRUE"
    MISLEADING = "MISLEADING"
    FALSE = "FALSE"
    UNVERIFIABLE = "UNVERIFIABLE"

class CredibilityTier(str, Enum):
    TIER_1_AUTHORITATIVE = "TIER_1_AUTHORITATIVE"  # PubMed, CDC, WHO, Nature, Reuters, AP, IFCN Fact-checkers
    TIER_2_REPUTABLE = "TIER_2_REPUTABLE"          # Established mainstream news, university press
    TIER_3_GENERAL = "TIER_3_GENERAL"              # Standard blogs, commercial sites
    TIER_4_UNRELIABLE = "TIER_4_UNRELIABLE"        # Tabloids, spam, content farms

class EvidenceSource(BaseModel):
    url: str
    title: str
    domain: str
    snippet: str
    credibility_tier: CredibilityTier = CredibilityTier.TIER_3_GENERAL
    credibility_score: float = Field(default=0.5, description="Score between 0.0 and 1.0")
    relevant_quote: Optional[str] = None
    is_fact_check_article: bool = False

class ClaimVerdict(BaseModel):
    claim_id: str
    claim_text: str
    timestamp_start: float = 0.0
    timestamp_end: float = 0.0
    verdict: Verdict
    confidence_score: int = Field(default=80, ge=0, le=100, description="Confidence in verdict (0-100)")
    summary_rationale: str = Field(..., description="Quick 1-2 sentence breakdown for the user")
    detailed_analysis: str = Field(..., description="Comprehensive explanation with evidence synthesis")
    key_nuances: Optional[str] = None
    sources: List[EvidenceSource] = Field(default_factory=list)

class ReelDossier(BaseModel):
    video_id: str
    title: Optional[str] = ""
    author: Optional[str] = ""
    thumbnail_url: Optional[str] = None
    video_path: Optional[str] = None
    duration_seconds: float = 0.0
    overall_trust_score: int = Field(default=100, ge=0, le=100, description="Overall trust rating from 0 to 100")
    overall_verdict: Verdict = Verdict.TRUE
    executive_summary: str = Field(..., description="High-level assessment of the reel's accuracy")
    claims_count: int = 0
    true_count: int = 0
    mostly_true_count: int = 0
    misleading_count: int = 0
    false_count: int = 0
    unverifiable_count: int = 0
    claims: List[ClaimVerdict] = []
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
