import logging
from typing import List, Dict, Any, Optional
from app.claims.models import MultimodalTranscript
from app.verification.models import ReelDossier
from app.retrieval.vector_store import VectorEvidenceStore
from app.retrieval.search import SearchRetriever
from app.agent.llm_client import LLMClient

logger = logging.getLogger(__name__)

FOLLOW_UP_AGENT_SYSTEM_PROMPT = """You are an intelligent, articulate Fact-Checking Assistant dedicated to explaining, clarifying, and investigating claims made in a specific Instagram Reel.

You have access to:
1. The Reel's full Multimodal Transcript (timestamped speech + on-screen text overlays).
2. The complete Fact-Check Dossier (claims extracted, verdicts, rationales, and cited sources).
3. Retrieved external evidence passages from authoritative medical, scientific, and journalistic sources.

INSTRUCTIONS:
- Answer the user's questions clearly, objectively, and politely.
- When referencing specific moments in the video, cite the timestamp (e.g. `[0:12]` or `[0:45]`).
- When referencing facts or research, cite the specific publication, institution, or URL from the dossier.
- If the user asks something not directly addressed in the reel or existing sources, explain the broader context truthfully or acknowledge limitations.
- Use markdown formatting with bullet points, bold key takeaways, and neat links where appropriate.
"""

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
                f"Verdict: {c.verdict.value} (Confidence: {c.confidence_score}%)\n"
                f"Rationale: {c.summary_rationale}\n"
                f"Detailed Analysis: {c.detailed_analysis}"
            )
            if c.key_nuances:
                lines.append(f"Nuance/Context: {c.key_nuances}")
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
        """Answers a user question using conversational RAG."""
        # 1. Retrieve relevant evidence chunks from ChromaDB
        relevant_docs = self.vector_store.query_evidence(video_id=video_id, query=question, top_k=3)
        evidence_snippets = []
        for doc in relevant_docs:
            evidence_snippets.append(f"[Retrieved Source Excerpt]: {doc['text']}")

        evidence_block = "\n\n".join(evidence_snippets) if evidence_snippets else "No additional vector chunks retrieved."

        # 2. Format context
        dossier_context = self.format_dossier_context(dossier, transcript)

        # 3. Format history
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
            return await self.llm.generate_text(prompt, FOLLOW_UP_AGENT_SYSTEM_PROMPT)
        except Exception as e:
            logger.error(f"Error generating follow-up answer: {e}")
            return f"I encountered an issue generating a response: {str(e)}"
