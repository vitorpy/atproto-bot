"""Tool definitions for the bot."""

from .calculator import calculator
from .web_search import search_web
from .wikipedia import search_wikipedia

# All available tools
ALL_TOOLS = [
    search_web,
    calculator,
    search_wikipedia,
]

__all__ = [
    "ALL_TOOLS",
    "calculator",
    "search_web",
    "search_wikipedia",
]
