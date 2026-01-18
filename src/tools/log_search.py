"""Log search tool for querying bot activity logs from the database."""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Optional

from langchain_core.tools import tool
from sqlalchemy import select, and_, or_, func

from ..services.database import get_db_service
from ..orm.tool_execution import ToolExecution
from ..orm.conversation import ConversationHistory
from ..orm.processed_mention import ProcessedMention

logger = logging.getLogger(__name__)


@tool
def search_logs(
    hours_ago: int = 24,
    log_type: str = "all",
    search_term: Optional[str] = None,
    limit: int = 50
) -> str:
    """Search the bot's activity logs for a specified time period.

    This tool searches the bot's database for activity logs including tool executions,
    conversations, and processed mentions. Useful for reviewing what the bot has done,
    debugging issues, or analyzing bot behavior over time.

    Args:
        hours_ago: Number of hours to look back (default: 24, max: 720/30 days)
        log_type: Type of logs to search. Options:
            - "all": All log types (default)
            - "tools": Tool execution logs only
            - "conversations": Conversation history only
            - "mentions": Processed mention logs only
        search_term: Optional text to search for in log content (case-insensitive)
        limit: Maximum number of results to return per log type (default: 50, max: 200)

    Returns:
        Formatted string with search results organized by log type, including
        timestamps, relevant details, and summary statistics.

    Examples:
        - search_logs(hours_ago=1, log_type="tools") - Tool executions in last hour
        - search_logs(hours_ago=24, search_term="github") - All logs mentioning "github"
        - search_logs(hours_ago=168, log_type="conversations", limit=20) - Last week's conversations
    """
    # Validate and constrain parameters
    hours_ago = max(1, min(hours_ago, 720))  # 1 hour to 30 days
    limit = max(1, min(limit, 200))  # 1 to 200 results

    valid_log_types = ["all", "tools", "conversations", "mentions"]
    if log_type not in valid_log_types:
        return f"Error: Invalid log_type '{log_type}'. Must be one of: {', '.join(valid_log_types)}"

    # Calculate time threshold
    time_threshold = datetime.utcnow() - timedelta(hours=hours_ago)

    # Run async database queries in sync context
    try:
        return asyncio.run(_search_logs_async(
            time_threshold, log_type, search_term, limit, hours_ago
        ))
    except Exception as e:
        logger.error(f"Error searching logs: {e}", exc_info=True)
        return f"Error searching logs: {str(e)}"


async def _search_logs_async(
    time_threshold: datetime,
    log_type: str,
    search_term: Optional[str],
    limit: int,
    hours_ago: int
) -> str:
    """Async helper to perform database queries."""
    db = get_db_service()
    results = []

    async with db.session() as session:
        # Search tool executions
        if log_type in ["all", "tools"]:
            tool_results = await _search_tool_executions(
                session, time_threshold, search_term, limit
            )
            if tool_results:
                results.append(tool_results)

        # Search conversation history
        if log_type in ["all", "conversations"]:
            conv_results = await _search_conversations(
                session, time_threshold, search_term, limit
            )
            if conv_results:
                results.append(conv_results)

        # Search processed mentions
        if log_type in ["all", "mentions"]:
            mention_results = await _search_mentions(
                session, time_threshold, search_term, limit
            )
            if mention_results:
                results.append(mention_results)

    # Format results
    if not results:
        return (
            f"No logs found for the past {hours_ago} hours "
            f"(log_type={log_type}, search_term={search_term or 'none'})"
        )

    header = f"=== Log Search Results ===\n"
    header += f"Time period: Last {hours_ago} hours (since {time_threshold.strftime('%Y-%m-%d %H:%M:%S')} UTC)\n"
    header += f"Log type: {log_type}\n"
    if search_term:
        header += f"Search term: '{search_term}'\n"
    header += f"Limit: {limit} per type\n"
    header += "=" * 50 + "\n\n"

    return header + "\n\n".join(results)


async def _search_tool_executions(session, time_threshold, search_term, limit):
    """Search tool execution logs."""
    query = select(ToolExecution).where(
        and_(
            ToolExecution.created_at >= time_threshold,
            ToolExecution.is_deleted == False
        )
    )

    # Apply search term filter if provided
    if search_term:
        search_pattern = f"%{search_term}%"
        query = query.where(
            or_(
                ToolExecution.tool_name.ilike(search_pattern),
                ToolExecution.input_args.ilike(search_pattern),
                ToolExecution.output_result.ilike(search_pattern),
                ToolExecution.error_message.ilike(search_term)
            )
        )

    query = query.order_by(ToolExecution.created_at.desc()).limit(limit)
    result = await session.execute(query)
    executions = result.scalars().all()

    if not executions:
        return None

    output = f"### TOOL EXECUTIONS ({len(executions)} results)\n\n"

    for exe in executions:
        timestamp = exe.created_at.strftime("%Y-%m-%d %H:%M:%S")
        status = "✓ SUCCESS" if exe.success else "✗ FAILED"

        output += f"[{timestamp}] {status} - {exe.tool_name}\n"

        # Parse and format input args
        try:
            args = json.loads(exe.input_args) if exe.input_args else {}
            if args:
                args_str = ", ".join(f"{k}={v}" for k, v in args.items())
                output += f"  Args: {args_str}\n"
        except json.JSONDecodeError:
            output += f"  Args: {exe.input_args}\n"

        # Show result or error
        if exe.success and exe.output_result:
            result_preview = exe.output_result[:200]
            if len(exe.output_result) > 200:
                result_preview += "..."
            output += f"  Result: {result_preview}\n"
        elif exe.error_message:
            output += f"  Error: {exe.error_message}\n"

        # Show token usage
        if exe.execution_time_ms:
            output += f"  Execution time: {exe.execution_time_ms}ms\n"

        if exe.input_tokens or exe.output_tokens:
            token_info = f"  Tokens: in={exe.input_tokens or 0}, out={exe.output_tokens or 0}"
            if exe.cache_read_input_tokens:
                token_info += f", cached={exe.cache_read_input_tokens}"
            output += token_info + "\n"

        output += "\n"

    # Add summary statistics
    total_success = sum(1 for e in executions if e.success)
    total_failed = len(executions) - total_success
    tool_counts = {}
    for e in executions:
        tool_counts[e.tool_name] = tool_counts.get(e.tool_name, 0) + 1

    output += f"Summary: {total_success} successful, {total_failed} failed\n"
    output += f"Tools used: {', '.join(f'{tool}({count})' for tool, count in tool_counts.items())}\n"

    return output


async def _search_conversations(session, time_threshold, search_term, limit):
    """Search conversation history logs."""
    query = select(ConversationHistory).where(
        and_(
            ConversationHistory.created_at >= time_threshold,
            ConversationHistory.is_deleted == False
        )
    )

    # Apply search term filter if provided
    if search_term:
        search_pattern = f"%{search_term}%"
        query = query.where(
            or_(
                ConversationHistory.message_content.ilike(search_pattern),
                ConversationHistory.author_did.ilike(search_pattern)
            )
        )

    query = query.order_by(ConversationHistory.created_at.desc()).limit(limit)
    result = await session.execute(query)
    conversations = result.scalars().all()

    if not conversations:
        return None

    output = f"### CONVERSATION HISTORY ({len(conversations)} results)\n\n"

    for conv in conversations:
        timestamp = conv.created_at.strftime("%Y-%m-%d %H:%M:%S")
        role_icon = "👤" if conv.role == "user" else "🤖"

        output += f"[{timestamp}] {role_icon} {conv.role.upper()}\n"
        output += f"  Thread: {conv.thread_uri}\n"

        if conv.author_did:
            output += f"  Author: {conv.author_did}\n"

        # Show message content preview
        content_preview = conv.message_content[:300]
        if len(conv.message_content) > 300:
            content_preview += "..."
        output += f"  Message: {content_preview}\n"

        # Show token usage if available
        if conv.input_tokens or conv.output_tokens:
            token_info = f"  Tokens: in={conv.input_tokens or 0}, out={conv.output_tokens or 0}"
            if conv.cache_read_input_tokens:
                token_info += f", cached={conv.cache_read_input_tokens}"
            output += token_info + "\n"

        output += "\n"

    # Add summary statistics
    user_messages = sum(1 for c in conversations if c.role == "user")
    assistant_messages = len(conversations) - user_messages
    unique_threads = len(set(c.thread_uri for c in conversations))

    output += f"Summary: {user_messages} user messages, {assistant_messages} assistant messages\n"
    output += f"Unique threads: {unique_threads}\n"

    return output


async def _search_mentions(session, time_threshold, search_term, limit):
    """Search processed mention logs."""
    query = select(ProcessedMention).where(
        and_(
            ProcessedMention.created_at >= time_threshold,
            ProcessedMention.is_deleted == False
        )
    )

    # Apply search term filter if provided
    if search_term:
        search_pattern = f"%{search_term}%"
        query = query.where(
            or_(
                ProcessedMention.mention_uri.ilike(search_pattern),
                ProcessedMention.author_did.ilike(search_pattern),
                ProcessedMention.thread_uri.ilike(search_pattern)
            )
        )

    query = query.order_by(ProcessedMention.created_at.desc()).limit(limit)
    result = await session.execute(query)
    mentions = result.scalars().all()

    if not mentions:
        return None

    output = f"### PROCESSED MENTIONS ({len(mentions)} results)\n\n"

    for mention in mentions:
        timestamp = mention.created_at.strftime("%Y-%m-%d %H:%M:%S")

        output += f"[{timestamp}] Mention processed\n"
        output += f"  URI: {mention.mention_uri}\n"
        output += f"  Author: {mention.author_did}\n"

        if mention.thread_uri:
            output += f"  Thread: {mention.thread_uri}\n"

        output += "\n"

    # Add summary statistics
    unique_authors = len(set(m.author_did for m in mentions))
    unique_threads = len(set(m.thread_uri for m in mentions if m.thread_uri))

    output += f"Summary: {len(mentions)} mentions from {unique_authors} unique authors\n"
    output += f"Unique threads: {unique_threads}\n"

    return output
