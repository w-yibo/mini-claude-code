"""
Terminal display helpers — replaces Claude Code's React/Ink UI.
Maps to: src/components/, src/screens/

Claude Code uses React + Ink for a rich terminal UI with spinners,
progress bars, and real-time streaming. We use simple ANSI codes.
"""

import sys
import shutil
import time
from typing import IO

# ============================================================================
# ANSI color helpers
# ============================================================================

_NO_COLOR = not sys.stdout.isatty() or "NO_COLOR" in __import__("os").environ


def _c(code: str, text: str) -> str:
    return text if _NO_COLOR else f"\033[{code}m{text}\033[0m"


def dim(t: str) -> str: return _c("2", t)
def bold(t: str) -> str: return _c("1", t)
def green(t: str) -> str: return _c("32", t)
def yellow(t: str) -> str: return _c("33", t)
def red(t: str) -> str: return _c("31", t)
def cyan(t: str) -> str: return _c("36", t)
def magenta(t: str) -> str: return _c("35", t)
def blue(t: str) -> str: return _c("34", t)


def term_width() -> int:
    return shutil.get_terminal_size((80, 24)).columns


# ============================================================================
# Spinner for streaming (simple single-line)
# ============================================================================

class Spinner:
    """Minimal spinner for long-running operations."""
    FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

    def __init__(self, message: str = "Thinking...", stream: IO = sys.stderr):
        self._msg = message
        self._stream = stream
        self._idx = 0
        self._active = False

    def start(self):
        self._active = True
        self._draw()

    def stop(self, clear: bool = True):
        self._active = False
        if clear:
            self._stream.write(f"\r{' ' * (len(self._msg) + 4)}\r")
            self._stream.flush()

    def tick(self, message: str | None = None):
        if message:
            self._msg = message
        self._idx = (self._idx + 1) % len(self.FRAMES)
        self._draw()

    def _draw(self):
        frame = self.FRAMES[self._idx]
        self._stream.write(f"\r  {cyan(frame)} {dim(self._msg)}")
        self._stream.flush()


# ============================================================================
# Tool call display
# ============================================================================

# Icons for each tool (mirrors Claude Code's UI components)
TOOL_ICONS = {
    "Bash": "⚡",
    "Read": "📄",
    "Write": "✍️",
    "Edit": "🔧",
    "Glob": "📂",
    "Grep": "🔎",
    "WebFetch": "🌐",
    "WebSearch": "🔍",
    "NotebookEdit": "📓",
}


def print_tool_call(name: str, inp: dict):
    """Display a tool invocation — like Claude Code's tool call UI."""
    icon = TOOL_ICONS.get(name, "⚙️")

    if name == "Bash":
        cmd = inp.get("command", "")
        print(f"\n  {cyan(icon)} {bold('Bash')} {dim('›')} {cmd}")
    elif name == "Read":
        path = inp.get("file_path", "")
        extra = ""
        if inp.get("offset"):
            extra += f" (from line {inp['offset']}"
            if inp.get("limit"):
                extra += f", {inp['limit']} lines"
            extra += ")"
        print(f"\n  {cyan(icon)} {bold('Read')} {dim('›')} {path}{dim(extra)}")
    elif name == "Write":
        path = inp.get("file_path", "")
        print(f"\n  {cyan(icon)} {bold('Write')} {dim('›')} {path}")
    elif name == "Edit":
        path = inp.get("file_path", "")
        print(f"\n  {cyan(icon)} {bold('Edit')} {dim('›')} {path}")
    elif name == "Glob":
        pat = inp.get("pattern", "")
        base = inp.get("path", "")
        loc = f" in {base}" if base else ""
        print(f"\n  {cyan(icon)} {bold('Glob')} {dim('›')} {pat}{dim(loc)}")
    elif name == "Grep":
        pat = inp.get("pattern", "")
        base = inp.get("path", "")
        loc = f" in {base}" if base else ""
        print(f"\n  {cyan(icon)} {bold('Grep')} {dim('›')} {pat}{dim(loc)}")
    else:
        import json as _json
        args_str = _json.dumps(inp, ensure_ascii=False)[:120]
        print(f"\n  {cyan(icon)} {bold(name)} {dim('›')} {args_str}")


def print_tool_result(output: str, max_lines: int = 20):
    """Display truncated tool output."""
    lines = output.strip().splitlines()
    for line in lines[:max_lines]:
        print(f"  {dim(line[:200])}")
    remaining = len(lines) - max_lines
    if remaining > 0:
        print(f"  {dim(f'... ({remaining} more lines)')}")


def print_assistant(text: str):
    """Display assistant response."""
    print(f"\n{bold('Claude:')} {text}\n")


def print_streaming_token(token: str):
    """Print a single token during streaming — no newline."""
    sys.stdout.write(token)
    sys.stdout.flush()


def print_banner(model: str, cwd: str):
    """Display startup banner."""
    w = min(term_width(), 50)
    border = cyan("─" * w)
    print(f"""
  {border}
  {bold('Mini Claude Code')}  {dim('— Python Edition')}
  {border}
  {dim(f'Model:  {model}')}
  {dim(f'CWD:    {cwd}')}
  {dim('Type /help for commands, Ctrl+C to exit')}
""")


def print_cost(cost_info: dict):
    """Display token usage and cost."""
    print(f"""
  {bold('Session Usage:')}
    Input tokens:  {cost_info.get('input_tokens', 0):>10,}
    Output tokens: {cost_info.get('output_tokens', 0):>10,}
    Cache read:    {cost_info.get('cache_read', 0):>10,}
    Cache write:   {cost_info.get('cache_write', 0):>10,}
    {dim('─' * 30)}
    Total tokens:  {cost_info.get('total_tokens', 0):>10,}
    Est. cost:     {green(f"${cost_info.get('total_cost', 0):.4f}")}
""")
