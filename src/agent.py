"""Agent loop for tool calling."""

import logging
import time
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage
from langchain_core.tools import BaseTool

from .services import ToolService

logger = logging.getLogger(__name__)


class ToolCallingAgent:
    """Agent that can use tools to answer questions."""

    def __init__(
        self,
        llm: BaseChatModel,
        tools: list[BaseTool],
        max_iterations: int = 10,
        tool_service: ToolService | None = None,
    ):
        """Initialize the agent.

        Args:
            llm: The language model to use
            tools: List of tools available to the agent
            max_iterations: Maximum number of agent loop iterations
            tool_service: Optional service for tracking tool usage
        """
        self.llm = llm.bind_tools(tools)
        self.tools = {tool.name: tool for tool in tools}
        self.max_iterations = max_iterations
        self.tool_service = tool_service

    async def run(
        self,
        messages: list[BaseMessage],
        conversation_id: str | None = None,
    ) -> AIMessage:
        """Run the agent loop with tool calling.

        Args:
            messages: Initial messages (SystemMessage + HumanMessage)
            conversation_id: Optional conversation ID for tracking

        Returns:
            Final AIMessage with response
        """
        iteration = 0

        while iteration < self.max_iterations:
            iteration += 1
            logger.debug("Agent iteration %d/%d", iteration, self.max_iterations)

            # Call LLM
            try:
                response = self.llm.invoke(messages)
            except Exception as e:
                logger.error("LLM invocation failed: %s", e, exc_info=True)
                # Return error as AIMessage
                return AIMessage(
                    content=f"I encountered an error while processing your request: {str(e)}"
                )

            # Extract token usage for cost tracking
            usage_metadata = getattr(response, "usage_metadata", None) or {}
            input_tokens = usage_metadata.get("input_tokens")
            output_tokens = usage_metadata.get("output_tokens")
            cache_creation_tokens = usage_metadata.get("cache_creation_input_tokens")
            cache_read_tokens = usage_metadata.get("cache_read_input_tokens")

            # Extract extended thinking content if available
            thinking_content = None
            response_metadata = getattr(response, "response_metadata", {})
            if "thinking" in response_metadata:
                thinking_content = response_metadata["thinking"]
                logger.info("Extended thinking: %s", thinking_content[:200] + "..." if len(thinking_content) > 200 else thinking_content)

            if cache_creation_tokens or cache_read_tokens:
                logger.info(
                    "Token usage: input=%s, output=%s, cache_creation=%s, cache_read=%s",
                    input_tokens,
                    output_tokens,
                    cache_creation_tokens,
                    cache_read_tokens,
                )

            # Add response to messages
            messages.append(response)

            # Check if model wants to use tools
            if not response.tool_calls:
                logger.debug("No tool calls - returning final response")
                return response

            logger.info("Agent making %d tool call(s)", len(response.tool_calls))

            # Execute tool calls
            for tool_call in response.tool_calls:
                await self._execute_tool_call(
                    tool_call,
                    messages,
                    conversation_id,
                    input_tokens,
                    output_tokens,
                    cache_creation_tokens,
                    cache_read_tokens,
                    thinking_content,
                )

        # Max iterations reached
        logger.warning("Agent reached max iterations (%d)", self.max_iterations)
        return AIMessage(
            content=(
                "I apologize, but I've reached the limit of tool usage attempts. "
                "Please try rephrasing your question or breaking it into smaller parts."
            )
        )

    async def _execute_tool_call(
        self,
        tool_call: dict[str, Any],
        messages: list[BaseMessage],
        conversation_id: str | None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        cache_creation_tokens: int | None = None,
        cache_read_tokens: int | None = None,
        thinking_content: str | None = None,
    ) -> None:
        """Execute a single tool call and append ToolMessage.

        Args:
            tool_call: Tool call dict from AIMessage
            messages: Message list to append result to
            conversation_id: Optional conversation ID for tracking
        """
        tool_name = tool_call["name"]
        tool_args = tool_call["args"]
        tool_id = tool_call["id"]

        logger.info("Executing tool: %s with args: %s", tool_name, tool_args)

        start_time = time.time()
        success = True
        error_message = None

        try:
            # Check if tool exists
            if tool_name not in self.tools:
                result = (
                    f"Error: Tool '{tool_name}' not found. "
                    f"Available tools: {list(self.tools.keys())}"
                )
                success = False
                error_message = f"Tool not found: {tool_name}"
            else:
                # Execute tool
                tool = self.tools[tool_name]
                result = tool.invoke(tool_args)

                # Check if result indicates failure
                if isinstance(result, str) and result.startswith("Error"):
                    success = False
                    error_message = result

        except Exception as e:
            logger.error("Tool execution failed: %s", e, exc_info=True)
            result = f"Tool execution failed: {str(e)}"
            success = False
            error_message = str(e)

        execution_time_ms = int((time.time() - start_time) * 1000)

        # Track in database
        if self.tool_service:
            try:
                await self.tool_service.record_execution(
                    tool_name=tool_name,
                    tool_call_id=tool_id,
                    input_args=tool_args,
                    output_result=str(result),
                    success=success,
                    error_message=error_message,
                    execution_time_ms=execution_time_ms,
                    conversation_id=conversation_id,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cache_creation_input_tokens=cache_creation_tokens,
                    cache_read_input_tokens=cache_read_tokens,
                )
            except Exception as e:
                logger.error("Failed to track tool execution: %s", e)

        # Create ToolMessage
        tool_message = ToolMessage(
            content=str(result),
            tool_call_id=tool_id,
            name=tool_name,
        )

        messages.append(tool_message)

        logger.debug(
            "Tool %s completed in %dms (success=%s)", tool_name, execution_time_ms, success
        )
