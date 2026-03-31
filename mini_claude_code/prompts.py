"""
System prompt builder.
Maps to: src/constants/prompts.ts, src/constants/system.ts

Claude Code's system prompt is assembled from:
  1. Static blocks (cacheable) — role, tool instructions, coding guidelines
  2. Dynamic boundary marker
  3. Dynamic blocks (per-request) — CWD, date, CLAUDE.md, project context
"""

import os
import sys
from datetime import datetime
from pathlib import Path


def build_system_prompt(cwd: str) -> str:
    """
    Assemble the full system prompt.
    Mirrors buildSystemPromptBlocks() in src/constants/prompts.ts.
    """
    sections = [
        _role_prefix(),
        _tool_guidelines(),
        _coding_guidelines(),
        _task_execution_guidelines(),
        _environment_context(cwd),
        _load_claude_md(cwd),
    ]
    return "\n\n".join(s for s in sections if s)


# ---- Section builders (each mirrors a block in prompts.ts) ----

def _role_prefix() -> str:
    """From src/constants/system.ts line 10: DEFAULT_PREFIX"""
    return (
        "You are Mini Claude Code, an AI coding assistant that operates in the terminal. "
        "You have access to tools for reading, writing, searching files and running shell commands. "
        "You can use these tools to explore codebases, write code, fix bugs, and complete tasks.\n"
        "Use tools proactively — don't ask for permission, just act."
    )


def _tool_guidelines() -> str:
    """
    From the 'Using tools' section of prompts.ts (~200 lines).
    Distilled to the essential rules that actually affect behavior.
    """
    return """## Tool Usage Guidelines

**Bash tool:**
- Run shell commands for building, testing, git, package management, etc.
- NEVER use interactive commands (vim, less, nano) — they hang
- Prefer dedicated tools over bash equivalents: use Read not `cat`, Glob not `find`, Grep not `grep`
- Quote file paths with spaces
- Chain sequential commands with `&&`
- For long-running commands, add a timeout

**File tools:**
- ALWAYS Read a file before Editing it
- Use Edit for surgical changes (preferred). Use Write only for new files or complete rewrites
- Edit will fail if old_string is not unique — provide more context or use replace_all
- Prefer editing existing files over creating new ones

**Search tools:**
- Use Glob to find files by name pattern (e.g. `**/*.py`)
- Use Grep to search file contents with regex
- Call multiple independent search tools in parallel

**General:**
- You can make multiple tool calls in a single response when they are independent
- Always verify your changes work (run tests, check for errors)
- Don't leave TODO/placeholder comments — implement fully"""


def _coding_guidelines() -> str:
    """
    From the 'Doing tasks' section of prompts.ts.
    Key coding style and investigation rules.
    """
    return """## Coding Guidelines

**Before writing code:**
- Read relevant files and understand the existing patterns
- Check for existing similar implementations to reuse
- Understand the project's style (naming, formatting, structure)

**When writing code:**
- Follow the project's existing code style exactly
- Use existing libraries and patterns from the project
- Write clean, readable code — don't over-engineer
- Handle errors properly
- Add comments only when the code isn't self-explanatory

**After writing code:**
- Run existing tests if available
- Verify the change works as expected
- Check for regressions

**Git commits (only when asked):**
- Use concise, descriptive commit messages
- Stage specific files, not `git add .`
- Never force push or amend without being asked"""


def _task_execution_guidelines() -> str:
    """
    From the 'Executing actions' section of prompts.ts.
    Rules about blast radius and thoroughness.
    """
    return """## Task Execution

- Make the smallest change that solves the problem
- Don't refactor unrelated code unless asked
- If a task is ambiguous, make a reasonable choice and proceed
- When completing tasks, give a concise summary of what was done
- If something fails, investigate the root cause before retrying"""


def _environment_context(cwd: str) -> str:
    """Dynamic context block — from the 'Environment' section of prompts.ts."""
    return f"""## Environment

- Working directory: {cwd}
- Platform: {sys.platform}
- Date: {datetime.now().strftime('%Y-%m-%d')}
- Python: {sys.version.split()[0]}
- Shell: {os.environ.get('SHELL', 'unknown')}"""


def _load_claude_md(cwd: str) -> str:
    """
    Load CLAUDE.md project memory files.
    Maps to: src/utils/claudemd.ts

    Search order (same as real Claude Code):
      1. CLAUDE.md in project root
      2. .claude/CLAUDE.md
      3. .claude/rules/*.md
      4. ~/.mini-claude-code/CLAUDE.md (global user memory)
    """
    parts = []

    # Project-level files
    search_paths = [
        (os.path.join(cwd, "CLAUDE.md"), "Project Memory (CLAUDE.md)"),
        (os.path.join(cwd, ".claude", "CLAUDE.md"), "Project Memory (.claude/CLAUDE.md)"),
    ]

    for path, label in search_paths:
        content = _safe_read(path, max_chars=8000)
        if content:
            parts.append(f"## {label}\n\n{content}")

    # .claude/rules/*.md files
    rules_dir = os.path.join(cwd, ".claude", "rules")
    if os.path.isdir(rules_dir):
        for md_file in sorted(Path(rules_dir).glob("*.md")):
            content = _safe_read(str(md_file), max_chars=4000)
            if content:
                parts.append(f"## Project Rule ({md_file.name})\n\n{content}")

    # Global user memory
    home_md = os.path.join(
        os.environ.get("MINI_CC_CONFIG_DIR", os.path.join(Path.home(), ".mini-claude-code")),
        "CLAUDE.md",
    )
    content = _safe_read(home_md, max_chars=4000)
    if content:
        parts.append(f"## User Memory (global CLAUDE.md)\n\n{content}")

    return "\n\n".join(parts) if parts else ""


def _safe_read(path: str, max_chars: int = 8000) -> str:
    """Read a file safely, returning empty string on any error."""
    try:
        if os.path.isfile(path):
            return Path(path).read_text(encoding="utf-8", errors="replace")[:max_chars]
    except Exception:
        pass
    return ""
