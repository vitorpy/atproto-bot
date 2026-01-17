"""Service for tracking tool executions."""

import json
import logging
from typing import Optional

from ..orm.tool_execution import ToolExecution
from .database import get_db_service

logger = logging.getLogger(__name__)


class ToolService:
    """Service for managing tool execution tracking."""

    async def record_execution(
        self,
        tool_name: str,
        tool_call_id: str,
        input_args: dict,
        output_result: Optional[str],
        success: bool,
        error_message: Optional[str] = None,
        execution_time_ms: Optional[int] = None,
        conversation_id: Optional[str] = None,
        input_tokens: Optional[int] = None,
        output_tokens: Optional[int] = None,
        cache_creation_input_tokens: Optional[int] = None,
        cache_read_input_tokens: Optional[int] = None,
        thinking_content: Optional[str] = None,
    ) -> ToolExecution:
        """Record a tool execution in the database."""
        db = get_db_service()
        async with db.session() as session:
            execution = ToolExecution(
                conversation_id=conversation_id,
                tool_name=tool_name,
                tool_call_id=tool_call_id,
                input_args=json.dumps(input_args),
                output_result=output_result,
                success=success,
                error_message=error_message,
                execution_time_ms=execution_time_ms,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cache_creation_input_tokens=cache_creation_input_tokens,
                cache_read_input_tokens=cache_read_input_tokens,
                thinking_content=thinking_content,
            )
            session.add(execution)
            await session.commit()
            await session.refresh(execution)

            logger.debug(
                "Recorded tool execution: %s (success=%s, time=%sms)",
                tool_name,
                success,
                execution_time_ms,
            )

            return execution
