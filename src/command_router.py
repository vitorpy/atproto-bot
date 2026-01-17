"""Command router for parsing and routing slash commands."""

import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class CommandType(Enum):
    """Available slash command types."""

    SELFIMPROVEMENT = "selfimprovement"
    # Future commands can be added here


@dataclass
class ParsedCommand:
    """Parsed slash command with its arguments."""

    command_type: CommandType
    arguments: str
    raw_text: str


class CommandRouter:
    """Parse and route slash commands from mentions/DMs."""

    COMMAND_PREFIX = "/"

    def __init__(self):
        """Initialize the command router."""
        # Build regex pattern from available commands
        command_names = "|".join(cmd.value for cmd in CommandType)
        # Match: /command followed by optional whitespace and arguments
        self.command_pattern = re.compile(
            rf"{re.escape(self.COMMAND_PREFIX)}({command_names})(?:\s+(.*))?$",
            re.IGNORECASE | re.DOTALL,
        )

    def parse_command(self, text: str, bot_handle: str) -> Optional[ParsedCommand]:
        """
        Extract slash command from mention/DM text.

        Args:
            text: The full text of the mention or DM.
            bot_handle: The bot's handle (to strip @mentions).

        Returns:
            ParsedCommand if valid slash command found, else None.

        Examples:
            >>> router = CommandRouter()
            >>> cmd = router.parse_command("@bot /selfimprovement add tests", "bot.bsky.social")
            >>> cmd.command_type == CommandType.SELFIMPROVEMENT
            True
            >>> cmd.arguments
            'add tests'
        """
        if not text:
            return None

        # Remove @bot-handle from the text (case insensitive)
        # Handle various formats: @handle, @handle.bsky.social
        cleaned_text = self._strip_bot_mention(text, bot_handle)

        # Try to match command pattern
        match = self.command_pattern.match(cleaned_text.strip())
        if not match:
            return None

        command_name = match.group(1).lower()
        arguments = match.group(2) or ""
        arguments = arguments.strip()

        # Convert command name to CommandType
        try:
            command_type = CommandType(command_name)
        except ValueError:
            # Invalid command (shouldn't happen due to regex, but be safe)
            return None

        return ParsedCommand(
            command_type=command_type,
            arguments=arguments,
            raw_text=text,
        )

    def is_command(self, text: str, bot_handle: str) -> bool:
        """
        Quick check if text contains a slash command.

        Args:
            text: The text to check.
            bot_handle: The bot's handle.

        Returns:
            True if text contains a valid slash command, else False.
        """
        return self.parse_command(text, bot_handle) is not None

    def _strip_bot_mention(self, text: str, bot_handle: str) -> str:
        """
        Remove @bot-handle from text.

        Handles various mention formats:
        - @bot.bsky.social
        - @bot
        - Multiple spaces after mention

        Args:
            text: The text containing potential @mention.
            bot_handle: The bot's full handle (e.g., "bot.bsky.social").

        Returns:
            Text with bot mention removed.
        """
        # Try full handle first (e.g., @bot.bsky.social)
        patterns = [
            rf"@{re.escape(bot_handle)}\s*",
            # Also try short handle (e.g., @bot from bot.bsky.social)
            rf"@{re.escape(bot_handle.split('.')[0])}\s*",
        ]

        result = text
        for pattern in patterns:
            result = re.sub(pattern, "", result, flags=re.IGNORECASE)

        return result
