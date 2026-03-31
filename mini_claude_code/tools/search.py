"""
Search tools: Glob and Grep.
Maps to: src/tools/GlobTool/, src/tools/GrepTool/
"""

import os
import re
import subprocess
from pathlib import Path

from . import ToolSpec


# ============================================================================
# Glob Tool — src/tools/GlobTool/GlobTool.ts
# ============================================================================

def run_glob(inp: dict) -> str:
    pattern = inp.get("pattern", "")
    search_path = inp.get("path", os.getcwd())

    if not pattern:
        return "Error: pattern is required"

    try:
        base = Path(search_path).resolve()
        if not base.exists():
            return f"Error: path does not exist: {search_path}"

        # Use pathlib's glob (supports **)
        matches = sorted(str(m) for m in base.glob(pattern) if m.is_file())

        if not matches:
            return "No files matched the pattern."

        shown = matches[:300]
        result = "\n".join(shown)
        if len(matches) > 300:
            result += f"\n\n... and {len(matches) - 300} more files"
        return result
    except Exception as e:
        return f"Error: {e}"


glob_spec = ToolSpec(
    name="Glob",
    description=(
        "Find files by glob pattern. Supports ** for recursive matching. "
        "Returns matching file paths sorted alphabetically. "
        "Examples: '**/*.py', 'src/**/*.ts', '*.json'"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "Glob pattern (e.g. '**/*.py', 'src/**/*.ts')",
            },
            "path": {
                "type": "string",
                "description": "Directory to search in (default: CWD)",
            },
        },
        "required": ["pattern"],
    },
    run=run_glob,
)


# ============================================================================
# Grep Tool — src/tools/GrepTool/GrepTool.ts
# Uses ripgrep if available, falls back to pure Python.
# ============================================================================

def run_grep(inp: dict) -> str:
    pattern = inp.get("pattern", "")
    search_path = inp.get("path", os.getcwd())
    include = inp.get("include", "")
    max_results = inp.get("max_results", 100)

    if not pattern:
        return "Error: pattern is required"

    # Try ripgrep first (matches real Claude Code behavior)
    try:
        return _grep_ripgrep(pattern, search_path, include, max_results)
    except FileNotFoundError:
        return _grep_python(pattern, search_path, include, max_results)


def _grep_ripgrep(pattern: str, path: str, include: str, max_results: int) -> str:
    """Use ripgrep for fast searching."""
    cmd = ["rg", "--no-heading", "-n", f"--max-count={max_results}"]
    if include:
        cmd.extend(["--glob", include])
    cmd.extend(["--", pattern, path])

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    output = result.stdout

    if not output and result.returncode == 1:
        return "No matches found."
    if result.returncode == 2:
        return f"Error: {result.stderr}"

    # Truncate if very long
    if len(output) > 100_000:
        lines = output.splitlines()
        output = "\n".join(lines[:max_results])
        output += f"\n\n(truncated at {max_results} matches)"
    return output or "No matches found."


def _grep_python(pattern: str, search_path: str, include: str, max_results: int) -> str:
    """Pure Python fallback grep."""
    try:
        regex = re.compile(pattern)
    except re.error as e:
        return f"Invalid regex pattern: {e}"

    results = []
    search = Path(search_path)

    # Determine files to search
    if search.is_file():
        files = [search]
    else:
        glob_pat = include if include else "**/*"
        files = search.glob(glob_pat)

    for fp in files:
        if not fp.is_file():
            continue
        # Skip binary / very large files
        try:
            if fp.stat().st_size > 2_000_000:
                continue
        except OSError:
            continue

        try:
            text = fp.read_text(encoding="utf-8", errors="replace")
            for i, line in enumerate(text.splitlines(), 1):
                if regex.search(line):
                    results.append(f"{fp}:{i}:{line}")
                    if len(results) >= max_results:
                        return "\n".join(results) + f"\n\n(truncated at {max_results} matches)"
        except Exception:
            continue

    return "\n".join(results) if results else "No matches found."


grep_spec = ToolSpec(
    name="Grep",
    description=(
        "Search file contents using regex patterns. Uses ripgrep if available, "
        "falls back to Python regex. Returns matching lines with file paths and line numbers."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "Regular expression pattern to search for",
            },
            "path": {
                "type": "string",
                "description": "File or directory to search (default: CWD)",
            },
            "include": {
                "type": "string",
                "description": "Glob pattern to filter files (e.g. '*.py', '*.ts')",
            },
        },
        "required": ["pattern"],
    },
    run=run_grep,
)
