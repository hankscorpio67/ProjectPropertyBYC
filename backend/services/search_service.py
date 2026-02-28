"""
Brave Search API wrapper for web research during conversations.
"""
import time
from typing import List, Dict, Optional
import httpx

from ..config import config

# Simple in-memory cache: {query: (timestamp, results)}
_cache: Dict[str, tuple] = {}
_CACHE_TTL = 3600  # 1 hour


async def web_search(query: str, count: int = None) -> List[Dict]:
    """
    Search the web using Brave Search API.
    Returns list of {title, url, description} dicts.
    """
    if not config.BRAVE_SEARCH_API_KEY:
        return [{"title": "Search unavailable", "url": "", "description": "No Brave Search API key configured."}]

    k = count or config.SEARCH_RESULTS_COUNT

    # Check cache
    cache_key = f"{query}:{k}"
    if cache_key in _cache:
        ts, results = _cache[cache_key]
        if time.time() - ts < _CACHE_TTL:
            return results

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                "https://api.search.brave.com/res/v1/web/search",
                headers={
                    "Accept": "application/json",
                    "Accept-Encoding": "gzip",
                    "X-Subscription-Token": config.BRAVE_SEARCH_API_KEY,
                },
                params={"q": query, "count": k, "safesearch": "moderate"},
            )
            resp.raise_for_status()
            data = resp.json()

        results = []
        for item in data.get("web", {}).get("results", [])[:k]:
            results.append({
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "description": item.get("description", ""),
            })

        _cache[cache_key] = (time.time(), results)
        return results

    except Exception as e:
        print(f"[search] error: {e}")
        return [{"title": "Search error", "url": "", "description": str(e)}]


def format_search_results(results: List[Dict]) -> str:
    """Format search results as Markdown for injection into Claude context."""
    if not results:
        return ""
    lines = ["**Web Search Results:**\n"]
    for i, r in enumerate(results, 1):
        lines.append(f"{i}. **{r['title']}**")
        if r.get("url"):
            lines.append(f"   Source: {r['url']}")
        if r.get("description"):
            lines.append(f"   {r['description']}")
        lines.append("")
    return "\n".join(lines)
