import json
import logging
from typing import Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import select
from app.config import settings
from app.database.models import Base, ReelRecord, ClaimRecord, ChatMessageRecord
from app.verification.models import ReelDossier, ClaimVerdict, Verdict, EvidenceSource, CredibilityTier
from app.claims.models import MultimodalTranscript

logger = logging.getLogger(__name__)

engine = create_async_engine(settings.DATABASE_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

async def init_db():
    """Create database tables if they do not exist."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def save_reel_dossier(dossier: ReelDossier, transcript: Optional[MultimodalTranscript] = None, url: Optional[str] = None):
    """Saves or updates a complete reel dossier and claim records in database."""
    async with AsyncSessionLocal() as session:
        async with session.begin():
            # Check if reel exists
            stmt = select(ReelRecord).where(ReelRecord.id == dossier.video_id)
            result = await session.execute(stmt)
            reel = result.scalar_one_or_none()

            transcript_str = transcript.model_dump_json() if transcript else "{}"

            if not reel:
                reel = ReelRecord(
                    id=dossier.video_id,
                    url=url or "",
                    title=dossier.title or "",
                    author=dossier.author or "",
                    duration_seconds=dossier.duration_seconds,
                    video_path=dossier.video_path or "",
                    overall_trust_score=dossier.overall_trust_score,
                    overall_verdict=dossier.overall_verdict.value,
                    executive_summary=dossier.executive_summary,
                    transcript_json=transcript_str
                )
                session.add(reel)
            else:
                reel.title = dossier.title or reel.title
                reel.author = dossier.author or reel.author
                reel.overall_trust_score = dossier.overall_trust_score
                reel.overall_verdict = dossier.overall_verdict.value
                reel.executive_summary = dossier.executive_summary
                reel.transcript_json = transcript_str

            # Save claims
            for c in dossier.claims:
                sources_json = json.dumps([s.model_dump() for s in c.sources])
                claim_rec = ClaimRecord(
                    id=f"{dossier.video_id}_{c.claim_id}",
                    reel_id=dossier.video_id,
                    claim_text=c.claim_text,
                    timestamp_start=c.timestamp_start,
                    timestamp_end=c.timestamp_end,
                    verdict=c.verdict.value,
                    confidence_score=c.confidence_score,
                    summary_rationale=c.summary_rationale,
                    detailed_analysis=c.detailed_analysis,
                    key_nuances=c.key_nuances,
                    sources_json=sources_json
                )
                await session.merge(claim_rec)

async def get_reel_dossier(video_id: str) -> Optional[ReelDossier]:
    """Loads a previously fact-checked reel dossier."""
    async with AsyncSessionLocal() as session:
        stmt = select(ReelRecord).where(ReelRecord.id == video_id)
        res = await session.execute(stmt)
        reel = res.scalar_one_or_none()
        if not reel:
            return None

        # Fetch claims
        claims_stmt = select(ClaimRecord).where(ClaimRecord.reel_id == video_id)
        claims_res = await session.execute(claims_stmt)
        claim_rows = claims_res.scalars().all()

        claim_verdicts: List[ClaimVerdict] = []
        for row in claim_rows:
            raw_sources = json.loads(row.sources_json or "[]")
            sources = [EvidenceSource(**s) for s in raw_sources]
            claim_verdicts.append(ClaimVerdict(
                claim_id=row.id.replace(f"{video_id}_", ""),
                claim_text=row.claim_text,
                timestamp_start=row.timestamp_start,
                timestamp_end=row.timestamp_end,
                verdict=Verdict(row.verdict),
                confidence_score=row.confidence_score,
                summary_rationale=row.summary_rationale,
                detailed_analysis=row.detailed_analysis,
                key_nuances=row.key_nuances,
                sources=sources
            ))

        return ReelDossier(
            video_id=reel.id,
            title=reel.title,
            author=reel.author,
            video_path=reel.video_path,
            duration_seconds=reel.duration_seconds,
            overall_trust_score=reel.overall_trust_score,
            overall_verdict=Verdict(reel.overall_verdict),
            executive_summary=reel.executive_summary,
            claims_count=len(claim_verdicts),
            true_count=sum(1 for c in claim_verdicts if c.verdict == Verdict.TRUE),
            mostly_true_count=sum(1 for c in claim_verdicts if c.verdict == Verdict.MOSTLY_TRUE),
            misleading_count=sum(1 for c in claim_verdicts if c.verdict == Verdict.MISLEADING),
            false_count=sum(1 for c in claim_verdicts if c.verdict == Verdict.FALSE),
            unverifiable_count=sum(1 for c in claim_verdicts if c.verdict == Verdict.UNVERIFIABLE),
            claims=claim_verdicts,
            created_at=reel.created_at.isoformat()
        )

async def get_reel_transcript(video_id: str) -> Optional[MultimodalTranscript]:
    """Retrieves cached multimodal transcript."""
    async with AsyncSessionLocal() as session:
        stmt = select(ReelRecord.transcript_json).where(ReelRecord.id == video_id)
        res = await session.execute(stmt)
        raw_json = res.scalar_one_or_none()
        if raw_json and raw_json != "{}":
            try:
                return MultimodalTranscript.model_validate_json(raw_json)
            except Exception:
                pass
        return None

async def save_chat_message(video_id: str, role: str, content: str):
    """Save user or assistant chat message."""
    async with AsyncSessionLocal() as session:
        async with session.begin():
            msg = ChatMessageRecord(reel_id=video_id, role=role, content=content)
            session.add(msg)

async def get_chat_history(video_id: str) -> List[Dict[str, str]]:
    """Retrieve chat history for a reel."""
    async with AsyncSessionLocal() as session:
        stmt = select(ChatMessageRecord).where(ChatMessageRecord.reel_id == video_id).order_by(ChatMessageRecord.timestamp.asc())
        res = await session.execute(stmt)
        rows = res.scalars().all()
        return [{"role": r.role, "content": r.content} for r in rows]

async def list_recent_reels(limit: int = 20) -> List[Dict[str, Any]]:
    """List recently fact-checked reels."""
    async with AsyncSessionLocal() as session:
        stmt = select(ReelRecord).order_by(ReelRecord.created_at.desc()).limit(limit)
        res = await session.execute(stmt)
        rows = res.scalars().all()
        return [
            {
                "id": r.id,
                "title": r.title or "Untitled Reel",
                "author": r.author or "Unknown",
                "trust_score": r.overall_trust_score,
                "overall_verdict": r.overall_verdict,
                "created_at": r.created_at.isoformat()
            }
            for r in rows
        ]
