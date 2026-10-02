import asyncio
import logging
from typing import List, Dict, Any

try:
    from ddgs import DDGS
except ImportError:
    from duckduckgo_search import DDGS

from app.config import settings
from app.verification.models import EvidenceSource
from app.retrieval.credibility import score_domain_credibility, extract_domain
from app.retrieval.crawler import fetch_article_text

logger = logging.getLogger(__name__)

class SearchRetriever:
    def __init__(self):
        self.provider = settings.SEARCH_PROVIDER
        self.tavily_api_key = settings.TAVILY_API_KEY

    async def search_duckduckgo(self, query: str, max_results: int = 4) -> List[Dict[str, Any]]:
        """Search DuckDuckGo with automatic news fallback and query cleaning."""
        import re
        def _ddg_sync():
            results = []
            clean_q = re.sub(r"[^\w\s\-\.\%]", " ", query).strip()
            # Trim excessively long queries to first 10 words for search engine friendliness
            clean_words = clean_q.split()
            if len(clean_words) > 10:
                clean_q = " ".join(clean_words[:10])

            # 1. Try DuckDuckGo standard text search
            try:
                with DDGS() as ddgs:
                    raw_results = list(ddgs.text(clean_q, max_results=max_results))
                    for r in raw_results:
                        results.append({
                            "title": r.get("title", ""),
                            "url": r.get("href", ""),
                            "snippet": r.get("body", ""),
                        })
            except Exception as e:
                logger.debug(f"DuckDuckGo text search error for '{clean_q}': {e}")

            # 2. Fallback to DuckDuckGo News search for current events/political claims
            if not results:
                try:
                    with DDGS() as ddgs:
                        raw_news = list(ddgs.news(clean_q, max_results=max_results))
                        for r in raw_news:
                            results.append({
                                "title": r.get("title", ""),
                                "url": r.get("url", ""),
                                "snippet": r.get("body", ""),
                            })
                except Exception as e:
                    logger.debug(f"DuckDuckGo news search error for '{clean_q}': {e}")

            return results

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _ddg_sync)


    async def search_tavily(self, query: str, max_results: int = 5) -> List[Dict[str, Any]]:
        """Search Tavily if API key is provided."""
        if not self.tavily_api_key:
            return await self.search_duckduckgo(query, max_results)
        
        import httpx
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post(
                    "https://api.tavily.com/search",
                    json={
                        "api_key": self.tavily_api_key,
                        "query": query,
                        "search_depth": "advanced",
                        "max_results": max_results,
                        "include_answer": False,
                    }
                )
                if res.status_code == 200:
                    data = res.json()
                    return [
                        {
                            "title": r.get("title", ""),
                            "url": r.get("url", ""),
                            "snippet": r.get("content", ""),
                        }
                        for r in data.get("results", [])
                    ]
        except Exception as e:
            logger.error(f"Tavily search error: {e}, falling back to DuckDuckGo")
        return await self.search_duckduckgo(query, max_results)

    async def search_query(self, query: str, max_results: int = 5) -> List[EvidenceSource]:
        """Perform search and enrich with credibility tiers."""
        if self.provider == "tavily" and self.tavily_api_key:
            raw_results = await self.search_tavily(query, max_results=max_results)
        else:
            raw_results = await self.search_duckduckgo(query, max_results=max_results)

        evidence_list: List[EvidenceSource] = []
        for item in raw_results:
            url = item.get("url", "")
            if not url or not url.startswith("http"):
                continue
            
            domain = extract_domain(url)
            tier, score, is_fact_check = score_domain_credibility(url)
            
            evidence_list.append(EvidenceSource(
                url=url,
                title=item.get("title", domain),
                domain=domain,
                snippet=item.get("snippet", ""),
                credibility_tier=tier,
                credibility_score=score,
                is_fact_check_article=is_fact_check
            ))

        # Sort by credibility score descending (fact-checks & authoritative sources first)
        evidence_list.sort(key=lambda e: (e.is_fact_check_article, e.credibility_score), reverse=True)
        return evidence_list

    async def gather_evidence_for_queries(self, queries: List[str], max_sources_total: int = 6) -> List[EvidenceSource]:
        """Runs search across multiple targeted queries, deduplicates by domain/URL, and crawls text."""
        tasks = [self.search_query(q, max_results=4) for q in queries]
        all_results = await asyncio.gather(*tasks, return_exceptions=True)

        seen_urls = set()
        combined_sources: List[EvidenceSource] = []

        for res in all_results:
            if isinstance(res, list):
                for src in res:
                    if src.url not in seen_urls:
                        seen_urls.add(src.url)
                        combined_sources.append(src)

        # Sort by credibility
        combined_sources.sort(key=lambda e: (e.is_fact_check_article, e.credibility_score), reverse=True)
        top_sources = combined_sources[:max_sources_total]

        # Concurrently fetch full article text for top sources to get high-accuracy excerpts
        fetch_tasks = [fetch_article_text(s.url) for s in top_sources]
        article_texts = await asyncio.gather(*fetch_tasks, return_exceptions=True)

        for i, text in enumerate(article_texts):
            if isinstance(text, str) and text:
                top_sources[i].relevant_quote = text[:1500]  # First 1500 chars for LLM context

        return top_sources
