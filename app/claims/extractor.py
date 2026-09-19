import logging
from typing import List
from app.claims.models import MultimodalTranscript, AtomicClaim, ExtractedClaimsResponse, ClaimCategory, ModalitySource
from app.agent.llm_client import LLMClient

logger = logging.getLogger(__name__)

CLAIM_EXTRACTION_SYSTEM_PROMPT = """You are an expert fact-checker and claim decomposition engine.
Your task is to analyze the multimodal transcript of an Instagram Reel (including transcribed speech, on-screen text overlays, and caption) and extract ALL atomic, verifiable factual claims.

RULES:
1. ONLY extract checkable factual assertions:
   - Specific regulatory, legal, or financial rules (e.g. fees, caps, percentages, dates, exemptions)
   - Scientific, medical, and health claims
   - Statistics, percentages, and data points
   - Quotes or attributions to official bodies (NPCI, RBI, Ministries, WHO, etc.)
2. IGNORE:
   - Subjective opinions ("This is great", "I think this is unfair")
   - Personal anecdotes, casual banter, greetings, humor, rhetorical questions
   - Generic hype / clickbait without a concrete fact
3. For each factual claim:
   - Make the claim concise, standalone, and clear.
   - Assign the closest timestamp in the video where it is stated or shown.
   - Indicate modality: "audio", "visual_ocr", "caption", or "combined".
   - Assign the category: health_medical, science_tech, finance_economy, politics_policy, history_geography, lifestyle_nutrition, or general.
   - Generate 2-3 precise search queries. MUST include key entities, numbers, percentages, flat fees, or sectoral terms (e.g., fuel, petrol, railway, insurance, 0.4%, ₹5).

Output format must strictly be JSON:
{
  "claims": [
    {
      "id": "claim_1",
      "claim_text": "Detailed factual assertion statement here.",
      "context_in_reel": "Context in video.",
      "timestamp_start": 2.5,
      "timestamp_end": 6.0,
      "modality": "audio",
      "category": "finance_economy",
      "importance_score": 0.95,
      "search_queries": [
        "precise search query with numbers and entities",
        "official announcement circular search query"
      ]
    }
  ],
  "non_factual_notes": "Notes on non-checkable content."
}
"""

class ClaimExtractor:
    def __init__(self, llm_client: LLMClient = None):
        self.llm = llm_client or LLMClient()

    async def extract_claims(self, transcript: MultimodalTranscript) -> List[AtomicClaim]:
        """Extract atomic claims from a multimodal transcript."""
        # Format the transcript into structured text
        prompt_parts = [
            f"=== REEL METADATA ===",
            f"Title: {transcript.title or 'N/A'}",
            f"Author: {transcript.author or 'N/A'}",
            f"Caption: {transcript.caption or 'N/A'}",
            f"Duration: {transcript.duration_seconds:.1f} seconds\n",
            f"=== MULTIMODAL TIMELINE ==="
        ]

        last_ocr_text = ""
        for seg in transcript.segments:
            seg_text = []
            if seg.audio_text:
                seg_text.append(f"[Audio: {seg.audio_text.strip()}]")
            
            # Deduplicate OCR text to save tokens
            if seg.ocr_text:
                current_ocr = seg.ocr_text.strip()
                if current_ocr and current_ocr != last_ocr_text:
                    seg_text.append(f"[On-Screen Text: {current_ocr}]")
                    last_ocr_text = current_ocr
            
            if seg.visual_notes:
                seg_text.append(f"[Visual Context: {seg.visual_notes.strip()}]")
            
            if seg_text:
                prompt_parts.append(f"[{seg.start:.1f}s - {seg.end:.1f}s]: {' '.join(seg_text)}")

        if not transcript.segments and transcript.full_audio_text:
            prompt_parts.append(f"Full Audio Transcript:\n{transcript.full_audio_text}")

        prompt = "\n".join(prompt_parts) + "\n\nExtract all verifiable factual claims from this reel in the required JSON format."
        
        # Hard limit to prevent exceeding context window (approx 12000 tokens)
        MAX_PROMPT_CHARS = 45000
        if len(prompt) > MAX_PROMPT_CHARS:
            prompt = prompt[:MAX_PROMPT_CHARS] + "\n\n[TEXT TRUNCATED] Extract all verifiable factual claims from this reel in the required JSON format."


        try:
            response_json = await self.llm.generate_json(prompt, CLAIM_EXTRACTION_SYSTEM_PROMPT)
            raw_claims = response_json.get("claims", [])
            
            parsed_claims: List[AtomicClaim] = []
            for idx, c in enumerate(raw_claims):
                claim_id = c.get("id") or f"claim_{idx+1}"
                parsed_claims.append(AtomicClaim(
                    id=claim_id,
                    claim_text=c.get("claim_text", ""),
                    context_in_reel=c.get("context_in_reel", ""),
                    timestamp_start=float(c.get("timestamp_start", 0.0)),
                    timestamp_end=float(c.get("timestamp_end", 0.0)),
                    modality=ModalitySource(c.get("modality", "audio")),
                    category=ClaimCategory(c.get("category", "general")),
                    importance_score=float(c.get("importance_score", 1.0)),
                    search_queries=c.get("search_queries", [])
                ))

            return parsed_claims
        except Exception as e:
            logger.error(f"Error extracting claims with LLM: {e}")
            # Fallback heuristic if LLM output fails
            if transcript.full_audio_text:
                return [
                    AtomicClaim(
                        id="claim_1",
                        claim_text=transcript.full_audio_text[:200],
                        context_in_reel="Full transcript fallback",
                        timestamp_start=0.0,
                        timestamp_end=transcript.duration_seconds,
                        modality=ModalitySource.AUDIO,
                        category=ClaimCategory.GENERAL,
                        search_queries=[f"fact check {transcript.full_audio_text[:100]}"]
                    )
                ]
            return []
