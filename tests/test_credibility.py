import pytest
from app.retrieval.credibility import score_domain_credibility, extract_domain
from app.verification.models import CredibilityTier

def test_extract_domain():
    assert extract_domain("https://www.snopes.com/fact-check/lemon-water") == "snopes.com"
    assert extract_domain("http://cdc.gov/coronavirus") == "cdc.gov"
    assert extract_domain("https://sub.nature.com/articles/123") == "sub.nature.com"

def test_authoritative_domains():
    tier, score, is_fc = score_domain_credibility("https://www.cdc.gov/flu/index.html")
    assert tier == CredibilityTier.TIER_1_AUTHORITATIVE
    assert score >= 0.95

    tier, score, is_fc = score_domain_credibility("https://pubmed.ncbi.nlm.nih.gov/31234567/")
    assert tier == CredibilityTier.TIER_1_AUTHORITATIVE
    assert score >= 0.95

    tier, score, is_fc = score_domain_credibility("https://www.snopes.com/fact-check/test")
    assert tier == CredibilityTier.TIER_1_AUTHORITATIVE
    assert is_fc is True

def test_reputable_news_domains():
    tier, score, is_fc = score_domain_credibility("https://www.reuters.com/business/finance-news")
    assert tier == CredibilityTier.TIER_2_REPUTABLE or tier == CredibilityTier.TIER_1_AUTHORITATIVE
    assert score >= 0.8

def test_unreliable_domains():
    tier, score, is_fc = score_domain_credibility("https://www.naturalnews.com/cure-everything")
    assert tier == CredibilityTier.TIER_4_UNRELIABLE
    assert score <= 0.3
