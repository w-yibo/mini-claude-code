"""
CLI entry point — argument parsing and REPL.
Maps to: src/entrypoints/cli.tsx, src/main.tsx, src/replLauncher.tsx

Claude Code's CLI:
  - cli.tsx: bootstrap, fast-path for --version
  - main.tsx: Commander.js arg parsing, feature flags
  - replLauncher.tsx: interactive REPL with React/Ink

We combine all three into a single clean entry point.
"""

import os
import sys
import argparse

from .agent import AgentLoop
from .config import get_config, reset_config
from .history import list_sessions
from .ui import (
    bold, cyan, dim, green, red, yellow,
    print_banner, print_cost, print_assistant,
)

__version__ = "0.1.0"

# ============================================================================
# Slash command handler  (mirrors src/commands/)
# ============================================================================

HELP_TEXT = """
  {bold}Commands:{reset}
    {cmd}/help{reset}              Show this help
    {cmd}/clear{reset}             Clear conversation history
    {cmd}/compact{reset}           Manually compact conversation
    {cmd}/cost{reset}              Show token usage and cost
    {cmd}/model [name]{reset}      Show or change model
    {cmd}/history{reset}           Show recent sessions
    {cmd}/sessions{reset}          Alias for /history
    {cmd}/config{reset}            Show current configuration
    {cmd}/quit{reset}              Exit (also Ctrl+C)

  {bold}Tips:{reset}
    - Describe tasks in natural language
    - The agent uses tools automatically
    - Multi-line input: end a line with \\ to continue
    - Use CLAUDE.md in your project for persistent instructions
""".format(bold="\033[1m", reset="\033[0m", cmd="\033[36m")


def handle_slash_command(text: str, agent: AgentLoop) -> bool:
    """
    Handle a /command. Returns True if handled, False if not a command.
    """
    parts = text.strip().split(maxsplit=1)
    cmd = parts[0].lower()
    arg = parts[1] if len(parts) > 1 else ""

    if cmd in ("/quit", "/exit", "/q"):
        agent.save()
        print(dim("  Session saved. Goodbye!"))
        sys.exit(0)

    elif cmd == "/help":
        print(HELP_TEXT)
        return True

    elif cmd == "/clear":
        agent.messages.clear()
        agent.turn_count = 0
        print(dim("  ✓ Conversation cleared."))
        return True

    elif cmd == "/compact":
        from .compact import compact_messages
        if len(agent.messages) <= 2:
            print(dim("  Nothing to compact."))
        else:
            before = len(agent.messages)
            agent.messages = compact_messages(
                agent.client, agent.messages, agent.config.model
            )
            print(dim(f"  ✓ Compacted {before} messages → {len(agent.messages)}"))
        return True

    elif cmd == "/cost":
        print_cost(agent.cost.get_summary(agent.config.model))
        return True

    elif cmd == "/model":
        if arg:
            agent.config.model = arg
            print(dim(f"  ✓ Model changed to: {arg}"))
        else:
            print(dim(f"  Current model: {agent.config.model}"))
        return True

    elif cmd in ("/history", "/sessions"):
        sessions = list_sessions(limit=10)
        if not sessions:
            print(dim("  No previous sessions."))
        else:
            print(f"\n  {bold('Recent Sessions:')}")
            for s in sessions:
                ts = s["timestamp"][:16] if s["timestamp"] else "unknown"
                preview = s["preview"][:60] if s["preview"] else "(empty)"
                print(f"    {dim(ts)}  {preview}")
            print()
        return True

    elif cmd == "/config":
        config = agent.config
        print(f"""
  {bold('Configuration:')}
    Provider:        {config.provider}
    Model:           {config.model}
    Max tokens:      {config.max_tokens:,}
    Max turns:       {config.max_turns}
    Context window:  {config.context_window:,}
    Auto-compact:    {config.auto_compact}
    Config dir:      {config.config_dir}
    CWD:             {config.cwd}
    Session ID:      {agent.session_id}
    API base URL:    {config.api_base_url or '(default)'}
""")
        return True

    else:
        print(dim(f"  Unknown command: {cmd}. Type /help for available commands."))
        return True


# ============================================================================
# Input handling
# ============================================================================

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


# ============================================================================
# Main entry points
# ============================================================================

def run_interactive(agent: AgentLoop):
    """Interactive REPL mode — mirrors src/screens/REPL/."""
    print_banner(agent.config.model, agent.config.cwd)

    while True:
        try:
            user_input = read_multiline_input()
        except (KeyboardInterrupt, EOFError):
            print()
            agent.save()
            print(dim("  Session saved. Goodbye!"))
            break

        text = user_input.strip()
        if not text:
            continue

        # Slash commands
        if text.startswith("/"):
            handle_slash_command(text, agent)
            continue

        # Run agent loop
        try:
            response = agent.run_turn(text)
            print_assistant(response)
        except KeyboardInterrupt:
            print(yellow("\n  [Interrupted]"))
            # Clean up partial messages
            while agent.messages and agent.messages[-1].get("role") == "assistant":
                agent.messages.pop()
        except Exception as e:
            print(red(f"\n  Error: {e}"))
            if agent.config.verbose:
                import traceback
                traceback.print_exc()


def run_oneshot(prompt: str, agent: AgentLoop, output_format: str = "text"):
    """
    Non-interactive mode — mirrors `claude -p "..."`.
    Runs a single prompt and exits.
    """
    try:
        response = agent.run_turn(prompt)
        if output_format == "json":
            import json
            print(json.dumps({
                "response": response,
                "session_id": agent.session_id,
                "usage": agent.cost.get_summary(agent.config.model),
            }, ensure_ascii=False, indent=2))
        else:
            print(response)
    except Exception as e:
        print(red(f"Error: {e}"), file=sys.stderr)
        sys.exit(1)
    finally:
        agent.save()


def main():
    """Main entry point — mirrors src/entrypoints/cli.tsx → main()."""
    parser = argparse.ArgumentParser(
        prog="mini-claude-code",
        description="Mini Claude Code — a minimal AI coding agent",
    )
    parser.add_argument("prompt", nargs="?", help="Initial prompt (starts interactive mode)")
    parser.add_argument("-p", "--print", dest="oneshot", metavar="PROMPT",
                        help="Run a single prompt and exit (non-interactive)")
    parser.add_argument("-m", "--model", help="Model to use")
    parser.add_argument("--provider", choices=["anthropic", "openai", "openai-compatible"],
                        help="API provider (auto-detected from model name if omitted)")
    parser.add_argument("--api-base-url", help="Base URL for OpenAI-compatible APIs")
    parser.add_argument("--max-tokens", type=int, help="Max response tokens")
    parser.add_argument("--max-turns", type=int, help="Max agent loop turns")
    parser.add_argument("--output-format", choices=["text", "json"], default="text",
                        help="Output format for non-interactive mode")
    parser.add_argument("--verbose", action="store_true", help="Verbose output")
    parser.add_argument("-v", "--version", action="version", version=f"%(prog)s {__version__}")

    args = parser.parse_args()

    # Check API key
    if not os.environ.get("ANTHROPIC_API_KEY") and not os.environ.get("OPENAI_API_KEY"):
        print(red("Error: No API key found."), file=sys.stderr)
        print(dim("Set one of:"), file=sys.stderr)
        print(dim("  export ANTHROPIC_API_KEY=sk-ant-...  (for Claude models)"), file=sys.stderr)
        print(dim("  export OPENAI_API_KEY=sk-...         (for GPT/OpenAI-compatible models)"), file=sys.stderr)
        sys.exit(1)

    # Build config from args
    overrides = {}
    if args.model:
        overrides["model"] = args.model
    if args.provider:
        overrides["provider"] = args.provider
    if args.api_base_url:
        overrides["api_base_url"] = args.api_base_url
        overrides["model"] = args.model
    if args.max_tokens:
        overrides["max_tokens"] = args.max_tokens
    if args.max_turns:
        overrides["max_turns"] = args.max_turns
    if args.verbose:
        overrides["verbose"] = True

    reset_config()
    config = get_config(**overrides)
    agent = AgentLoop(config)

    # Dispatch to the right mode
    if args.oneshot:
        run_oneshot(args.oneshot, agent, args.output_format)
    elif args.prompt:
        # Interactive mode with initial prompt
        print_banner(config.model, config.cwd)
        print(f"{green(bold('You:'))} {args.prompt}")
        try:
            response = agent.run_turn(args.prompt)
            print_assistant(response)
        except Exception as e:
            print(red(f"Error: {e}"))
        run_interactive(agent)
    else:
        run_interactive(agent)


if __name__ == "__main__":
    main()
