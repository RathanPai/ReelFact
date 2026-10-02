import logging
import httpx
import trafilatura
from typing import Optional

logger = logging.getLogger(__name__)

async def fetch_article_text(url: str, timeout_sec: float = 6.0) -> Optional[str]:
    """
    Fetches the web page content and extracts clean, structured main body text
    using trafilatura. Returns None if unreachable, blocked by WAF/403, or paywalled.
    The pipeline automatically falls back to search engine excerpts when this occurs.
    """
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Sec-Ch-Ua": "\"Google Chrome\";v=\"129\", \"Chromium\";v=\"129\", \"Not=A?Brand\";v=\"24\"",
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": "\"Windows\"",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1"
    }
    
    try:
        async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=timeout_sec) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                # Many news sites (e.g. NDTV, Telegraph) block automated scrapers with 403.
                # This is normal; DuckDuckGo search snippets serve as reliable fallback.
                logger.debug(f"Full article fetch skipped for {url} (status: {resp.status_code}), using search excerpt fallback.")
                return None
            
            html = resp.text
            # Extract main article body
            extracted = trafilatura.extract(
                html,
                include_comments=False,
                include_tables=True,
                include_links=False,
                output_format="txt"
            )
            
            if extracted and len(extracted.strip()) > 100:
                return extracted.strip()
            
            return None
    except Exception as e:
        logger.debug(f"Error fetching article text for {url}: {e}")
        return None

