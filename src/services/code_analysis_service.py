"""Code analysis service using Claude for code generation."""

import ast
import json
import logging
import os
import re
from pathlib import Path
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

logger = logging.getLogger(__name__)


class CodeAnalysisService:
    """Claude-powered code analysis and generation."""

    def __init__(self, llm: BaseChatModel, repo_path: Path | str):
        """
        Initialize code analysis service.

        Args:
            llm: LangChain LLM instance (Claude).
            repo_path: Path to the repository root.
        """
        self.llm = llm
        self.repo_path = Path(repo_path).expanduser().resolve()
        logger.debug("CodeAnalysisService initialized for repo: %s", self.repo_path)

    async def analyze_and_generate_changes(
        self, prompt: str, conversation_id: str
    ) -> dict[str, Any]:
        """
        Analyze codebase and generate changes based on prompt.

        Args:
            prompt: User's improvement request.
            conversation_id: Conversation ID for tracking.

        Returns:
            Dict containing:
                - success: bool
                - changes: list of file changes
                - explanation: what was changed and why
                - branch_name: suggested branch name
                - commit_message: commit message
                - pr_title: PR title
                - pr_body: PR description
        """
        logger.info("Analyzing prompt and generating code changes...")
        logger.debug("Prompt: %s", prompt)

        try:
            # Build codebase context
            codebase_context = await self._build_codebase_context()

            # Construct system and user prompts
            system_prompt = self._build_analysis_system_prompt()
            user_message = self._build_analysis_user_message(prompt, codebase_context)

            # Get response from Claude
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_message),
            ]

            response = await self.llm.ainvoke(messages)
            response_text = response.content

            # Parse JSON response
            result = self._parse_response(response_text)

            logger.info("Successfully generated %d file changes", len(result.get("changes", [])))
            return result

        except Exception as e:
            logger.error("Failed to analyze and generate changes: %s", e, exc_info=True)
            return {
                "success": False,
                "changes": [],
                "explanation": f"Error during analysis: {str(e)}",
                "branch_name": "",
                "commit_message": "",
                "pr_title": "",
                "pr_body": "",
            }

    async def _build_codebase_context(self) -> str:
        """
        Build context about codebase structure.

        Includes:
        - Directory structure
        - Key files (bot.py, config.py, llm_handler.py)
        - pyproject.toml
        - README.md

        Returns:
            Formatted codebase context string.
        """
        logger.debug("Building codebase context...")

        context_parts = []

        # 1. Directory structure
        context_parts.append("## Directory Structure")
        context_parts.append(self._get_directory_tree())

        # 2. Key files content
        key_files = [
            "src/bot.py",
            "src/config.py",
            "src/llm_handler.py",
            "pyproject.toml",
            "README.md",
        ]

        for file_path in key_files:
            full_path = self.repo_path / file_path
            if full_path.exists():
                content = self._read_file_safe(full_path)
                if content:
                    context_parts.append(f"\n## File: {file_path}")
                    context_parts.append(f"```\n{content}\n```")

        return "\n\n".join(context_parts)

    def _get_directory_tree(self) -> str:
        """Get directory tree structure."""
        tree_lines = ["```"]

        # Walk the directory structure
        for root, dirs, files in os.walk(self.repo_path):
            # Skip hidden and common ignored directories
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ["__pycache__", "node_modules", ".git"]]

            level = root.replace(str(self.repo_path), "").count(os.sep)
            indent = "  " * level
            rel_root = os.path.relpath(root, self.repo_path)
            if rel_root == ".":
                tree_lines.append(f"{self.repo_path.name}/")
            else:
                tree_lines.append(f"{indent}{os.path.basename(root)}/")

            sub_indent = "  " * (level + 1)
            for file in sorted(files):
                if not file.startswith("."):
                    tree_lines.append(f"{sub_indent}{file}")

        tree_lines.append("```")
        return "\n".join(tree_lines)

    def _read_file_safe(self, file_path: Path, max_lines: int = 500) -> str:
        """Safely read file content with size limit."""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
                if len(lines) > max_lines:
                    return "".join(lines[:max_lines]) + f"\n... (truncated, {len(lines)} total lines)"
                return "".join(lines)
        except Exception as e:
            logger.warning("Failed to read file %s: %s", file_path, e)
            return ""

    def _build_analysis_system_prompt(self) -> str:
        """Build system prompt for code analysis."""
        return """You are a senior software architect and Python expert. Your task is to analyze a codebase and generate code changes based on a user's improvement request.

Follow these principles:
1. **Understand existing patterns**: Study the codebase architecture before making changes
2. **Minimal changes**: Only modify what's necessary to fulfill the request
3. **Follow conventions**: Match existing code style, naming, and patterns
4. **Preserve functionality**: Don't break existing features
5. **Security first**: Never introduce vulnerabilities

You will receive:
- A description of the codebase structure and key files
- A specific improvement request from the user

You must respond with a valid JSON object (and ONLY JSON, no markdown code blocks) with this structure:
{
    "success": true/false,
    "changes": [
        {
            "file_path": "relative/path/to/file.py",
            "action": "create" | "modify" | "delete",
            "content": "full file content for create/modify actions"
        }
    ],
    "explanation": "Clear explanation of what was changed and why",
    "branch_name": "descriptive-branch-name",
    "commit_message": "Brief commit message (50 chars max)",
    "pr_title": "Pull request title",
    "pr_body": "Markdown-formatted PR description with:\n- Summary of changes\n- Reasoning\n- Testing notes"
}

Important constraints:
- For "modify" actions, provide the COMPLETE file content, not just diffs
- Branch names: lowercase, kebab-case, descriptive (e.g., "add-logging-to-mentions")
- If the request is unclear or impossible, set success=false and explain why
- Keep changes focused and atomic (one logical change per PR)
- Never remove or modify existing functionality unless explicitly requested"""

    def _build_analysis_user_message(self, prompt: str, codebase_context: str) -> str:
        """Build user message for code analysis."""
        return f"""# Codebase Context

{codebase_context}

# Improvement Request

{prompt}

# Your Task

Analyze the codebase and generate the necessary code changes to fulfill the improvement request.
Remember: Respond with ONLY the JSON object, no markdown code blocks or additional text."""

    def _parse_response(self, response_text: str) -> dict[str, Any]:
        """
        Parse Claude's JSON response.

        Args:
            response_text: Raw response from Claude.

        Returns:
            Parsed dict.

        Raises:
            ValueError: If JSON parsing fails.
        """
        # Remove markdown code blocks if present (Claude sometimes adds them)
        cleaned = response_text.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        if cleaned.startswith("```"):
            cleaned = cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()

        try:
            result = json.loads(cleaned)

            # Validate structure
            required_keys = ["success", "changes", "explanation", "branch_name", "commit_message", "pr_title", "pr_body"]
            for key in required_keys:
                if key not in result:
                    raise ValueError(f"Missing required key: {key}")

            return result
        except json.JSONDecodeError as e:
            logger.error("Failed to parse JSON response: %s", e)
            logger.debug("Response text: %s", response_text)
            raise ValueError(f"Invalid JSON response: {e}")

    async def apply_changes(self, changes: list[dict[str, Any]]) -> tuple[bool, str]:
        """
        Apply generated changes to filesystem.

        Args:
            changes: List of change dicts with file_path, action, content.

        Returns:
            (success, error_message).
        """
        logger.info("Applying %d file changes...", len(changes))

        try:
            for change in changes:
                file_path = self.repo_path / change["file_path"]
                action = change["action"]

                if action == "create" or action == "modify":
                    # Ensure parent directory exists
                    file_path.parent.mkdir(parents=True, exist_ok=True)

                    # Write content
                    with open(file_path, "w", encoding="utf-8") as f:
                        f.write(change["content"])

                    logger.debug("Wrote file: %s", file_path)

                elif action == "delete":
                    if file_path.exists():
                        file_path.unlink()
                        logger.debug("Deleted file: %s", file_path)
                    else:
                        logger.warning("Cannot delete non-existent file: %s", file_path)

                else:
                    logger.warning("Unknown action '%s' for file %s", action, file_path)

            logger.info("Successfully applied all changes")
            return (True, "")

        except Exception as e:
            error_msg = f"Failed to apply changes: {e}"
            logger.error(error_msg, exc_info=True)
            return (False, error_msg)

    async def validate_changes(self) -> tuple[bool, str]:
        """
        Validate applied changes.

        Checks:
        - Python syntax (AST compile)
        - No dangerous imports
        - File size limits

        Returns:
            (valid, error_message).
        """
        logger.info("Validating changes...")

        try:
            # Find all Python files in the repo
            for py_file in self.repo_path.rglob("*.py"):
                # Skip virtual environments and hidden directories
                if any(part.startswith(".") or part == "__pycache__" for part in py_file.parts):
                    continue

                # Check file size (< 10MB)
                if py_file.stat().st_size > 10 * 1024 * 1024:
                    return (False, f"File too large: {py_file} (>10MB)")

                # Check Python syntax
                try:
                    with open(py_file, "r", encoding="utf-8") as f:
                        code = f.read()
                    ast.parse(code)
                except SyntaxError as e:
                    return (False, f"Syntax error in {py_file}: {e}")

                # Check for dangerous imports (warning only)
                if re.search(r'\b(eval|exec)\s*\(', code):
                    logger.warning("Found potentially dangerous code in %s: eval/exec usage", py_file)

            logger.info("Validation passed")
            return (True, "")

        except Exception as e:
            error_msg = f"Validation failed: {e}"
            logger.error(error_msg, exc_info=True)
            return (False, error_msg)
