"""Tool definitions for the bot."""

from .calculator import calculator
from .log_search import search_logs
from .web_search import search_web
from .wikipedia import search_wikipedia

# All available tools
ALL_TOOLS = [
    search_web,
    calculator,
    search_wikipedia,
    search_logs,
]

__all__ = [
    "ALL_TOOLS",
    "calculator",
    "search_logs",
    "search_web",
    "search_wikipedia",
]
