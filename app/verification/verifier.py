import logging
from pathlib import Path
from typing import List, Optional
from app.claims.models import AtomicClaim, ModalitySource
from app.verification.models import ClaimVerdict, Verdict, EvidenceSource
from app.agent.llm_client import LLMClient

logger = logging.getLogger(__name__)

VERIFICATION_SYSTEM_PROMPT = """You are a rigorous, neutral, evidence-based fact-checking judge with multimodal visual reasoning capabilities.
You evaluate a specific factual claim made in an Instagram Reel against a curated set of retrieved web sources, authoritative documents, and attached keyframe images from the video.

RULES FOR EVALUATION:
1. Grounding in Evidence:
   - Base your decision strictly on the provided sources and visual frame evidence.
   - If keyframes are attached showing charts, product ingredients, text overlays, or visual demonstrations, cross-examine the visual content against what the authoritative sources state.
   - If the numbers, rules, rates, or entities in the claim match what is stated in the sources, you MUST rate it "TRUE".
   - Do NOT nitpick or invent artificial contradictions when the core facts, rates, and entities directly match the sources.
   - Recognize sectoral concessions & exemptions: A general policy (e.g. 0.4% MDR) frequently coexists with specific sectoral flat rates (e.g. flat ₹5 for fuel/petrol pumps, railways, utilities). If sources confirm the specific category rate, mark the claim TRUE.

2. Verdict Definitions:
   - "TRUE": The claim's key facts, numbers, and statements are directly confirmed by the sources.
   - "MOSTLY_TRUE": The core statement is accurate with minor nuances or slight imprecision.
   - "MISLEADING": The claim twists facts, takes things out of context, distorts visual charts, or makes unsupported extrapolations.
   - "FALSE": The claim's stated facts, dates, or numbers are directly contradicted or refuted by the sources.
   - "UNVERIFIABLE": There is insufficient evidence, no consensus, or contradictory reputable findings in the retrieved sources.

3. Confidence Score:
   - Provide an integer from 0 to 100 representing your certainty based on the evidence quality.

4. Rationale Fields:
   - summary_rationale: 1-2 punchy sentences clearly stating why the claim is true/false/misleading.
   - detailed_analysis: Single comprehensive paragraph breaking down the factual reality and quoting/referencing specific source facts.
   - key_nuances: Any important caveats or missing context for viewers.

Output MUST strictly be a JSON object with this structure:
{
  "verdict": "TRUE",
  "confidence_score": 95,
  "summary_rationale": "1-2 sentence summary here.",
  "detailed_analysis": "Comprehensive paragraph here as a single string.",
  "key_nuances": "Important caveats here as a single string."
}
"""

class ClaimVerifier:
    def __init__(self, llm_client: LLMClient = None):
        self.llm = llm_client or LLMClient()

    async def verify_claim(self, claim: AtomicClaim, sources: List[EvidenceSource]) -> ClaimVerdict:
        """Verifies an individual claim against its retrieved sources, including visual frame grounding."""
        evidence_text = []
        for idx, s in enumerate(sources, 1):
            tier_label = s.credibility_tier.value
            snippet = s.relevant_quote or s.snippet or "No snippet available."
            evidence_text.append(
                f"[Source {idx} - {s.domain} ({tier_label})]\n"
                f"Title: {s.title}\n"
                f"URL: {s.url}\n"
                f"Excerpt: {snippet}\n"
            )

        sources_block = "\n".join(evidence_text) if evidence_text else "No web evidence could be retrieved."

        # Check for keyframe image to pass for visual verification
        images_to_pass = []
        keyframe_note = ""
        if claim.keyframe_path:
            p = Path(claim.keyframe_path)
            if p.exists():
                images_to_pass.append(p)
                keyframe_note = f"\nAttached Video Keyframe: Frame captured at {claim.keyframe_timestamp or claim.timestamp_start:.1f}s."

        prompt = (
            f"=== CLAIM TO FACT-CHECK ===\n"
            f"Claim: \"{claim.claim_text}\"\n"
            f"Category: {claim.category.value}\n"
            f"Modality: {claim.modality.value}\n"
            f"Reel Context: {claim.context_in_reel}{keyframe_note}\n\n"
            f"=== RETRIEVED SOURCES & EVIDENCE ===\n"
            f"{sources_block}\n\n"
            f"Evaluate this claim strictly based on evidence, visual inspection (if frame is provided), and consensus in JSON format."
        )

        try:
            res_json = await self.llm.generate_json(
                prompt=prompt,
                system_prompt=VERIFICATION_SYSTEM_PROMPT,
                images=images_to_pass if images_to_pass else None
            )
            raw_verdict = str(res_json.get("verdict", "UNVERIFIABLE")).strip().upper()
            
            # Map to Enum
            try:
                verdict = Verdict(raw_verdict)
            except ValueError:
                normalized = raw_verdict.replace(" ", "_").replace("-", "_")
                try:
                    verdict = Verdict(normalized)
                except ValueError:
                    verdict = Verdict.UNVERIFIABLE

            # Safe string conversions
            summary = res_json.get("summary_rationale", "Evidence was inconclusive.")
            if isinstance(summary, list):
                summary = " ".join(str(i) for i in summary)
            elif not isinstance(summary, str):
                summary = str(summary)

            detailed = res_json.get("detailed_analysis", "No detailed analysis provided.")
            if isinstance(detailed, list):
                detailed = "\n\n".join(str(i) for i in detailed)
            elif not isinstance(detailed, str):
                detailed = str(detailed)

            nuances = res_json.get("key_nuances")
            if isinstance(nuances, list):
                nuances = "\n".join(f"- {i}" for i in nuances)
            elif nuances is not None and not isinstance(nuances, str):
                nuances = str(nuances)

            try:
                confidence = int(res_json.get("confidence_score", 70))
            except (ValueError, TypeError):
                confidence = 70

            return ClaimVerdict(
                claim_id=claim.id,
                claim_text=claim.claim_text,
                timestamp_start=claim.timestamp_start,
                timestamp_end=claim.timestamp_end,
                verdict=verdict,
                confidence_score=confidence,
                summary_rationale=summary,
                detailed_analysis=detailed,
                key_nuances=nuances,
                keyframe_url=claim.keyframe_path,
                modality=claim.modality.value,
                sources=sources
            )
        except Exception as e:
            logger.error(f"Error verifying claim '{claim.claim_text}': {e}")
            return ClaimVerdict(
                claim_id=claim.id,
                claim_text=claim.claim_text,
                timestamp_start=claim.timestamp_start,
                timestamp_end=claim.timestamp_end,
                verdict=Verdict.UNVERIFIABLE,
                confidence_score=50,
                summary_rationale="Failed to verify claim due to an LLM processing error.",
                detailed_analysis="An automated processing error occurred while reasoning over the evidence.",
                keyframe_url=claim.keyframe_path,
                modality=claim.modality.value,
                sources=sources
            )

