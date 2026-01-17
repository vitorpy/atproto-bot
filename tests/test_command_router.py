"""Tests for CommandRouter."""

import pytest

from src.command_router import CommandRouter, CommandType, ParsedCommand


class TestCommandRouter:
    """Test command router functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.router = CommandRouter()
        self.bot_handle = "bot.bsky.social"

    def test_parse_selfimprovement_command(self):
        """Test parsing /selfimprovement command."""
        text = "@bot /selfimprovement add logging to mentions"
        cmd = self.router.parse_command(text, self.bot_handle)

        assert cmd is not None
        assert cmd.command_type == CommandType.SELFIMPROVEMENT
        assert cmd.arguments == "add logging to mentions"
        assert cmd.raw_text == text

    def test_parse_command_with_full_handle(self):
        """Test parsing command with full bot handle."""
        text = "@bot.bsky.social /selfimprovement refactor config"
        cmd = self.router.parse_command(text, self.bot_handle)

        assert cmd is not None
        assert cmd.command_type == CommandType.SELFIMPROVEMENT
        assert cmd.arguments == "refactor config"

    def test_parse_command_without_arguments(self):
        """Test parsing command without arguments."""
        text = "@bot /selfimprovement"
        cmd = self.router.parse_command(text, self.bot_handle)

        assert cmd is not None
        assert cmd.command_type == CommandType.SELFIMPROVEMENT
        assert cmd.arguments == ""

    def test_parse_command_case_insensitive(self):
        """Test that command parsing is case insensitive."""
        text = "@bot /SELFIMPROVEMENT Add Tests"
        cmd = self.router.parse_command(text, self.bot_handle)

        assert cmd is not None
        assert cmd.command_type == CommandType.SELFIMPROVEMENT
        assert cmd.arguments == "Add Tests"

    def test_parse_invalid_command(self):
        """Test parsing invalid command returns None."""
        text = "@bot /invalidcommand do something"
        cmd = self.router.parse_command(text, self.bot_handle)

        assert cmd is None

    def test_parse_non_command_text(self):
        """Test parsing non-command text returns None."""
        text = "@bot please help me with something"
        cmd = self.router.parse_command(text, self.bot_handle)

        assert cmd is None

    def test_parse_command_with_extra_spaces(self):
        """Test parsing command with extra whitespace."""
        text = "@bot   /selfimprovement   add   tests"
        cmd = self.router.parse_command(text, self.bot_handle)

        assert cmd is not None
        assert cmd.command_type == CommandType.SELFIMPROVEMENT
        assert cmd.arguments == "add   tests"  # Preserves internal spaces

    def test_is_command_returns_true(self):
        """Test is_command helper method returns True for valid commands."""
        text = "@bot /selfimprovement add tests"
        assert self.router.is_command(text, self.bot_handle) is True

    def test_is_command_returns_false(self):
        """Test is_command helper method returns False for non-commands."""
        text = "@bot please help"
        assert self.router.is_command(text, self.bot_handle) is False

    def test_parse_command_without_mention(self):
        """Test parsing command in DM (no @mention)."""
        text = "/selfimprovement add error handling"
        cmd = self.router.parse_command(text, self.bot_handle)

        assert cmd is not None
        assert cmd.command_type == CommandType.SELFIMPROVEMENT
        assert cmd.arguments == "add error handling"

    def test_parse_multiline_arguments(self):
        """Test parsing command with multiline arguments."""
        text = "@bot /selfimprovement add a new feature\nthat does X\nand Y"
        cmd = self.router.parse_command(text, self.bot_handle)

        assert cmd is not None
        assert cmd.command_type == CommandType.SELFIMPROVEMENT
        assert "add a new feature" in cmd.arguments
        assert "\n" in cmd.arguments

    def test_parse_empty_text(self):
        """Test parsing empty text returns None."""
        cmd = self.router.parse_command("", self.bot_handle)
        assert cmd is None

    def test_parse_none_text(self):
        """Test parsing None text returns None."""
        cmd = self.router.parse_command(None, self.bot_handle)
        assert cmd is None
