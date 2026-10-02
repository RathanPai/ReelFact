import re
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
from app.claims.models import MultimodalTranscript
from app.verification.models import ReelDossier
from app.retrieval.vector_store import VectorEvidenceStore
from app.retrieval.search import SearchRetriever
from app.agent.llm_client import LLMClient
from app.config import settings

logger = logging.getLogger(__name__)

FOLLOW_UP_AGENT_SYSTEM_PROMPT = """You are an intelligent, articulate Fact-Checking Assistant dedicated to explaining, clarifying, and investigating claims made in a specific Instagram Reel.
You have native multimodal vision reasoning capabilities to inspect attached video frames whenever the user inquires about specific scenes, visual charts, badges, product labels, or timestamps.

You have access to:
1. The Reel's full Multimodal Transcript and Fact-Check Dossier (claims extracted, verdicts, rationales, and cited sources).
2. Attached visual video keyframes (when relevant to the user's query).
3. Retrieved external evidence passages from authoritative medical, scientific, and journalistic sources.

INSTRUCTIONS:
- Answer the user's questions clearly, objectively, and politely.
- When referencing specific moments or visual elements in the video, cite the timestamp (e.g. `[0:12]` or `[0:45]`).
- When referencing facts or research, cite the specific publication, institution, or URL from the dossier.
- If the user asks about an image or visual element in the video, describe what is visible and whether it matches verified facts.
- Use markdown formatting with bullet points, bold key takeaways, and neat links where appropriate.
"""

def extract_timestamp_from_query(query: str) -> Optional[float]:
    """Detects timestamp references in user queries (e.g. 0:15, 15s, 00:22)."""
    # Pattern 1: mm:ss or m:ss
    match = re.search(r'(\d+):(\d{2})', query)
    if match:
        minutes = int(match.group(1))
        seconds = int(match.group(2))
        return float(minutes * 60 + seconds)
    
    # Pattern 2: 15s or 15 seconds
    match2 = re.search(r'(\d+(?:\.\d+)?)\s*(?:s|sec|seconds)', query, re.IGNORECASE)
    if match2:
        return float(match2.group(1))
        
    return None

class FollowUpAgent:
    def __init__(self, vector_store: VectorEvidenceStore = None, llm_client: LLMClient = None):
        self.vector_store = vector_store or VectorEvidenceStore()
        self.search_retriever = SearchRetriever()
        self.llm = llm_client or LLMClient()

    def format_dossier_context(self, dossier: ReelDossier, transcript: Optional[MultimodalTranscript] = None) -> str:
        """Serializes reel fact-check context for the agent."""
        lines = [
            f"=== REEL FACT-CHECK DOSSIER ===",
            f"Title: {dossier.title or 'Instagram Reel'}",
            f"Author: {dossier.author or 'Unknown'}",
            f"Duration: {dossier.duration_seconds:.1f}s",
            f"Overall Verdict: {dossier.overall_verdict.value} (Trust Score: {dossier.overall_trust_score}/100)",
            f"Executive Summary: {dossier.executive_summary}\n",
            f"=== DETAILED CLAIMS & VERDICTS ==="
        ]

        for idx, c in enumerate(dossier.claims, 1):
            lines.append(
                f"\nClaim {idx} [{c.timestamp_start:.1f}s - {c.timestamp_end:.1f}s]: \"{c.claim_text}\"\n"
                f"Modality: {c.modality or 'audio'}\n"
                f"Verdict: {c.verdict.value} (Confidence: {c.confidence_score}%)\n"
                f"Rationale: {c.summary_rationale}\n"
                f"Detailed Analysis: {c.detailed_analysis}"
            )
            if c.key_nuances:
                lines.append(f"Nuance/Context: {c.key_nuances}")
            if c.keyframe_url:
                lines.append(f"Associated Keyframe: {c.keyframe_url}")
            if c.sources:
                lines.append("Cited Sources:")
                for s in c.sources[:3]:
                    lines.append(f"  - [{s.domain}] {s.title} ({s.url})")

        if transcript and transcript.full_audio_text:
            lines.append(f"\n=== FULL AUDIO TRANSCRIPT ===\n{transcript.full_audio_text}")

        return "\n".join(lines)

    async def answer_question(
        self,
        video_id: str,
        question: str,
        dossier: ReelDossier,
        transcript: Optional[MultimodalTranscript] = None,
        chat_history: Optional[List[Dict[str, str]]] = None
    ) -> str:
        """Answers a user question using conversational RAG with visual frame grounding."""
        # 1. Retrieve relevant evidence chunks from ChromaDB
        relevant_docs = self.vector_store.query_evidence(video_id=video_id, query=question, top_k=3)
        evidence_snippets = []
        for doc in relevant_docs:
            evidence_snippets.append(f"[Retrieved Source Excerpt]: {doc['text']}")

        evidence_block = "\n\n".join(evidence_snippets) if evidence_snippets else "No additional vector chunks retrieved."

        # 2. Check if user question relates to a specific keyframe or timestamp
        images_to_attach: List[Path] = []
        ts_in_query = extract_timestamp_from_query(question)
        
        # Look for frames in claims or frame directory
        if ts_in_query is not None:
            # Find closest claim or frame
            reel_frames_dir = settings.FRAMES_DIR / video_id
            if reel_frames_dir.exists():
                all_frames = list(reel_frames_dir.glob("frame_*.jpg"))
                if all_frames:
                    # Parse timestamp from filename
                    def _get_ts(f: Path):
                        try:
                            return float(f.stem.split("_ts_")[-1])
                        except Exception:
                            return 0.0
                    closest = min(all_frames, key=lambda f: abs(_get_ts(f) - ts_in_query))
                    images_to_attach.append(closest)
        else:
            # Check if user mentioned claim 1, claim 2, etc.
            claim_match = re.search(r'claim\s*#?(\d+)', question, re.IGNORECASE)
            if claim_match:
                idx = int(claim_match.group(1)) - 1
                if 0 <= idx < len(dossier.claims) and dossier.claims[idx].keyframe_url:
                    p = Path(dossier.claims[idx].keyframe_url)
                    if p.exists():
                        images_to_attach.append(p)

        # 3. Format context
        dossier_context = self.format_dossier_context(dossier, transcript)

        # 4. Format history
        history_lines = []
        if chat_history:
            for turn in chat_history[-6:]:  # Keep last 6 messages
                role = "User" if turn.get("role") == "user" else "Assistant"
                history_lines.append(f"{role}: {turn.get('content', '')}")
        history_block = "\n".join(history_lines) if history_lines else "No previous conversation."

        prompt = (
            f"{dossier_context}\n\n"
            f"=== DEEP SEARCH EVIDENCE CHUNKS ===\n"
            f"{evidence_block}\n\n"
            f"=== CONVERSATION HISTORY ===\n"
            f"{history_block}\n\n"
            f"User Question: {question}\n\n"
            f"Provide a direct, accurate, and source-backed answer to the user's question."
        )

        try:
            return await self.llm.generate_text(
                prompt=prompt,
                system_prompt=FOLLOW_UP_AGENT_SYSTEM_PROMPT,
                images=images_to_attach if images_to_attach else None
            )
        except Exception as e:
            logger.error(f"Error generating follow-up answer: {e}")
            return f"I encountered an issue generating a response: {str(e)}"

