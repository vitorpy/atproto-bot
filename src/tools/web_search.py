"""Web search tool using DuckDuckGo."""

import logging

from langchain_core.tools import tool

logger = logging.getLogger(__name__)


@tool
def search_web(query: str) -> str:
    """Search the web for current information, news, or facts.

    Use this tool when you need:
    - Current events or recent news
    - Real-time information (weather, stock prices, etc.)
    - Facts that may have changed since your training data
    - General web searches

    Args:
        query: The search query (be specific for best results)

    Returns:
        Search results as formatted text
    """
    try:
        from langchain_community.tools import DuckDuckGoSearchRun

        search = DuckDuckGoSearchRun()
        results = search.run(query)

        logger.info("Web search completed for query: %s", query)
        return results

    except Exception as e:
        logger.error("Web search failed: %s", e, exc_info=True)
        return f"Error performing web search: {str(e)}"
