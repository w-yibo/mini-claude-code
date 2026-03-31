"""
Core agent loop — the heart of Claude Code.
Maps to: src/query.ts → queryLoop()

The agent loop pattern:
  1. Send messages + tools to API (with streaming)
  2. If response has tool_use blocks → execute tools → append tool_results → goto 1
  3. If response is text only → done, show to user

This module also handles streaming output and auto-compact.
"""

from .compact import compact_messages, should_compact
from .config import Config, get_config
from .cost import CostTracker
from .history import generate_session_id, save_session
from .prompts import build_system_prompt
from .providers import create_client, call_api_streaming, call_api_sync
from .tools import ToolRegistry
from .tools.bash import spec as bash_spec
from .tools.files import read_spec, write_spec, edit_spec
from .tools.search import glob_spec, grep_spec
from .tools.notebook import spec as notebook_spec
from .tools.web import webfetch_spec, websearch_spec
from .ui import (
    dim, red, yellow, cyan,
    print_tool_call, print_tool_result,
    print_streaming_token, Spinner,
)


def create_tool_registry() -> ToolRegistry:
    """Register all tools — mirrors getTools() in src/tools.ts."""
    registry = ToolRegistry()
    for spec in [
        bash_spec,
        read_spec, write_spec, edit_spec,
        glob_spec, grep_spec,
        notebook_spec,
        webfetch_spec, websearch_spec,
    ]:
        registry.register(spec)
    return registry


class AgentLoop:
    """
    The core agent loop.

    Mirrors src/query.ts → queryLoop():
      - State object holds messages, model config, tools
      - while(true): call API → check tool_use → execute → feed back → loop
      - Auto-compact when context gets full
      - Streaming output for text blocks

    Provider-agnostic: works with Anthropic, OpenAI, and any OpenAI-compatible API
    via the providers.py abstraction layer.
    """

    def __init__(self, config: Config | None = None):
        self.config = config or get_config()
        self.client = create_client(self.config)
        self.messages: list[dict] = []
        self.tools = create_tool_registry()
        self.cost = CostTracker()
        self.session_id = generate_session_id()
        self.turn_count = 0

        # Build system prompt (includes CLAUDE.md, env context, tool hints)
        self.system_prompt = build_system_prompt(self.config.cwd)
        tool_hints = self.tools.get_prompt_hints()
        if tool_hints:
            self.system_prompt += "\n\n" + tool_hints

    def run_turn(self, user_input: str) -> str:
        """
        Process one user turn through the full agent loop.

        Returns the final text response.
        Mirrors queryLoop() in src/query.ts.
        """
        self.messages.append({"role": "user", "content": user_input})

        while True:
            self.turn_count += 1
            if self.turn_count > self.config.max_turns:
                return red(f"[Reached max turns ({self.config.max_turns}). Stopping.]")

            # ---- Auto-compact check (mirrors shouldAutoCompact) ----
            if should_compact(self.messages, self.config):
                self.messages = compact_messages(
                    self.client, self.messages, self.config
                )

            # ---- Step 1: Call API with streaming ----
            try:
                response_text, tool_uses, usage = call_api_streaming(
                    self.client,
                    self.messages,
                    self.tools.get_api_definitions(),
                    self.system_prompt,
                    self.config,
                )
                # Record usage
                if usage:
                    self.cost.record_usage_dict(usage, self.config.model)

            except Exception as e:
                err_str = str(e).lower()
                if "overloaded" in err_str:
                    return yellow("[API overloaded. Please try again.]")
                return red(f"API Error: {e}")

            # ---- Step 2: If no tool calls, we're done ----
            if not tool_uses:
                return response_text

            # ---- Step 3: Build assistant message with all content blocks ----
            assistant_content = []
            if response_text:
                assistant_content.append({"type": "text", "text": response_text})
            for tu in tool_uses:
                assistant_content.append({
                    "type": "tool_use",
                    "id": tu["id"],
                    "name": tu["name"],
                    "input": tu["input"],
                })
            self.messages.append({"role": "assistant", "content": assistant_content})

            # ---- Step 4: Execute tools & collect results ----
            tool_results = []
            for tu in tool_uses:
                result = self._execute_tool(tu)
                tool_results.append(result)

            # ---- Step 5: Append tool results and loop ----
            self.messages.append({"role": "user", "content": tool_results})

    def _execute_tool(self, tool_use: dict) -> dict:
        """
        Execute a single tool call.
        Maps to tool execution in query.ts → StreamingToolExecutor.
        """
        name = tool_use["name"]
        inp = tool_use["input"]
        tool_id = tool_use["id"]

        # Display the tool call
        print_tool_call(name, inp)

        # Execute
        output, is_error = self.tools.execute(name, inp)

        # Display result
        print_tool_result(output)

        return {
            "type": "tool_result",
            "tool_use_id": tool_id,
            "content": output,
            **({"is_error": True} if is_error else {}),
        }

    def save(self):
        """Save session to disk."""
        save_session(
            self.session_id,
            self.messages,
            metadata={
                "total_tokens": self.cost.total_tokens,
                "total_cost": self.cost.estimate_cost(self.config.model),
                "turns": self.turn_count,
                "provider": self.config.provider,
                "model": self.config.model,
            },
        )
