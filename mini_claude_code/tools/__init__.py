"""
Tool registry and base types.
Maps to: src/tools.ts, src/Tool.ts

Claude Code's tool system:
  - Each tool has: name, description, input_schema, run()
  - Tools are registered in a central registry
  - Each tool can inject text into the system prompt via prompt()
  - Tools can be concurrent-safe or exclusive

We simplify: no permissions, no concurrency control.
"""

from typing import Callable, Any

# Type alias for a tool runner function
ToolRunner = Callable[[dict], str]


class ToolSpec:
    """A tool specification — mirrors the Tool interface in src/Tool.ts."""

    def __init__(
        self,
        name: str,
        description: str,
        input_schema: dict,
        run: ToolRunner,
        prompt_hint: str = "",
    ):
        self.name = name
        self.description = description
        self.input_schema = input_schema
        self.run = run
        self.prompt_hint = prompt_hint  # Extra system prompt injection

    def to_api_format(self) -> dict:
        """Convert to Anthropic API tool definition format."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }


class ToolRegistry:
    """
    Central tool registry — mirrors getTools() in src/tools.ts.
    Register tools, look them up, and export to API format.
    """

    def __init__(self):
        self._tools: dict[str, ToolSpec] = {}

    def register(self, tool: ToolSpec):
        self._tools[tool.name] = tool

    def get(self, name: str) -> ToolSpec | None:
        return self._tools.get(name)

    def get_api_definitions(self) -> list[dict]:
        return [t.to_api_format() for t in self._tools.values()]

    def get_prompt_hints(self) -> str:
        """Collect all tool prompt hints for system prompt injection."""
        hints = [t.prompt_hint for t in self._tools.values() if t.prompt_hint]
        return "\n\n".join(hints)

    def execute(self, name: str, inp: dict) -> tuple[str, bool]:
        """
        Execute a tool by name. Returns (output, is_error).
        Maps to the tool execution in query.ts.
        """
        tool = self._tools.get(name)
        if not tool:
            return f"Error: unknown tool '{name}'", True
        try:
            output = tool.run(inp)
            return output, False
        except Exception as e:
            return f"Error executing {name}: {e}", True

    @property
    def tool_names(self) -> list[str]:
        return list(self._tools.keys())
