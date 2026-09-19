import logging
import httpx
import trafilatura
from typing import Optional

logger = logging.getLogger(__name__)

async def fetch_article_text(url: str, timeout_sec: float = 8.0) -> Optional[str]:
    """
    Fetches the web page content and extracts clean, structured main body text
    using trafilatura. Returns None if unreachable or paywalled.
    """
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }
    
    try:
        async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=timeout_sec) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                logger.warning(f"Failed to fetch {url}, status code: {resp.status_code}")
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
        logger.debug(f"Error fetching article at {url}: {e}")
        return None
