import pytest
from app.retrieval.search import SearchRetriever

@pytest.mark.asyncio
async def test_search_retriever():
    retriever = SearchRetriever()
    results = await retriever.search_query("who organization health guidelines", max_results=3)
    assert len(results) > 0
    assert any("who.int" in r.domain or "health" in r.snippet.lower() or "who" in r.title.lower() for r in results)
