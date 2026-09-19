import re
from urllib.parse import urlparse
from typing import Tuple
from app.verification.models import CredibilityTier

# High-authority domains
AUTHORITATIVE_DOMAINS = {
    # Fact-checking organizations (IFCN certified)
    "snopes.com", "politifact.com", "factcheck.org", "leadstories.com",
    "fullfact.org", "checkyourfact.com", "reuters.com/fact-check",
    "apnews.com/hub/ap-fact-check", "bbc.com/news/reality_check", "climatefeedback.org", "healthfeedback.org",
    
    # Official Health / Scientific / Gov Organizations
    "who.int", "cdc.gov", "nih.gov", "fda.gov", "nasa.gov", "noaa.gov",
    "epa.gov", "usda.gov", "ncbi.nlm.nih.gov", "pubmed.ncbi.nlm.nih.gov",
    "nature.com", "science.org", "thelancet.com", "nejm.org", "bmj.com",
    "cell.com", "jamanetwork.com", "pnas.org", "sciencedirect.com",
    "scientificamerican.com", "cochranelibrary.com",
}

# Reputable Mainstream & Educational Journalism
REPUTABLE_DOMAINS = {
    "reuters.com", "apnews.com", "bbc.com", "bbc.co.uk", "bloomberg.com",
    "theguardian.com", "nytimes.com", "washingtonpost.com", "wsj.com",
    "economist.com", "npr.org", "pbs.org", "theatlantic.com",
    "nationalgeographic.com", "newscientist.com", "phys.org",
    "mayoclinic.org", "clevelandclinic.org", "hopkinsmedicine.org",
    "harvard.edu", "mit.edu", "stanford.edu", "ox.ac.uk", "cam.ac.uk"
}

# Questionable / Low Reliability Patterns
UNRELIABLE_DOMAINS = {
    "naturalnews.com", "infowars.com", "thegatewaypundit.com", "dailymail.co.uk",
    "thesun.co.uk", "beforeitsnews.com", "worldnewsdailyreport.com"
}

def extract_domain(url: str) -> str:
    """Extract clean domain name from URL."""
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        if domain.startswith("www."):
            domain = domain[4:]
        return domain
    except Exception:
        return ""

def score_domain_credibility(url: str) -> Tuple[CredibilityTier, float, bool]:
    """
    Evaluates credibility tier and score (0.0 - 1.0) for a given source URL.
    Returns: (CredibilityTier, score, is_fact_check_article)
    """
    domain = extract_domain(url)
    lower_url = url.lower()

    # Check for dedicated fact-checking URLs
    is_fact_check = (
        "fact-check" in lower_url or
        "factcheck" in lower_url or
        "snopes.com" in domain or
        "politifact.com" in domain or
        "leadstories.com" in domain or
        "healthfeedback.org" in domain or
        "climatefeedback.org" in domain
    )

    # Check .gov and .edu top-level domains
    if domain.endswith(".gov") or domain.endswith(".mil"):
        return CredibilityTier.TIER_1_AUTHORITATIVE, 0.98, is_fact_check
    
    if domain.endswith(".edu") or domain.endswith(".ac.uk"):
        return CredibilityTier.TIER_1_AUTHORITATIVE, 0.95, is_fact_check

    # Check Authoritative set
    for auth_d in AUTHORITATIVE_DOMAINS:
        if auth_d in domain or domain.endswith(auth_d):
            return CredibilityTier.TIER_1_AUTHORITATIVE, 0.95, is_fact_check

    # Check Reputable set
    for rep_d in REPUTABLE_DOMAINS:
        if rep_d in domain or domain.endswith(rep_d):
            return CredibilityTier.TIER_2_REPUTABLE, 0.85, is_fact_check

    # Check Unreliable set
    for unk_d in UNRELIABLE_DOMAINS:
        if unk_d in domain or domain.endswith(unk_d):
            return CredibilityTier.TIER_4_UNRELIABLE, 0.20, is_fact_check

    # Standard general web domain
    return CredibilityTier.TIER_3_GENERAL, 0.60, is_fact_check
