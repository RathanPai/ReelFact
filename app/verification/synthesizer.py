from typing import List
from app.verification.models import ClaimVerdict, ReelDossier, Verdict
from app.agent.llm_client import LLMClient

SYNTHESIS_SYSTEM_PROMPT = """You are a senior editorial fact-checker.
Given the individual verdicts for all claims extracted from an Instagram Reel, synthesize a high-level, objective Executive Summary (2-3 sentences) evaluating the overall reliability, accuracy, and any misinformation risks of the video for the viewer.
"""

class ReelSynthesizer:
    def __init__(self, llm_client: LLMClient = None):
        self.llm = llm_client or LLMClient()

    async def synthesize_dossier(
        self,
        video_id: str,
        title: str,
        author: str,
        video_path: str,
        duration_seconds: float,
        claim_verdicts: List[ClaimVerdict]
    ) -> ReelDossier:
        """Synthesize individual claim verdicts into a final Reel Dossier."""
        total = len(claim_verdicts)
        true_cnt = sum(1 for c in claim_verdicts if c.verdict == Verdict.TRUE)
        mostly_true_cnt = sum(1 for c in claim_verdicts if c.verdict == Verdict.MOSTLY_TRUE)
        misleading_cnt = sum(1 for c in claim_verdicts if c.verdict == Verdict.MISLEADING)
        false_cnt = sum(1 for c in claim_verdicts if c.verdict == Verdict.FALSE)
        unverifiable_cnt = sum(1 for c in claim_verdicts if c.verdict == Verdict.UNVERIFIABLE)

        # Calculate weighted trust score (0 - 100)
        if total == 0:
            trust_score = 100
            overall_verdict = Verdict.TRUE
        else:
            # Score formula: TRUE=100%, MOSTLY_TRUE=75%, UNVERIFIABLE=50%, MISLEADING=25%, FALSE=0%
            points = (true_cnt * 100) + (mostly_true_cnt * 75) + (unverifiable_cnt * 50) + (misleading_cnt * 25) + (false_cnt * 0)
            trust_score = int(points / total)
            
            if false_cnt > 0 and (false_cnt / total) >= 0.4:
                overall_verdict = Verdict.FALSE
            elif false_cnt > 0 or misleading_cnt > 0:
                overall_verdict = Verdict.MISLEADING
            elif mostly_true_cnt > 0:
                overall_verdict = Verdict.MOSTLY_TRUE
            elif unverifiable_cnt == total:
                overall_verdict = Verdict.UNVERIFIABLE
            else:
                overall_verdict = Verdict.TRUE

        # Generate executive summary
        summary_prompt = (
            f"Reel Title: {title or 'Instagram Reel'}\n"
            f"Author: {author or 'Unknown'}\n"
            f"Total Claims Analyzed: {total}\n"
            f"True: {true_cnt}, Mostly True: {mostly_true_cnt}, Misleading: {misleading_cnt}, False: {false_cnt}, Unverified: {unverifiable_cnt}\n\n"
            f"Claim Breakdown:\n"
        )
        for c in claim_verdicts:
            summary_prompt += f"- [{c.verdict.value}] \"{c.claim_text}\": {c.summary_rationale}\n"

        summary_prompt += "\nWrite a concise executive summary for the viewer."

        try:
            executive_summary = await self.llm.generate_text(summary_prompt, SYNTHESIS_SYSTEM_PROMPT)
            executive_summary = executive_summary.strip()
        except Exception:
            executive_summary = f"This reel contains {total} analyzed claims with an overall trust score of {trust_score}/100."

        return ReelDossier(
            video_id=video_id,
            title=title,
            author=author,
            video_path=video_path,
            duration_seconds=duration_seconds,
            overall_trust_score=trust_score,
            overall_verdict=overall_verdict,
            executive_summary=executive_summary,
            claims_count=total,
            true_count=true_cnt,
            mostly_true_count=mostly_true_cnt,
            misleading_count=misleading_cnt,
            false_count=false_cnt,
            unverifiable_count=unverifiable_cnt,
            claims=claim_verdicts
        )
