import pytest
from app.claims.models import AtomicClaim, ClaimCategory, ModalitySource
from app.verification.models import ClaimVerdict, Verdict, ReelDossier, EvidenceSource, CredibilityTier
from app.verification.synthesizer import ReelSynthesizer

def test_atomic_claim_schema():
    claim = AtomicClaim(
        id="claim_1",
        claim_text="Cold showers increase metabolism by 200%",
        context_in_reel="Opening statement",
        timestamp_start=1.2,
        timestamp_end=4.5,
        modality=ModalitySource.AUDIO,
        category=ClaimCategory.HEALTH_MEDICAL,
        search_queries=["cold showers metabolism increase study"]
    )
    assert claim.id == "claim_1"
    assert claim.timestamp_start == 1.2
    assert claim.category == ClaimCategory.HEALTH_MEDICAL

@pytest.mark.asyncio
async def test_reel_synthesizer_scoring():
    synthesizer = ReelSynthesizer()
    
    claims = [
        ClaimVerdict(
            claim_id="c1",
            claim_text="Claim A",
            verdict=Verdict.TRUE,
            confidence_score=90,
            summary_rationale="Supported by CDC",
            detailed_analysis="Evidence details...",
            sources=[]
        ),
        ClaimVerdict(
            claim_id="c2",
            claim_text="Claim B",
            verdict=Verdict.FALSE,
            confidence_score=95,
            summary_rationale="Refuted by peer-reviewed paper",
            detailed_analysis="Evidence details...",
            sources=[]
        )
    ]

    dossier = await synthesizer.synthesize_dossier(
        video_id="vid1",
        title="Test Reel",
        author="Tester",
        video_path="data/raw/vid1.mp4",
        duration_seconds=15.0,
        claim_verdicts=claims
    )

    assert dossier.claims_count == 2
    assert dossier.true_count == 1
    assert dossier.false_count == 1
    assert dossier.overall_trust_score == 50  # (100 + 0) / 2
    assert dossier.overall_verdict == Verdict.FALSE or dossier.overall_verdict == Verdict.MISLEADING
