"""Wikipedia lookup tool."""

import logging

from langchain_core.tools import tool

logger = logging.getLogger(__name__)


@tool
def search_wikipedia(query: str) -> str:
    """Search Wikipedia for encyclopedic information.

    Use this tool for:
    - Historical facts and figures
    - Scientific concepts and definitions
    - Biographical information
    - Well-established knowledge

    Args:
        query: Topic to search for (person, place, concept, etc.)

    Returns:
        Summary from Wikipedia article(s)
    """
    try:
        from langchain_community.tools import WikipediaQueryRun
        from langchain_community.utilities import WikipediaAPIWrapper

        wrapper = WikipediaAPIWrapper(top_k_results=2, doc_content_chars_max=1000)
        wiki = WikipediaQueryRun(api_wrapper=wrapper)

        results = wiki.run(query)
        logger.info("Wikipedia search completed for: %s", query)

        return results

    except Exception as e:
        logger.error("Wikipedia search failed: %s", e, exc_info=True)
        return f"Error searching Wikipedia: {str(e)}"
