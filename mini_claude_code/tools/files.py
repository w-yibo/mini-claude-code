"""
File tools: Read, Write, Edit.
Maps to: src/tools/ReadTool/, src/tools/WriteTool/, src/tools/EditTool/
"""

import os
from pathlib import Path

from . import ToolSpec


# ============================================================================
# Read Tool — src/tools/ReadTool/ReadTool.ts
# ============================================================================

def run_read(inp: dict) -> str:
    file_path = inp.get("file_path", "")
    offset = inp.get("offset", 0)
    limit = inp.get("limit", 0)

    if not file_path:
        return "Error: file_path is required"

    try:
        path = Path(file_path).expanduser().resolve()
        if not path.exists():
            return f"Error: file not found: {file_path}"
        if path.is_dir():
            return f"Error: {file_path} is a directory. Use Bash with 'ls' to list contents."

        # Check file size (don't read huge binary files)
        size = path.stat().st_size
        if size > 5_000_000:
            return f"Error: file too large ({size:,} bytes). Use offset/limit or Bash."

        text = path.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()

        # Apply offset and limit (1-based offset, like Claude Code)
        start = max(0, offset - 1) if offset > 0 else 0
        end = (start + limit) if limit > 0 else len(lines)
        selected = lines[start:end]

        # cat -n format (same as real Claude Code)
        numbered = [f"{i + start + 1:>6}\t{line}" for i, line in enumerate(selected)]
        return "\n".join(numbered) if numbered else "(empty file)"
    except UnicodeDecodeError:
        return f"Error: {file_path} appears to be a binary file"
    except Exception as e:
        return f"Error reading {file_path}: {e}"


read_spec = ToolSpec(
    name="Read",
    description=(
        "Read a file's contents with line numbers. "
        "Supports optional offset (1-based line number) and limit parameters for large files. "
        "Returns content in 'cat -n' format."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "file_path": {"type": "string", "description": "Absolute path to the file"},
            "offset": {"type": "integer", "description": "Start reading from this line (1-based)"},
            "limit": {"type": "integer", "description": "Maximum number of lines to read"},
        },
        "required": ["file_path"],
    },
    run=run_read,
)


# ============================================================================
# Write Tool — src/tools/WriteTool/WriteTool.ts
# ============================================================================

def run_write(inp: dict) -> str:
    file_path = inp.get("file_path", "")
    content = inp.get("content", "")

    if not file_path:
        return "Error: file_path is required"

    try:
        path = Path(file_path).expanduser().resolve()
        is_new = not path.exists()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        lines = content.count("\n") + (1 if content and not content.endswith("\n") else 0)
        action = "Created" if is_new else "Wrote"
        return f"{action} {lines} lines to {file_path}"
    except Exception as e:
        return f"Error writing {file_path}: {e}"


write_spec = ToolSpec(
    name="Write",
    description=(
        "Create a new file or completely overwrite an existing file. "
        "Creates parent directories if they don't exist. "
        "Prefer Edit for modifying existing files — only use Write for new files or complete rewrites."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "file_path": {"type": "string", "description": "Absolute path to the file"},
            "content": {"type": "string", "description": "The full content to write"},
        },
        "required": ["file_path", "content"],
    },
    run=run_write,
)


# ============================================================================
# Edit Tool — src/tools/EditTool/EditTool.ts
# ============================================================================

def run_edit(inp: dict) -> str:
    file_path = inp.get("file_path", "")
    old_string = inp.get("old_string", "")
    new_string = inp.get("new_string", "")
    replace_all = inp.get("replace_all", False)

    if not file_path:
        return "Error: file_path is required"
    if not old_string:
        return "Error: old_string is required"
    if old_string == new_string:
        return "Error: old_string and new_string are identical"

    try:
        path = Path(file_path).expanduser().resolve()
        if not path.exists():
            return f"Error: file not found: {file_path}"

        text = path.read_text(encoding="utf-8")
        count = text.count(old_string)

        if count == 0:
            # Helpful error with context (like Claude Code)
            return (
                f"Error: old_string not found in {file_path}. "
                "Make sure you've read the file first and the string matches exactly "
                "(including whitespace and indentation)."
            )
        if count > 1 and not replace_all:
            return (
                f"Error: old_string appears {count} times in {file_path}. "
                "Provide more surrounding context to make it unique, or set replace_all=true."
            )

        if replace_all:
            new_text = text.replace(old_string, new_string)
        else:
            new_text = text.replace(old_string, new_string, 1)

        path.write_text(new_text, encoding="utf-8")
        return f"Edited {file_path} ({count} replacement{'s' if count > 1 else ''})"
    except Exception as e:
        return f"Error editing {file_path}: {e}"


edit_spec = ToolSpec(
    name="Edit",
    description=(
        "Make exact string replacements in a file. "
        "You MUST read the file first before editing. "
        "Fails if old_string is not unique — provide more context or use replace_all. "
        "Preserves indentation — match the exact whitespace in the file."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "file_path": {"type": "string", "description": "Absolute path to the file"},
            "old_string": {"type": "string", "description": "The exact text to find and replace"},
            "new_string": {"type": "string", "description": "The replacement text"},
            "replace_all": {
                "type": "boolean",
                "description": "Replace all occurrences (default false)",
                "default": False,
            },
        },
        "required": ["file_path", "old_string", "new_string"],
    },
    run=run_edit,
)
