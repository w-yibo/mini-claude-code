#!/usr/bin/env python3
"""
mini-claude-code: A minimal Python re-implementation of Claude Code's core agent loop.

Architecture (mirrors the real Claude Code):
  User Input → System Prompt + Tools → Anthropic API → Tool Calls → Execute → Feed Back → Loop

Original Claude Code: ~500k LOC TypeScript
This file: ~600 LOC Python — same core loop, same tool design, zero bloat.
"""

import os
import sys
import re
import glob as glob_module
import json
import subprocess
import fnmatch
from pathlib import Path
from datetime import datetime
from typing import Any

import anthropic

# ============================================================================
# Configuration
# ============================================================================

MODEL = os.environ.get("MINI_CC_MODEL", "claude-sonnet-4-20250514")
MAX_TOKENS = int(os.environ.get("MINI_CC_MAX_TOKENS", "16384"))
MAX_TURNS = int(os.environ.get("MINI_CC_MAX_TURNS", "50"))

# ============================================================================
# Color helpers (no dependency needed)
# ============================================================================

def _c(code: str, text: str) -> str:
    if not sys.stdout.isatty():
        return text
    return f"\033[{code}m{text}\033[0m"

def dim(t: str) -> str: return _c("2", t)
def green(t: str) -> str: return _c("32", t)
def yellow(t: str) -> str: return _c("33", t)
def red(t: str) -> str: return _c("31", t)
def cyan(t: str) -> str: return _c("36", t)
def bold(t: str) -> str: return _c("1", t)
def magenta(t: str) -> str: return _c("35", t)

# ============================================================================
# System Prompt  (simplified from src/constants/system.ts + prompts.ts)
# ============================================================================

def build_system_prompt(cwd: str) -> str:
    """
    Claude Code 的 system prompt 由以下部分拼接:
    1. 角色定义 (DEFAULT_PREFIX)
    2. 工具使用指南
    3. 环境上下文 (CWD, OS, date)
    4. CLAUDE.md 项目记忆 (如果存在)
    """
    parts = []

    # 1. Role prefix — from src/constants/system.ts line 10
    parts.append(
        "You are Mini Claude Code, a lightweight AI coding assistant that operates in the terminal. "
        "You have access to tools for reading, writing, searching files and running shell commands. "
        "Use them proactively to explore the codebase and complete tasks."
    )

    # 2. Tool usage guidelines — extracted from prompts.ts
    parts.append("""
## Tool Usage Guidelines

- Use Bash for shell commands. Avoid interactive commands (vim, less, etc.)
- Use Read to view file contents before editing
- Use Edit for surgical changes to existing files (preferred over Write for modifications)
- Use Write only to create new files or complete rewrites
- Use Glob to find files by name pattern
- Use Grep to search file contents
- You can call multiple tools in parallel when they are independent
- Always read a file before editing it
- For code changes: implement fully, don't leave TODOs or placeholders

## Response Style

- Be concise and direct
- When completing tasks, report what was done
- Don't ask for permission — just use the tools
- If a task is ambiguous, make a reasonable choice and proceed
""")

    # 3. Environment context — from the dynamic block in prompts.ts
    parts.append(f"""
## Environment

- Working directory: {cwd}
- Platform: {sys.platform}
- Date: {datetime.now().strftime('%Y-%m-%d')}
- Python: {sys.version.split()[0]}
""")

    # 4. CLAUDE.md memory — from src/utils/claudemd.ts
    for md_name in ["CLAUDE.md", ".claude/CLAUDE.md"]:
        md_path = os.path.join(cwd, md_name)
        if os.path.isfile(md_path):
            try:
                content = Path(md_path).read_text(encoding="utf-8")[:4000]
                parts.append(f"\n## Project Memory ({md_name})\n\n{content}")
            except Exception:
                pass

    return "\n".join(parts)

# ============================================================================
# Tool Definitions  (mirrors src/tools/*.ts)
#
# Each tool: name, description, input_schema, run(input) → str
# Directly modeled after Claude Code's Tool interface:
#   { name, description, inputSchema, run() }
# ============================================================================

def tool_bash(inp: dict) -> str:
    """From src/tools/BashTool/ — execute shell commands."""
    cmd = inp.get("command", "")
    timeout = min(inp.get("timeout", 120), 600)
    if not cmd.strip():
        return "Error: empty command"
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True,
            timeout=timeout, cwd=os.getcwd(),
        )
        output = ""
        if result.stdout:
            output += result.stdout
        if result.stderr:
            output += ("\n" if output else "") + result.stderr
        if result.returncode != 0:
            output += f"\n[exit code: {result.returncode}]"
        return output[:100_000] or "(no output)"
    except subprocess.TimeoutExpired:
        return f"Error: command timed out after {timeout}s"
    except Exception as e:
        return f"Error: {e}"


def tool_read(inp: dict) -> str:
    """From src/tools/ReadTool/ — read file with optional offset/limit."""
    file_path = inp.get("file_path", "")
    offset = inp.get("offset", 0)  # 1-based line number
    limit = inp.get("limit", 0)
    if not file_path:
        return "Error: file_path is required"
    try:
        path = Path(file_path).expanduser()
        if not path.exists():
            return f"Error: file not found: {file_path}"
        if path.is_dir():
            return f"Error: {file_path} is a directory, not a file"
        text = path.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()
        start = max(0, offset - 1) if offset > 0 else 0
        end = start + limit if limit > 0 else len(lines)
        selected = lines[start:end]
        # cat -n format (same as Claude Code)
        numbered = [f"{i + start + 1:>6}\t{line}" for i, line in enumerate(selected)]
        return "\n".join(numbered) if numbered else "(empty file)"
    except Exception as e:
        return f"Error reading {file_path}: {e}"


def tool_write(inp: dict) -> str:
    """From src/tools/WriteTool/ — write/create file."""
    file_path = inp.get("file_path", "")
    content = inp.get("content", "")
    if not file_path:
        return "Error: file_path is required"
    try:
        path = Path(file_path).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        lines = content.count("\n") + (1 if content and not content.endswith("\n") else 0)
        return f"Successfully wrote {lines} lines to {file_path}"
    except Exception as e:
        return f"Error writing {file_path}: {e}"


def tool_edit(inp: dict) -> str:
    """From src/tools/EditTool/ — exact string replacement in files."""
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
        path = Path(file_path).expanduser()
        if not path.exists():
            return f"Error: file not found: {file_path}"
        text = path.read_text(encoding="utf-8")
        count = text.count(old_string)
        if count == 0:
            return f"Error: old_string not found in {file_path}"
        if count > 1 and not replace_all:
            return f"Error: old_string appears {count} times. Use replace_all=true or provide more context to make it unique."
        if replace_all:
            new_text = text.replace(old_string, new_string)
        else:
            new_text = text.replace(old_string, new_string, 1)
        path.write_text(new_text, encoding="utf-8")
        return f"Successfully edited {file_path} ({count} replacement{'s' if count > 1 else ''})"
    except Exception as e:
        return f"Error editing {file_path}: {e}"


def tool_glob(inp: dict) -> str:
    """From src/tools/GlobTool/ — find files by pattern."""
    pattern = inp.get("pattern", "")
    search_path = inp.get("path", os.getcwd())
    if not pattern:
        return "Error: pattern is required"
    try:
        full_pattern = os.path.join(search_path, pattern)
        matches = sorted(glob_module.glob(full_pattern, recursive=True))
        # Filter out directories, keep files only
        files = [m for m in matches if os.path.isfile(m)]
        if not files:
            return "No files matched the pattern."
        # Limit output
        shown = files[:200]
        result = "\n".join(shown)
        if len(files) > 200:
            result += f"\n... and {len(files) - 200} more files"
        return result
    except Exception as e:
        return f"Error: {e}"


def tool_grep(inp: dict) -> str:
    """From src/tools/GrepTool/ — search file contents with regex (uses ripgrep or fallback)."""
    pattern = inp.get("pattern", "")
    search_path = inp.get("path", os.getcwd())
    include = inp.get("include", "")
    if not pattern:
        return "Error: pattern is required"
    try:
        # Try ripgrep first (much faster), fall back to grep
        cmd = ["rg", "--no-heading", "-n", "--max-count=100"]
        if include:
            cmd.extend(["--glob", include])
        cmd.extend([pattern, search_path])
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        output = result.stdout
        if not output and result.returncode == 1:
            return "No matches found."
        return output[:100_000] if output else "No matches found."
    except FileNotFoundError:
        # ripgrep not available, use Python fallback
        return _grep_python_fallback(pattern, search_path, include)
    except Exception as e:
        return f"Error: {e}"


def _grep_python_fallback(pattern: str, search_path: str, include: str) -> str:
    """Pure Python grep fallback when ripgrep is not installed."""
    results = []
    try:
        regex = re.compile(pattern)
    except re.error as e:
        return f"Invalid regex: {e}"
    search = Path(search_path)
    files = search.rglob(include if include else "*") if search.is_dir() else [search]
    for fp in files:
        if not fp.is_file():
            continue
        try:
            for i, line in enumerate(fp.read_text(errors="replace").splitlines(), 1):
                if regex.search(line):
                    results.append(f"{fp}:{i}:{line}")
                    if len(results) >= 100:
                        return "\n".join(results) + "\n(truncated at 100 matches)"
        except Exception:
            continue
    return "\n".join(results) if results else "No matches found."


# ============================================================================
# Tool Registry  (mirrors src/tools.ts → getTools())
# ============================================================================

TOOLS = {
    "Bash": {
        "description": "Execute a shell command. Use for running scripts, git commands, installing packages, etc.",
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "The shell command to execute"},
                "timeout": {"type": "integer", "description": "Timeout in seconds (max 600)", "default": 120},
            },
            "required": ["command"],
        },
        "run": tool_bash,
    },
    "Read": {
        "description": "Read a file's contents. Returns lines with line numbers.",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Absolute path to the file"},
                "offset": {"type": "integer", "description": "Start line (1-based)", "default": 0},
                "limit": {"type": "integer", "description": "Max lines to read", "default": 0},
            },
            "required": ["file_path"],
        },
        "run": tool_read,
    },
    "Write": {
        "description": "Write content to a file. Creates parent directories if needed.",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Absolute path to the file"},
                "content": {"type": "string", "description": "The content to write"},
            },
            "required": ["file_path", "content"],
        },
        "run": tool_write,
    },
    "Edit": {
        "description": "Make exact string replacements in a file. Must read the file first.",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Absolute path to the file"},
                "old_string": {"type": "string", "description": "The exact text to find"},
                "new_string": {"type": "string", "description": "The replacement text"},
                "replace_all": {"type": "boolean", "description": "Replace all occurrences", "default": False},
            },
            "required": ["file_path", "old_string", "new_string"],
        },
        "run": tool_edit,
    },
    "Glob": {
        "description": "Find files by glob pattern. Supports ** for recursive matching.",
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Glob pattern (e.g. '**/*.py')"},
                "path": {"type": "string", "description": "Directory to search in"},
            },
            "required": ["pattern"],
        },
        "run": tool_glob,
    },
    "Grep": {
        "description": "Search file contents using regex. Uses ripgrep if available.",
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Regex pattern to search for"},
                "path": {"type": "string", "description": "File or directory to search"},
                "include": {"type": "string", "description": "File glob filter (e.g. '*.py')"},
            },
            "required": ["pattern"],
        },
        "run": tool_grep,
    },
}

def get_tool_definitions() -> list[dict]:
    """Convert our tools to Anthropic API format — mirrors getTools() in src/tools.ts"""
    return [
        {
            "name": name,
            "description": spec["description"],
            "input_schema": spec["input_schema"],
        }
        for name, spec in TOOLS.items()
    ]

# ============================================================================
# Core Agent Loop  (mirrors src/query.ts → queryLoop())
#
# The REAL Claude Code loop:
#   1. Send messages + tools to API
#   2. If response has tool_use blocks → execute tools → append tool_results → goto 1
#   3. If response is text only → done, show to user
# ============================================================================

class AgentLoop:
    """
    The core agent loop — the heart of Claude Code.

    Simplified from src/query.ts's queryLoop():
    - Original: streaming + concurrent tool execution + auto-compact + error recovery
    - This: synchronous + sequential tools + simple context management
    """

    def __init__(self):
        self.client = anthropic.Anthropic()  # Uses ANTHROPIC_API_KEY env var
        self.messages: list[dict] = []
        self.system_prompt = build_system_prompt(os.getcwd())
        self.tools = get_tool_definitions()
        self.total_tokens = 0
        self.total_cost = 0.0
        self.turn_count = 0

    def run_turn(self, user_input: str) -> str:
        """
        Process one user turn through the full agent loop.

        This is the Python equivalent of queryLoop() in src/query.ts:
          while (true) {
            response = await queryModelWithStreaming(state)
            if (no tool_use) return response
            execute tools, append results, continue
          }
        """
        # Add user message
        self.messages.append({"role": "user", "content": user_input})

        while True:
            self.turn_count += 1
            if self.turn_count > MAX_TURNS:
                return red(f"[Reached max turns ({MAX_TURNS}). Stopping.]")

            # ---- Step 1: Call the API (mirrors queryModelWithStreaming) ----
            try:
                response = self._call_api()
            except anthropic.APIError as e:
                return red(f"API Error: {e}")

            # ---- Step 2: Process response ----
            assistant_content = response.content
            self.messages.append({"role": "assistant", "content": assistant_content})

            # Track usage
            if response.usage:
                self.total_tokens += response.usage.input_tokens + response.usage.output_tokens

            # ---- Step 3: Check for tool calls ----
            tool_uses = [b for b in assistant_content if b.type == "tool_use"]

            if not tool_uses:
                # No tools → extract text and return (Terminal state in Claude Code)
                text_parts = [b.text for b in assistant_content if hasattr(b, "text")]
                return "\n".join(text_parts)

            # ---- Step 4: Execute tools & collect results ----
            # (mirrors StreamingToolExecutor in src/query.ts)
            tool_results = []
            for tool_use in tool_uses:
                result = self._execute_tool(tool_use)
                tool_results.append(result)

            # ---- Step 5: Append tool results and loop ----
            # (mirrors the tool_result message in src/utils/messages.ts)
            self.messages.append({"role": "user", "content": tool_results})

            # Continue the loop (goto Step 1)

    def _call_api(self) -> Any:
        """Call Anthropic API — mirrors src/services/api/claude.ts"""
        return self.client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=self.system_prompt,
            tools=self.tools,
            messages=self.messages,
        )

    def _execute_tool(self, tool_use) -> dict:
        """
        Execute a single tool call — mirrors the tool execution in query.ts.

        In real Claude Code, this goes through:
          tool.checkPermissions() → tool.run() → collect output
        We skip permissions (no security = mini version).
        """
        name = tool_use.name
        inp = tool_use.input
        tool_id = tool_use.id

        spec = TOOLS.get(name)
        if not spec:
            self._print_tool_error(name, "unknown tool")
            return {
                "type": "tool_result",
                "tool_use_id": tool_id,
                "content": f"Error: unknown tool '{name}'",
                "is_error": True,
            }

        # Print what we're doing
        self._print_tool_call(name, inp)

        # Run the tool
        try:
            output = spec["run"](inp)
        except Exception as e:
            output = f"Error: {e}"

        # Print result summary
        self._print_tool_result(name, output)

        return {
            "type": "tool_result",
            "tool_use_id": tool_id,
            "content": output,
        }

    # ---- Display helpers ----

    def _print_tool_call(self, name: str, inp: dict):
        """Show tool invocation — like Claude Code's Ink UI but in plain text."""
        if name == "Bash":
            print(f"\n  {cyan('$')} {inp.get('command', '')}")
        elif name == "Read":
            print(f"\n  {cyan('📖')} Read {inp.get('file_path', '')}")
        elif name == "Write":
            path = inp.get("file_path", "")
            print(f"\n  {cyan('✏️')} Write {path}")
        elif name == "Edit":
            path = inp.get("file_path", "")
            print(f"\n  {cyan('🔧')} Edit {path}")
        elif name == "Glob":
            print(f"\n  {cyan('🔍')} Glob {inp.get('pattern', '')}")
        elif name == "Grep":
            print(f"\n  {cyan('🔎')} Grep {inp.get('pattern', '')} ")
        else:
            print(f"\n  {cyan('⚙️')} {name}({json.dumps(inp, ensure_ascii=False)[:100]})")

    def _print_tool_result(self, name: str, output: str):
        """Show truncated tool output."""
        lines = output.strip().splitlines()
        max_show = 15
        for line in lines[:max_show]:
            print(f"  {dim(line[:200])}")
        if len(lines) > max_show:
            print(f"  {dim(f'... ({len(lines) - max_show} more lines)')}")

# ============================================================================
# REPL  (mirrors src/replLauncher.tsx + src/screens/REPL/)
# ============================================================================

BANNER = f"""
{bold(cyan('╔══════════════════════════════════════════╗'))}
{bold(cyan('║'))}   {bold('Mini Claude Code')}  {dim('— Python Edition')}    {bold(cyan('║'))}
{bold(cyan('╚══════════════════════════════════════════╝'))}

  {dim(f'Model: {MODEL}')}
  {dim(f'CWD:   {os.getcwd()}')}
  {dim('Type /help for commands, Ctrl+C to exit')}
"""

HELP_TEXT = f"""
  {bold('Commands:')}
    {cyan('/help')}     Show this help
    {cyan('/clear')}    Clear conversation history
    {cyan('/cost')}     Show token usage
    {cyan('/model')}    Show/change model
    {cyan('/quit')}     Exit

  {bold('Tips:')}
    - Just describe what you want in natural language
    - The agent will use tools automatically
    - Multi-line input: end a line with \\ to continue
"""


def read_multiline_input() -> str:
    """Read input, supporting \\ for line continuation."""
    lines = []
    prompt = green(bold("You: "))
    while True:
        try:
            line = input(prompt)
        except EOFError:
            if lines:
                break
            raise
        if line.endswith("\\"):
            lines.append(line[:-1])
            prompt = green("...  ")
        else:
            lines.append(line)
            break
    return "\n".join(lines)


def main():
    print(BANNER)

    # Check for API key
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print(red("  Error: ANTHROPIC_API_KEY environment variable not set."))
        print(dim("  Get one at https://console.anthropic.com/settings/keys"))
        sys.exit(1)

    agent = AgentLoop()

    # Handle initial prompt from -p flag
    if len(sys.argv) > 1:
        if sys.argv[1] in ("-p", "--prompt"):
            prompt = " ".join(sys.argv[2:])
            if prompt:
                print(f"{green(bold('You:'))} {prompt}")
                response = agent.run_turn(prompt)
                print(f"\n{bold('Claude:')} {response}")
                return
        elif sys.argv[1] in ("-h", "--help"):
            print(HELP_TEXT)
            return

    # Interactive REPL loop
    while True:
        try:
            user_input = read_multiline_input()
        except (KeyboardInterrupt, EOFError):
            print(f"\n{dim('Goodbye!')}")
            break

        text = user_input.strip()
        if not text:
            continue

        # Handle slash commands
        if text.startswith("/"):
            cmd = text.lower().split()[0]
            if cmd in ("/quit", "/exit", "/q"):
                print(dim("Goodbye!"))
                break
            elif cmd == "/help":
                print(HELP_TEXT)
                continue
            elif cmd == "/clear":
                agent.messages.clear()
                agent.turn_count = 0
                print(dim("  Conversation cleared."))
                continue
            elif cmd == "/cost":
                print(dim(f"  Total tokens: {agent.total_tokens:,}"))
                continue
            elif cmd == "/model":
                parts = text.split(maxsplit=1)
                if len(parts) > 1:
                    global MODEL
                    MODEL = parts[1]
                    agent.system_prompt = build_system_prompt(os.getcwd())
                    print(dim(f"  Model changed to: {MODEL}"))
                else:
                    print(dim(f"  Current model: {MODEL}"))
                continue
            elif cmd == "/compact":
                # Simple compaction: keep system prompt, drop old messages
                if len(agent.messages) > 4:
                    agent.messages = agent.messages[-4:]
                    print(dim("  Compacted conversation to last 2 turns."))
                continue
            else:
                print(dim(f"  Unknown command: {cmd}. Type /help"))
                continue

        # Run the agent loop
        try:
            response = agent.run_turn(text)
            print(f"\n{bold('Claude:')} {response}\n")
        except KeyboardInterrupt:
            print(yellow("\n  [Interrupted]"))
            # Remove partial messages
            while agent.messages and agent.messages[-1]["role"] == "assistant":
                agent.messages.pop()
        except Exception as e:
            print(red(f"\n  Error: {e}"))


if __name__ == "__main__":
    main()
