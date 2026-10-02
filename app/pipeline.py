import asyncio
import logging
from pathlib import Path
from typing import Optional, Callable, Dict, Any, List
from app.config import settings
from app.ingestion.downloader import ReelDownloader
from app.ingestion.preprocessor import VideoPreprocessor
from app.audio.transcriber import AudioTranscriber
from app.vision.ocr_extractor import OCRExtractor
from app.vision.fusion import MultimodalFusion
from app.claims.extractor import ClaimExtractor
from app.claims.models import MultimodalTranscript, AtomicClaim
from app.retrieval.search import SearchRetriever
from app.retrieval.vector_store import VectorEvidenceStore
from app.verification.verifier import ClaimVerifier
from app.verification.synthesizer import ReelSynthesizer
from app.verification.models import ReelDossier, ClaimVerdict
from app.database.storage import save_reel_dossier

logger = logging.getLogger(__name__)

class FactCheckPipeline:
    def __init__(self):
        self.downloader = ReelDownloader()
        self.preprocessor = VideoPreprocessor()
        self.transcriber = AudioTranscriber()
        self.ocr_extractor = OCRExtractor()
        self.claim_extractor = ClaimExtractor()
        self.search_retriever = SearchRetriever()
        self.vector_store = VectorEvidenceStore()
        self.verifier = ClaimVerifier()
        self.synthesizer = ReelSynthesizer()

    async def run_pipeline(
        self,
        url: Optional[str] = None,
        file_bytes: Optional[bytes] = None,
        filename: Optional[str] = None,
        status_callback: Optional[Callable[[str, int, Dict[str, Any]], Any]] = None
    ) -> ReelDossier:
        """
        Executes the end-to-end multimodal fact-checking pipeline with progress updates.
        """
        async def report(step_name: str, progress: int, data: Dict[str, Any] = None):
            if status_callback:
                try:
                    res = status_callback(step_name, progress, data or {})
                    if asyncio.iscoroutine(res):
                        await res
                except Exception as e:
                    logger.debug(f"Status callback error: {e}")

        # Stage 1: Ingestion
        await report("Ingesting Reel Video", 10, {"status": "downloading"})
        if url:
            video_id, video_path, metadata = await self.downloader.download_reel(url)
        elif file_bytes and filename:
            video_id, video_path, metadata = await self.downloader.save_uploaded_file(file_bytes, filename)
        else:
            raise ValueError("Either URL or uploaded video file must be provided.")

        duration = float(metadata.get("duration") or 0.0)

        # Stage 2: Audio & Keyframe Extraction
        await report("Extracting Audio & Keyframes", 25, {"status": "preprocessing"})
        audio_task = self.preprocessor.extract_audio(video_path, video_id)
        frames_task = self.preprocessor.extract_keyframes(video_path, video_id, interval_sec=settings.FRAME_SAMPLE_INTERVAL)
        audio_path, frames = await asyncio.gather(audio_task, frames_task)

        claims: List[AtomicClaim] = []
        transcript: MultimodalTranscript

        if settings.PIPELINE_MODE == "native_multimodal":
            # --- NATIVE MULTIMODAL MODE (Gemma 4 / LM Studio) ---
            await report("Transcribing Speech Audio", 38, {"status": "perception_audio"})
            audio_segments = await self.transcriber.transcribe(audio_path)
            full_speech_text = " ".join([seg["text"] for seg in audio_segments])

            transcript = MultimodalTranscript(
                video_id=video_id,
                title=metadata.get("title", ""),
                author=metadata.get("author", ""),
                caption=metadata.get("caption", ""),
                duration_seconds=duration,
                full_audio_text=full_speech_text
            )

            # Stage 4: Native Multimodal Claim Extraction
            await report(f"Extracting Multimodal Claims with {settings.LLM_PROVIDER.upper()} ({len(frames)} frames)", 55, {"status": "multimodal_extraction"})
            claims = await self.claim_extractor.extract_claims_multimodal(
                video_id=video_id,
                frames=frames,
                audio_transcript=full_speech_text,
                metadata=metadata
            )
        else:
            # --- LEGACY CASCADED MODE (Whisper + EasyOCR + Fusion) ---
            await report("Transcribing Speech & Analyzing On-Screen Text (OCR)", 40, {"status": "perception"})
            transcribe_task = self.transcriber.transcribe(audio_path)
            ocr_task = self.ocr_extractor.extract_text_from_frames(frames)
            audio_segments, ocr_entries = await asyncio.gather(transcribe_task, ocr_task)

            await report("Fusing Multimodal Timeline", 55, {"status": "fusion"})
            transcript = MultimodalFusion.fuse_timeline(
                video_id=video_id,
                title=metadata.get("title", ""),
                author=metadata.get("author", ""),
                caption=metadata.get("caption", ""),
                duration_seconds=duration,
                audio_segments=audio_segments,
                ocr_entries=ocr_entries
            )

            await report("Isolating Verifiable Factual Claims", 65, {"status": "extracting_claims"})
            claims = await self.claim_extractor.extract_claims(transcript)

        if not claims:
            # If no checkable factual claims found
            await report("No verifiable claims found in reel", 100, {"status": "complete"})
            dossier = await self.synthesizer.synthesize_dossier(
                video_id=video_id,
                title=transcript.title or "Instagram Reel",
                author=transcript.author or "Unknown",
                video_path=str(video_path.relative_to(settings.BASE_DIR)),
                duration_seconds=duration,
                claim_verdicts=[]
            )
            await save_reel_dossier(dossier, transcript, url=url)
            return dossier

        # Stage 6: Credible Web Evidence Retrieval (RAG)
        await report(f"Retrieving Credible Sources for {len(claims)} Claims", 75, {"status": "retrieval", "claims_count": len(claims)})
        claim_sources_map = {}
        for c in claims:
            queries = list(c.search_queries) if c.search_queries else []
            if c.claim_text and c.claim_text not in queries:
                queries.append(c.claim_text)
            sources = await self.search_retriever.gather_evidence_for_queries(queries, max_sources_total=5)
            claim_sources_map[c.id] = sources
            # Index to ChromaDB
            self.vector_store.add_evidence(video_id=video_id, claim_id=c.id, sources=sources)

        # Stage 7: Fact Verification Reasoning (with Visual Keyframe Grounding)
        await report("Reasoning & Verifying Claims Against Evidence", 88, {"status": "verifying"})
        claim_verdicts: List[ClaimVerdict] = []
        for c in claims:
            verdict = await self.verifier.verify_claim(c, claim_sources_map.get(c.id, []))
            claim_verdicts.append(verdict)

        # Stage 8: Reel Dossier Synthesis & Storage
        await report("Synthesizing Final Reel Dossier", 95, {"status": "synthesizing"})
        dossier = await self.synthesizer.synthesize_dossier(
            video_id=video_id,
            title=transcript.title or "Instagram Reel",
            author=transcript.author or "Unknown",
            video_path=str(video_path.relative_to(settings.BASE_DIR)),
            duration_seconds=duration,
            claim_verdicts=claim_verdicts
        )

        # Persist to database
        await save_reel_dossier(dossier, transcript, url=url)
        await report("Fact-Check Complete", 100, {"status": "done", "dossier": dossier.model_dump()})

        return dossier
