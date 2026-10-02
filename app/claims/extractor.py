import logging
from pathlib import Path
from typing import List, Tuple, Dict, Any, Optional
from app.config import settings
from app.claims.models import (
    MultimodalTranscript,
    AtomicClaim,
    ExtractedClaimsResponse,
    ClaimCategory,
    ModalitySource
)
from app.agent.llm_client import LLMClient

logger = logging.getLogger(__name__)

MULTIMODAL_CLAIM_SYSTEM_PROMPT = """You are an advanced multimodal fact-checking investigator.
You are given a sequence of timestamped video keyframes and the spoken audio transcript from an Instagram Reel.

Your mission is to inspect the visual scenes (charts, graphs, product packaging, on-screen text overlays, fine-print disclaimers, scientific/medical demonstrations) AND the spoken dialogue to extract the TOP 3 TO 5 CORE, HIGHEST-IMPACT verifiable atomic factual claims.

RULES:
1. FOCUS ON TOP 3 TO 5 HIGH-IMPACT FACTUAL ASSERTIONS:
   - Extract the primary factual claims that a viewer would care to fact-check (health advice, election numbers, policy rules, statistics, quotes).
   - Group closely connected sub-statements into a single coherent claim rather than producing 10+ fragmented micro-claims.
   - Do NOT extract trivial background details or obvious common-sense commentary.

2. IGNORE:
   - Subjective opinions, personal banter, greetings, humor, rhetorical questions, generic hype.

3. FOR EACH FACTUAL CLAIM:
   - Make it a concise, standalone factual assertion.
   - Specify timestamps (timestamp_start, timestamp_end).
   - Assign the closest keyframe timestamp that visually exhibits the claim.
   - Set modality: "audio", "visual_ocr", "visual_demonstration", "chart_graphic", "audio_visual_mismatch", or "combined".
   - Set category: health_medical, science_tech, finance_economy, politics_policy, history_geography, lifestyle_nutrition, or general.
   - Assign importance_score (0.0 to 1.0, where 1.0 is the most critical core thesis of the reel).
   - Generate 1-2 SHORT, PRECISE search queries (e.g. 3-6 keywords with key names, numbers, or terms - avoid full conversational sentences).

Output format must strictly be JSON:
{
  "claims": [
    {
      "id": "claim_1",
      "claim_text": "Detailed factual assertion statement.",
      "context_in_reel": "Visual and/or dialogue context in video.",
      "timestamp_start": 2.5,
      "timestamp_end": 6.0,
      "keyframe_timestamp": 3.0,
      "modality": "chart_graphic",
      "category": "finance_economy",
      "importance_score": 0.95,
      "search_queries": [
        "exact search query with entities and numbers",
        "official circular regulatory query"
      ]
    }
  ],
  "non_factual_notes": "Notes on banter/entertainment ignored."
}
"""

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
   - Generate 2-3 precise search queries. MUST include key entities, numbers, percentages, flat fees, or sectoral terms.

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

def parse_modality(raw_modality: str) -> ModalitySource:
    try:
        return ModalitySource(raw_modality.lower())
    except Exception:
        norm = raw_modality.lower().replace(" ", "_").replace("-", "_")
        for m in ModalitySource:
            if m.value == norm:
                return m
        return ModalitySource.AUDIO

def parse_category(raw_category: str) -> ClaimCategory:
    try:
        return ClaimCategory(raw_category.lower())
    except Exception:
        norm = raw_category.lower().replace(" ", "_").replace("-", "_")
        for c in ClaimCategory:
            if c.value == norm:
                return c
        return ClaimCategory.GENERAL


class ClaimExtractor:
    def __init__(self, llm_client: LLMClient = None):
        self.llm = llm_client or LLMClient()

    def _sample_keyframes(
        self,
        frames: List[Tuple[float, Path]],
        max_frames: int = 12
    ) -> List[Tuple[float, Path]]:
        """Selects up to max_frames evenly distributed from the extracted keyframes."""
        if not frames or len(frames) <= max_frames:
            return frames
        step = len(frames) / max_frames
        selected = [frames[int(i * step)] for i in range(max_frames)]
        return selected

    async def extract_claims_multimodal(
        self,
        video_id: str,
        frames: List[Tuple[float, Path]],
        audio_transcript: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> List[AtomicClaim]:
        """
        Natively extracts atomic claims by passing video keyframes and spoken dialogue directly to Gemma 4 via LM Studio.
        """
        metadata = metadata or {}
        duration = float(metadata.get("duration") or 0.0)
        sampled_frames = self._sample_keyframes(frames, max_frames=settings.MULTIMODAL_MAX_FRAMES)
        
        # Build frame index and paths
        image_paths = [f[1] for f in sampled_frames]
        frame_timestamps = [f[0] for f in sampled_frames]

        frame_descriptions = []
        for idx, (ts, path) in enumerate(sampled_frames, 1):
            frame_descriptions.append(f"Image {idx}: Video Keyframe at {ts:.1f}s (file: {path.name})")

        frames_block = "\n".join(frame_descriptions) if frame_descriptions else "No visual frames available."

        prompt_parts = [
            f"=== REEL METADATA ===",
            f"Title: {metadata.get('title', 'N/A')}",
            f"Author: {metadata.get('author', 'N/A')}",
            f"Caption: {metadata.get('caption', 'N/A')}",
            f"Duration: {duration:.1f} seconds\n",
            f"=== ATTACHED VIDEO FRAMES ===",
            f"{frames_block}\n",
            f"=== AUDIO SPEECH TRANSCRIPT ===",
            f"{audio_transcript or 'No spoken audio detected.'}\n",
            "Carefully analyze both the visual images (charts, text overlays, demonstrations) and the speech audio transcript.",
            "Extract all verifiable atomic claims in the required JSON format."
        ]

        prompt = "\n".join(prompt_parts)

        try:
            logger.info(f"Extracting multimodal claims using {self.llm.provider} with {len(image_paths)} visual keyframes...")
            response_json = await self.llm.generate_json(
                prompt=prompt,
                system_prompt=MULTIMODAL_CLAIM_SYSTEM_PROMPT,
                images=image_paths
            )
            raw_claims = response_json.get("claims", [])
            
            parsed_claims: List[AtomicClaim] = []
            for idx, c in enumerate(raw_claims):
                claim_id = c.get("id") or f"claim_{idx+1}"
                ts_start = float(c.get("timestamp_start", 0.0))
                ts_end = float(c.get("timestamp_end", 0.0))
                
                # Match closest keyframe
                kf_ts = c.get("keyframe_timestamp")
                matched_kf_ts = float(kf_ts) if kf_ts is not None else ts_start
                
                # Find the nearest actual frame path
                best_frame_path = None
                if sampled_frames:
                    closest_frame = min(sampled_frames, key=lambda f: abs(f[0] - matched_kf_ts))
                    best_frame_path = str(closest_frame[1])
                    matched_kf_ts = closest_frame[0]

                parsed_claims.append(AtomicClaim(
                    id=claim_id,
                    claim_text=c.get("claim_text", ""),
                    context_in_reel=c.get("context_in_reel", ""),
                    timestamp_start=ts_start,
                    timestamp_end=ts_end,
                    modality=parse_modality(str(c.get("modality", "audio"))),
                    category=parse_category(str(c.get("category", "general"))),
                    importance_score=float(c.get("importance_score", 1.0)),
                    search_queries=c.get("search_queries", []),
                    keyframe_timestamp=matched_kf_ts,
                    keyframe_path=best_frame_path
                ))

            if parsed_claims:
                logger.info(f"Extracted {len(parsed_claims)} multimodal claims.")
                return parsed_claims

        except Exception as e:
            logger.error(f"Multimodal claim extraction error: {e}")

        # Fallback to text-based extraction if multimodal call failed
        logger.warning("Falling back to text-based transcript extraction...")
        dummy_transcript = MultimodalTranscript(
            video_id=video_id,
            title=metadata.get("title", ""),
            author=metadata.get("author", ""),
            caption=metadata.get("caption", ""),
            duration_seconds=duration,
            full_audio_text=audio_transcript
        )
        return await self.extract_claims(dummy_transcript)

    async def extract_claims(self, transcript: MultimodalTranscript) -> List[AtomicClaim]:
        """Legacy / Text-based extraction from a fused multimodal transcript."""
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
                    modality=parse_modality(str(c.get("modality", "audio"))),
                    category=parse_category(str(c.get("category", "general"))),
                    importance_score=float(c.get("importance_score", 1.0)),
                    search_queries=c.get("search_queries", [])
                ))

            return parsed_claims
        except Exception as e:
            logger.error(f"Error extracting claims with LLM: {e}")
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

