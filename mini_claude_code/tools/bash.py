"""
Bash tool — execute shell commands.
Maps to: src/tools/BashTool/BashTool.ts

Claude Code's BashTool is non-concurrent (affects shell state),
has sandbox restrictions, and validates commands. We keep it simple.
"""

import os
import subprocess

from . import ToolSpec


def run(inp: dict) -> str:
    cmd = inp.get("command", "")
    timeout = min(inp.get("timeout", 120), 600)
    description = inp.get("description", "")

    if not cmd.strip():
        return "Error: empty command"

    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=os.getcwd(),
            env={**os.environ},
        )
        output = ""
        if result.stdout:
            output += result.stdout
        if result.stderr:
            output += ("\n" if output else "") + result.stderr
        if result.returncode != 0:
            output += f"\n[exit code: {result.returncode}]"
        # Truncate very long output (Claude Code does this too)
        if len(output) > 100_000:
            half = 50_000
            output = (
                output[:half]
                + f"\n\n... [{len(output) - 2 * half} chars truncated] ...\n\n"
                + output[-half:]
            )
        return output or "(no output)"
    except subprocess.TimeoutExpired:
        return f"Error: command timed out after {timeout}s"
    except Exception as e:
        return f"Error: {e}"


spec = ToolSpec(
    name="Bash",
    description=(
        "Execute a shell command and return its output. "
        "Use for: running scripts, git operations, package management, builds, tests. "
        "Avoid interactive commands (vim, less, nano). "
        "Commands run in the current working directory."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "The shell command to execute",
            },
            "description": {
                "type": "string",
                "description": "Brief description of what this command does",
            },
            "timeout": {
                "type": "integer",
                "description": "Timeout in seconds (default 120, max 600)",
            },
        },
        "required": ["command"],
    },
    run=run,
)
