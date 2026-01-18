"""Systemd log search tool for analyzing service failures and system logs."""

import logging
import subprocess
from typing import Optional

from langchain_core.tools import tool

logger = logging.getLogger(__name__)


@tool
def search_systemd_logs(
    unit: Optional[str] = None,
    since: str = "1 hour ago",
    priority: Optional[str] = None,
    grep: Optional[str] = None,
    lines: int = 100
) -> str:
    """Search systemd journal logs for service failures and system events.

    This tool searches systemd logs using journalctl to help diagnose service
    failures, errors, and other system events. Useful for debugging the bot's
    own systemd service or investigating system-level issues.

    Args:
        unit: Service/unit name to filter logs (e.g., "atproto-bot.service", "nginx.service").
              If not specified, searches all system logs.
        since: Time period to search. Examples:
            - "1 hour ago" (default)
            - "2 hours ago"
            - "today"
            - "yesterday"
            - "2024-01-01"
            - "2024-01-01 10:00:00"
        priority: Minimum log priority level. Options:
            - "emerg" (0) - System is unusable
            - "alert" (1) - Action must be taken immediately
            - "crit" (2) - Critical conditions
            - "err" (3) - Error conditions
            - "warning" (4) - Warning conditions
            - "notice" (5) - Normal but significant
            - "info" (6) - Informational
            - "debug" (7) - Debug messages
        grep: Search term to filter log lines (case-insensitive)
        lines: Maximum number of log lines to return (default: 100, max: 1000)

    Returns:
        Formatted systemd log entries with timestamps, units, and messages.

    Examples:
        - search_systemd_logs(unit="atproto-bot.service", since="1 hour ago")
        - search_systemd_logs(priority="err", since="today")
        - search_systemd_logs(unit="nginx.service", grep="error", lines=50)
        - search_systemd_logs(since="2024-01-18 10:00:00", priority="warning")
    """
    # Validate and constrain parameters
    lines = max(1, min(lines, 1000))

    valid_priorities = ["emerg", "alert", "crit", "err", "warning", "notice", "info", "debug"]
    if priority and priority not in valid_priorities:
        return f"Error: Invalid priority '{priority}'. Must be one of: {', '.join(valid_priorities)}"

    # Build journalctl command
    cmd = ["journalctl", "--no-pager", "-n", str(lines), "--since", since]

    if unit:
        cmd.extend(["-u", unit])

    if priority:
        cmd.extend(["-p", priority])

    if grep:
        cmd.extend(["--grep", grep, "-i"])  # -i for case-insensitive

    # Add output format for better parsing
    cmd.append("--output=short-precise")

    try:
        logger.info(f"Running journalctl command: {' '.join(cmd)}")

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
            check=False
        )

        # Check for errors
        if result.returncode != 0:
            error_msg = result.stderr.strip()
            if "No journal files were found" in error_msg:
                return "No journal logs found. This may be a permissions issue or systemd logging is not available."
            elif "Failed to determine unit" in error_msg:
                return f"Error: Unit '{unit}' not found. Use 'systemctl list-units' to see available units."
            elif "Specifying boot ID" in error_msg or "Unknown time specification" in error_msg:
                return f"Error: Invalid time specification '{since}'. Examples: '1 hour ago', 'today', '2024-01-18'"
            else:
                return f"Error running journalctl: {error_msg or 'Unknown error'}"

        output = result.stdout.strip()

        if not output:
            filter_info = []
            if unit:
                filter_info.append(f"unit={unit}")
            if priority:
                filter_info.append(f"priority={priority}")
            if grep:
                filter_info.append(f"grep='{grep}'")

            filters = ", ".join(filter_info) if filter_info else "no filters"
            return f"No logs found for the specified criteria (since='{since}', {filters})"

        # Format output with header
        header = "=== Systemd Journal Logs ===\n"
        header += f"Time period: Since {since}\n"
        if unit:
            header += f"Unit: {unit}\n"
        if priority:
            header += f"Priority: {priority} and higher\n"
        if grep:
            header += f"Filter: '{grep}'\n"
        header += f"Lines: {lines}\n"
        header += "=" * 50 + "\n\n"

        # Count log lines and provide summary
        log_lines = output.split('\n')
        actual_count = len(log_lines)

        footer = f"\n\n{'=' * 50}\n"
        footer += f"Total lines: {actual_count}\n"

        if actual_count >= lines:
            footer += f"Note: Output limited to {lines} lines. Use a larger 'lines' parameter or narrow your search to see more.\n"

        return header + output + footer

    except subprocess.TimeoutExpired:
        return "Error: journalctl command timed out (>30s). Try narrowing your search with more specific filters."
    except FileNotFoundError:
        return "Error: journalctl command not found. systemd logging may not be available on this system."
    except Exception as e:
        logger.error(f"Error searching systemd logs: {e}", exc_info=True)
        return f"Error searching systemd logs: {str(e)}"
