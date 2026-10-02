import pytest
import io
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from app.claims.models import AtomicClaim, ModalitySource, ClaimCategory
from app.claims.extractor import ClaimExtractor
from app.verification.verifier import ClaimVerifier
from app.verification.models import Verdict, EvidenceSource, CredibilityTier
from app.agent.follow_up_agent import FollowUpAgent, extract_timestamp_from_query
from app.agent.llm_client import encode_image_to_base64
from PIL import Image

def test_extract_timestamp_from_query():
    assert extract_timestamp_from_query("What is that bottle at 0:15?") == 15.0
    assert extract_timestamp_from_query("Look at 1:20 in the video") == 80.0
    assert extract_timestamp_from_query("At 4.5s there is a chart") == 4.5
    assert extract_timestamp_from_query("Is this true overall?") is None

def test_encode_image_to_base64(tmp_path):
    # Create test image
    img = Image.new("RGB", (100, 100), color="blue")
    img_path = tmp_path / "test_frame.jpg"
    img.save(img_path)

    b64 = encode_image_to_base64(img_path, max_dim=50)
    assert isinstance(b64, str)
    assert len(b64) > 50

@pytest.mark.asyncio
async def test_multimodal_claim_extraction(tmp_path):
    # Create dummy frames
    img_path1 = tmp_path / "frame_0001_ts_0.00.jpg"
    img_path2 = tmp_path / "frame_0002_ts_3.00.jpg"
    Image.new("RGB", (50, 50), color="red").save(img_path1)
    Image.new("RGB", (50, 50), color="green").save(img_path2)

    frames = [(0.0, img_path1), (3.0, img_path2)]

    mock_llm = MagicMock()
    mock_llm.provider = "lmstudio"
    mock_llm.generate_json = AsyncMock(return_value={
        "claims": [
            {
                "id": "claim_1",
                "claim_text": "Drinking lemon water cures diabetes",
                "context_in_reel": "Presenter holding lemon chart",
                "timestamp_start": 0.5,
                "timestamp_end": 3.5,
                "keyframe_timestamp": 3.0,
                "modality": "chart_graphic",
                "category": "health_medical",
                "importance_score": 0.95,
                "search_queries": ["lemon water diabetes study", "lemon cures diabetes fact check"]
            }
        ]
    })

    extractor = ClaimExtractor(llm_client=mock_llm)
    claims = await extractor.extract_claims_multimodal(
        video_id="test_vid",
        frames=frames,
        audio_transcript="Drink this lemon water every morning to cure your diabetes.",
        metadata={"title": "Lemon Cure", "duration": 4.0}
    )

    assert len(claims) == 1
    assert claims[0].claim_text == "Drinking lemon water cures diabetes"
    assert claims[0].modality == ModalitySource.CHART_GRAPHIC
    assert claims[0].keyframe_path == str(img_path2)
    assert mock_llm.generate_json.called

@pytest.mark.asyncio
async def test_multimodal_verifier(tmp_path):
    img_path = tmp_path / "frame_0001_ts_2.00.jpg"
    Image.new("RGB", (50, 50), color="blue").save(img_path)

    claim = AtomicClaim(
        id="c1",
        claim_text="Fuel transactions above Rs 2000 incur a flat Rs 5 fee",
        timestamp_start=2.0,
        timestamp_end=5.0,
        modality=ModalitySource.VISUAL_OCR,
        keyframe_path=str(img_path),
        keyframe_timestamp=2.0,
        search_queries=["fuel surcharge flat 5 rupees"]
    )

    sources = [
        EvidenceSource(
            url="https://reuters.com/news",
            title="NPCI Fuel Circular",
            domain="reuters.com",
            snippet="Transactions above 2000 at petrol pumps have a flat Rs 5 surcharge.",
            credibility_tier=CredibilityTier.TIER_1_AUTHORITATIVE
        )
    ]

    mock_llm = MagicMock()
    mock_llm.generate_json = AsyncMock(return_value={
        "verdict": "TRUE",
        "confidence_score": 95,
        "summary_rationale": "Directly confirmed by official NPCI circular.",
        "detailed_analysis": "The circular explicitly states flat Rs 5 for fuel.",
        "key_nuances": "Applies only to wallet PPI payments."
    })

    verifier = ClaimVerifier(llm_client=mock_llm)
    verdict = await verifier.verify_claim(claim, sources)

    assert verdict.verdict == Verdict.TRUE
    assert verdict.confidence_score == 95
    assert verdict.keyframe_url == str(img_path)
    assert mock_llm.generate_json.called
