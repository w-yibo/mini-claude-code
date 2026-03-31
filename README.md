<p align="center">
  <h1 align="center">Mini Claude Code 🐍</h1>
  <p align="center">
    <b>A minimal, readable Python re-implementation of <a href="https://claude.com/claude-code">Claude Code</a>'s agentic harness.</b>
    <br/>
    <i>500,000 lines of TypeScript → ~2,500 lines of Python. Same architecture. Same loop. 200× smaller.</i>
  </p>
</p>

<p align="center">
  <a href="#quick-start">Quick Start</a> •
  <a href="#architecture-claude-code-source-mapping">Architecture</a> •
  <a href="#side-by-side-comparison-with-claude-code">Comparison</a> •
  <a href="#extending">Extending</a> •
  <a href="#disclaimer">Disclaimer</a>
</p>

---

## Motivation

Modern AI coding agents like Claude Code, Cursor, and Aider represent a new paradigm: **the agentic harness** — an orchestration layer that connects an LLM to real-world tools (file I/O, shell, search) through an autonomous loop. Understanding, experimenting with, and improving this harness is critical for advancing the field.

However, production agent systems are massive and opaque. Claude Code alone is ~500K lines of TypeScript with React/Ink UI, OAuth, MCP, telemetry, sandboxing, and enterprise features — none of which are essential to the core agent pattern.

**Mini Claude Code** strips all of that away. What remains is the **architectural skeleton** of a production AI coding agent — faithful to the original design, but readable in an afternoon. Every module maps 1:1 to its Claude Code counterpart, with inline comments pointing back to the original source files.

**This project exists to serve the AI agent research community:**

- 📚 **Educational** — Learn how production agentic harnesses actually work, not how textbooks say they should
- 🔬 **Research** — A clean, hackable base for agent loop experiments, tool-use ablations, prompt engineering studies, and benchmark development
- 🧩 **Extensible** — Add new tools, swap LLM backends, or modify the loop in minutes, not days
- 📖 **Documented** — Every file, every function traces back to its origin in the Claude Code source

## Quick Start

### Option A: With Claude (Anthropic)

```bash
# Install
pip install anthropic

# Set your API key
export ANTHROPIC_API_KEY="sk-ant-..."

# Run
python -m mini_claude_code.cli
```

### Option B: With GPT (OpenAI)

```bash
# Install
pip install anthropic openai

# Set your API key
export OPENAI_API_KEY="sk-..."

# Run — provider is auto-detected from model name
python -m mini_claude_code.cli -m gpt-4o
```

### Option C: With DeepSeek / Any OpenAI-Compatible API

```bash
pip install anthropic openai

export OPENAI_API_KEY="your-deepseek-key"

# Auto-detects DeepSeek base URL
python -m mini_claude_code.cli -m deepseek-chat

# Or specify custom endpoint
python -m mini_claude_code.cli -m my-model --provider openai-compatible --api-base-url https://api.example.com
```

### Option D: Install as Package

```bash
# Clone the repo
git clone https://github.com/YOUR_USERNAME/mini-claude-code.git
cd mini-claude-code

# Install with all providers
pip install ".[all]"

# Or install with only Anthropic support
pip install .

# This gives you two global commands:
#   mcc              — short alias
#   mini-claude-code — full name

# Verify installation
mcc --version          # mini-claude-code 0.1.0
mcc --help             # show all options

# Set your API key (pick one)
export ANTHROPIC_API_KEY="sk-ant-..."   # for Claude
export OPENAI_API_KEY="sk-..."          # for GPT / compatible APIs

# Interactive mode — just run it
mcc

# One-shot mode
mcc -p "fix the bug in main.py"

# Use any model + custom endpoint
mcc -m gpt-4o-mini --api-base-url https://your-proxy.com/v1

# JSON output (for scripting / pipelines)
mcc -p "list all functions" --output-format json
```

### More Examples

```bash
# One-shot mode (like `claude -p`)
python -m mini_claude_code.cli -p "find all TODO comments in this project"

# With a specific model
python -m mini_claude_code.cli -m claude-opus-4-0-20250514

# JSON output for scripting
python -m mini_claude_code.cli -p "list all functions" --output-format json
```

## Architecture: Claude Code Source Mapping

Every file in this project maps directly to its counterpart in the Claude Code source tree. This is not a "inspired by" reimplementation — it is a **structural translation**.

```
mini_claude_code/
│
├── cli.py              ← src/entrypoints/cli.tsx + src/main.tsx
│                         Entry point, argument parsing, REPL loop, slash commands
│
├── agent.py            ← src/query.ts (queryLoop)
│                         ★ THE CORE: agent loop, streaming, tool execution
│
├── providers.py        ← src/services/api/claude.ts (NEW: multi-provider)
│                         Anthropic native + OpenAI-compatible API abstraction
│
├── prompts.py          ← src/constants/prompts.ts + src/constants/system.ts
│                         System prompt assembly, CLAUDE.md loading, tool guidelines
│
├── config.py           ← src/utils/config.ts + src/utils/envUtils.ts
│                         3-layer settings hierarchy + provider auto-detection
│
├── cost.py             ← src/cost-tracker.ts + src/costHook.ts
│                         Per-model token pricing, cache-aware cost accounting
│
├── compact.py          ← auto-compact logic within src/query.ts
│                         Context window compression when approaching limits
│
├── history.py          ← src/history.ts
│                         Session persistence, save/load/list conversations
│
├── ui.py               ← src/components/ + src/screens/ (replaces React/Ink)
│                         ANSI colors, spinner, tool call display, streaming output
│
└── tools/
    ├── __init__.py     ← src/Tool.ts + src/tools.ts
    │                     ToolSpec base class, ToolRegistry, execution dispatch
    ├── bash.py         ← src/tools/BashTool/BashTool.ts
    ├── files.py        ← src/tools/ReadTool/ + WriteTool/ + EditTool/
    ├── search.py       ← src/tools/GlobTool/ + GrepTool/
    ├── notebook.py     ← src/tools/NotebookEditTool/
    └── web.py          ← src/tools/WebFetchTool/ + WebSearchTool/
```

## The Core Agent Loop

The heart of every AI coding agent is a single loop. Here is ours — structurally identical to `queryLoop()` in Claude Code's `src/query.ts`:

```python
# agent.py — the entire agent in 15 lines of pseudocode

while True:
    # 1. Auto-compact if approaching context window limit
    if should_compact(messages):
        messages = compact_messages(messages)

    # 2. Call LLM API with streaming (shows tokens in real-time)
    text, tool_uses = call_api_streaming(messages, tools)

    # 3. No tool calls → agent is done, return text to user
    if not tool_uses:
        return text

    # 4. Execute each tool call, collect results
    for tool_call in tool_uses:
        result = execute(tool_call.name, tool_call.input)
        results.append(tool_result(result))

    # 5. Append results to conversation and loop back to step 1
    messages.append(results)
```

This is the **agentic harness pattern**: `LLM → Tool Use → Execute → Feed Back → Repeat`. Everything else — UI, config, history, cost tracking — is scaffolding around this loop.

## Side-by-Side Comparison with Claude Code

### Scale Comparison

| Metric | Claude Code | Mini Claude Code | Reduction |
|--------|-------------|------------------|-----------|
| Total lines of code | ~500,000 | ~2,500 | **200×** |
| Number of files | ~1,900 | 12 | **160×** |
| Dependencies | 100+ npm packages | 1-2 (anthropic, openai) | **~100×** |
| Languages | TypeScript + React/JSX | Python only | — |
| Build system | Bun + custom macros | None needed | — |

### Feature Comparison

| Feature | Claude Code | Mini Claude Code | Notes |
|---------|:-----------:|:----------------:|-------|
| **Core agent loop** | ✅ `queryLoop()` | ✅ `AgentLoop.run_turn()` | Structurally identical |
| **Streaming responses** | ✅ SSE + Ink rendering | ✅ Real-time token printing | Same streaming events |
| **Tool system** | ✅ 30+ tools | ✅ 9 essential tools | Covers all core operations |
| **Auto-compact** | ✅ 187k/200k threshold | ✅ Configurable threshold | Same summarize-and-replace strategy |
| **Cost tracking** | ✅ Cache-aware accounting | ✅ Cache-aware accounting | Same per-model pricing tables |
| **Session persistence** | ✅ JSONL per-project | ✅ JSON per-session | Same save/load/list pattern |
| **CLAUDE.md memory** | ✅ 4-layer hierarchy | ✅ 4-layer hierarchy | Same search order |
| **Settings files** | ✅ 4 layers + MDM + API | ✅ 3-layer merge | Same global→project→local pattern |
| **Slash commands** | ✅ 15+ commands | ✅ 8 commands | Core set retained |
| **Non-interactive mode** | ✅ `-p` print mode | ✅ `-p` with JSON output | Same flag |
| Permission system | ✅ Full sandbox | ❌ | Intentionally removed |
| Multi-LLM provider | ❌ Anthropic only | ✅ Anthropic + OpenAI + any compatible | Extension beyond original |
| React/Ink terminal UI | ✅ Rich components | ❌ → ANSI fallback | Simplified |
| OAuth / MCP / Auto-update | ✅ Full infrastructure | ❌ | Out of scope |
| Telemetry / Analytics | ✅ GrowthBook + OTEL | ❌ | Not needed |
| Agent SDK / Sub-agents | ✅ Fork semantics | ❌ | Future work |

### Architectural Mapping (Key Functions)

| Concept | Claude Code (TypeScript) | Mini Claude Code (Python) |
|---------|--------------------------|---------------------------|
| Agent loop | `src/query.ts` → `queryLoop()` | `agent.py` → `AgentLoop.run_turn()` |
| API call | `src/services/api/claude.ts` → `queryModelWithStreaming()` | `providers.py` → `call_api_streaming()` |
| Provider abstraction | ❌ Anthropic-only in claude.ts | `providers.py` → Anthropic / OpenAI / compatible |
| Tool execution | `src/query.ts` → `StreamingToolExecutor` | `agent.py` → `_execute_tool()` |
| Tool registry | `src/tools.ts` → `getTools()` | `tools/__init__.py` → `ToolRegistry` |
| Tool definition | `src/Tool.ts` → `Tool` interface | `tools/__init__.py` → `ToolSpec` class |
| System prompt | `src/constants/prompts.ts` → `buildSystemPromptBlocks()` | `prompts.py` → `build_system_prompt()` |
| CLAUDE.md loader | `src/utils/claudemd.ts` | `prompts.py` → `_load_claude_md()` |
| Config home | `src/utils/envUtils.ts` → `getClaudeConfigHomeDir()` | `config.py` → `Config.config_dir` |
| Settings merge | `src/utils/config.ts` → multi-layer load | `config.py` → `Config._load_settings()` |
| Cost tracker | `src/cost-tracker.ts` → `CostTracker` | `cost.py` → `CostTracker` |
| Auto-compact | `shouldAutoCompact()` in query.ts | `compact.py` → `should_compact()` |
| Session save | `src/history.ts` → `addToHistory()` | `history.py` → `save_session()` |
| CLI entry | `src/entrypoints/cli.tsx` → `main()` | `cli.py` → `main()` |
| REPL | `src/replLauncher.tsx` + React/Ink | `cli.py` → `run_interactive()` |
| User-Agent | `src/utils/userAgent.ts` | `config.py` (simplified) |
| Version output | `MACRO.VERSION` (build-time inject) | `cli.py` → `__version__` |

## Tools

| Tool | Claude Code Origin | Description |
|------|-------------------|-------------|
| **Bash** | `src/tools/BashTool/` | Execute shell commands with configurable timeout |
| **Read** | `src/tools/ReadTool/` | Read file contents with line numbers (cat -n format) |
| **Write** | `src/tools/WriteTool/` | Create new files or overwrite existing ones |
| **Edit** | `src/tools/EditTool/` | Exact string replacement with uniqueness checking |
| **Glob** | `src/tools/GlobTool/` | Find files by glob pattern (`**/*.py`) |
| **Grep** | `src/tools/GrepTool/` | Search file contents with regex (ripgrep + Python fallback) |
| **NotebookEdit** | `src/tools/NotebookEditTool/` | Edit Jupyter notebook cells (replace/insert/delete) |
| **WebFetch** | `src/tools/WebFetchTool/` | Fetch and extract content from URLs |
| **WebSearch** | `src/tools/WebSearchTool/` | Web search via DuckDuckGo (no API key needed) |

## Configuration

### Environment Variables

```bash
# API Keys (set at least one)
ANTHROPIC_API_KEY=sk-ant-...            # For Claude models
OPENAI_API_KEY=sk-...                   # For GPT / OpenAI-compatible models

# Model & Provider
MINI_CC_MODEL=claude-sonnet-4-20250514    # Model name (default: sonnet)
MINI_CC_PROVIDER=anthropic              # Force provider: anthropic, openai, openai-compatible
MINI_CC_API_BASE_URL=https://...        # Custom API base URL (for compatible providers)

# Limits
MINI_CC_MAX_TOKENS=16384                # Max response tokens per turn
MINI_CC_MAX_TURNS=100                   # Max agent loop iterations per query

# Paths & Debug
MINI_CC_CONFIG_DIR=~/.mini-claude-code  # Config directory location
MINI_CC_VERBOSE=1                       # Enable verbose error output
```

**Provider auto-detection**: If you don't set `MINI_CC_PROVIDER`, it is inferred from the model name:
- `claude-*` → `anthropic`
- `gpt-*`, `o1-*`, `o3-*`, `o4-*` → `openai`
- `deepseek-*`, `qwen-*`, `mistral-*`, `llama-*` → `openai-compatible`
- Otherwise → whichever API key is set

### Settings File Hierarchy

Same 3-layer pattern as Claude Code:

```
~/.mini-claude-code/settings.json       # Layer 1: Global user settings
<project>/.claude/settings.json         # Layer 2: Project settings (committed to git)
<project>/.claude/settings.local.json   # Layer 3: Personal overrides (gitignored)
```

### CLAUDE.md Memory Files

Project memory is loaded in the same order as Claude Code:

```
<project>/CLAUDE.md                     # Project root instructions
<project>/.claude/CLAUDE.md             # Project config directory
<project>/.claude/rules/*.md            # Modular project rules
~/.mini-claude-code/CLAUDE.md           # Global user memory (all projects)
```

## Slash Commands

| Command | Description |
|---------|-------------|
| `/help` | Show available commands |
| `/clear` | Clear conversation history |
| `/compact` | Manually trigger context compaction |
| `/cost` | Display token usage and estimated cost |
| `/model [name]` | Show current model or switch to a new one |
| `/history` | List recent sessions |
| `/config` | Show all current configuration values |
| `/quit` | Save session to disk and exit |

## Extending

### Adding a New Tool

Create a file in `tools/` and register it — that's it:

```python
# mini_claude_code/tools/my_tool.py
from . import ToolSpec

def run(inp: dict) -> str:
    """Your tool logic here."""
    name = inp.get("name", "world")
    return f"Hello, {name}!"

spec = ToolSpec(
    name="MyTool",
    description="A friendly greeting tool",
    input_schema={
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Who to greet"},
        },
        "required": ["name"],
    },
    run=run,
)
```

Then register it in `agent.py` → `create_tool_registry()`:

```python
from .tools.my_tool import spec as my_tool_spec
# Add: registry.register(my_tool_spec)
```

### Swapping the LLM Backend

Multi-provider support is built in. The `providers.py` module abstracts all LLM API calls:

```bash
# Anthropic (default)
python -m mini_claude_code.cli -m claude-sonnet-4-20250514

# OpenAI
python -m mini_claude_code.cli -m gpt-4o

# DeepSeek
python -m mini_claude_code.cli -m deepseek-chat

# Any OpenAI-compatible API
python -m mini_claude_code.cli -m my-model \
    --provider openai-compatible \
    --api-base-url https://api.example.com
```

To add a completely new provider (e.g., Google Gemini), add a new `_stream_gemini()` function in `providers.py` and a case in `create_client()`.

## What's Intentionally Left Out (and Why)

| Feature | Reason for Removal |
|---------|--------------------|
| Permission system / sandbox | Removes complexity barrier for research use |
| OAuth / session authentication | API key is sufficient; OAuth is infrastructure, not architecture |
| MCP (Model Context Protocol) | Orthogonal concern; can be added as a tool |
| React/Ink terminal UI | ANSI codes achieve the same goal in 177 LOC vs thousands |
| Auto-updater | Not relevant for a research tool |
| Telemetry / analytics | No data collection needed |
| Agent SDK / sub-agents | Interesting future work, but not core to the harness pattern |

### What's Added Beyond Claude Code

| Feature | Why |
|---------|-----|
| **Multi-provider support** | Anthropic + OpenAI + any compatible API via `providers.py` |
| **Provider auto-detection** | Model name → provider mapping (no config needed) |
| **OpenAI tool calling bridge** | Translates Anthropic tool_use ↔ OpenAI function calling |

Each omitted feature is a **deliberate architectural decision**, not a shortcut. The goal is to isolate the agentic harness pattern from production infrastructure.

## Research Applications

This codebase is designed as a **research platform** for studying AI agent systems:

- **Agent Loop Dynamics** — Modify the core loop to study how tool call ordering, parallel execution, or retry strategies affect task completion
- **Prompt Engineering** — Swap system prompts in `prompts.py` and measure impact on coding benchmarks (SWE-Bench, HumanEval, etc.)
- **Tool Ablation Studies** — Remove or modify tools to quantify their contribution to agent capability
- **Context Management** — Experiment with different compaction strategies in `compact.py`
- **Cost Optimization** — Study token efficiency patterns across different models and tasks
- **Benchmark Development** — Use the clean tool-use logs for building new agent evaluation frameworks
- **Multi-Model Comparison** — Switch models via `--model` flag to compare agent behavior across LLM families

## Disclaimer

> **⚠️ IMPORTANT: This project is for educational and scientific purposes only.**
>
> Mini Claude Code is an **independent, minimal re-implementation** created to advance the understanding of agentic harness architectures for the AI research community. It is intended solely for:
>
> - 📚 **Education** — Learning how production AI coding agents are architected
> - 🔬 **Academic research** — Providing a clean, modifiable base for agent system studies
> - 🧪 **Experimentation** — Enabling rapid prototyping of new agent loop designs
>
> **This project is NOT affiliated with, endorsed by, or sponsored by Anthropic.** "Claude Code" is a product of Anthropic. The architectural patterns documented here are based on publicly observable behavior and publicly available information. All trademarks belong to their respective owners.
>
> This project does **not** redistribute any proprietary code. It is a clean-room re-implementation in a different language (Python) based on publicly known agent design patterns.
>
> Users are responsible for complying with Anthropic's [Terms of Service](https://www.anthropic.com/policies/terms) and [Acceptable Use Policy](https://www.anthropic.com/policies/aup) when using the Anthropic API through this tool.

## Citation

If you use Mini Claude Code in academic work, please cite:

```bibtex
@software{mini_claude_code,
  title  = {Mini Claude Code: A Minimal Python Re-implementation of Claude Code's Agentic Harness},
  year   = {2025},
  url    = {https://github.com/YOUR_USERNAME/mini-claude-code},
  note   = {Educational and research re-implementation for studying AI agent architectures}
}
```

## License

MIT — use it freely for research, education, and building better AI agents.
