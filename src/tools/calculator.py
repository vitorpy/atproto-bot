"""Calculator tool for precise mathematical operations."""

import logging
import math
import re

from langchain_core.tools import tool

logger = logging.getLogger(__name__)


@tool
def calculator(expression: str) -> str:
    """Evaluate mathematical expressions with precision.

    Use this tool for:
    - Exact numeric calculations
    - Complex math operations (sqrt, sin, cos, log, etc.)
    - Multi-step calculations

    Supports: +, -, *, /, **, sqrt, sin, cos, tan, log, exp, pi, e

    Args:
        expression: Mathematical expression (e.g., "sqrt(16) + 2 * 3")

    Returns:
        Result of the calculation
    """
    try:
        # Sanitize input - allow only safe characters
        safe_chars = re.compile(r"^[0-9+\-*/().sqrt\s,sincotanlogexpie]+$")
        if not safe_chars.match(expression):
            return f"Error: Expression contains invalid characters: {expression}"

        # Safe evaluation with limited namespace
        safe_dict = {
            "__builtins__": {},
            "math": math,
            "sqrt": math.sqrt,
            "sin": math.sin,
            "cos": math.cos,
            "tan": math.tan,
            "log": math.log,
            "exp": math.exp,
            "pi": math.pi,
            "e": math.e,
        }

        result = eval(expression, safe_dict)
        logger.info("Calculator evaluated: %s = %s", expression, result)

        return str(result)

    except SyntaxError as e:
        return f"Syntax error in expression: {str(e)}"
    except Exception as e:
        logger.error("Calculator error: %s", e, exc_info=True)
        return f"Error evaluating expression: {str(e)}"
