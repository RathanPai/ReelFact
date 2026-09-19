import pytest
from httpx import AsyncClient, ASGITransport
from app.api.main import app
from app.database.storage import init_db, save_reel_dossier
from app.verification.models import ReelDossier, ClaimVerdict, Verdict

@pytest.mark.asyncio
async def test_api_endpoints():
    await init_db()

    # Seed a test reel dossier
    dossier = ReelDossier(
        video_id="test_reel_e2e",
        title="Test Reel Fact Check",
        author="HealthCreator",
        duration_seconds=12.0,
        overall_trust_score=85,
        overall_verdict=Verdict.MOSTLY_TRUE,
        executive_summary="This reel contains mostly verified claims with minor nuances.",
        claims=[
            ClaimVerdict(
                claim_id="c1",
                claim_text="Drinking water helps with hydration",
                verdict=Verdict.TRUE,
                confidence_score=99,
                summary_rationale="Well supported by all medical sources",
                detailed_analysis="Water is essential for cellular hydration.",
                sources=[]
            )
        ]
    )
    await save_reel_dossier(dossier)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # Test frontend root
        res_root = await ac.get("/")
        assert res_root.status_code == 200
        assert "ReelFact" in res_root.text

        # Test listing reels
        res_list = await ac.get("/api/reels")
        assert res_list.status_code == 200
        reels = res_list.json()
        assert any(r["id"] == "test_reel_e2e" for r in reels)

        # Test getting single reel
        res_single = await ac.get("/api/reels/test_reel_e2e")
        assert res_single.status_code == 200
        data = res_single.json()
        assert data["dossier"]["video_id"] == "test_reel_e2e"
        assert len(data["dossier"]["claims"]) == 1

        # Test status endpoint
        res_status = await ac.get("/api/status/test_reel_e2e")
        assert res_status.status_code == 200
        assert res_status.json()["status"] == "done"
