"""
LLM Provider abstraction — supports Anthropic (native) and OpenAI-compatible APIs.

This is the key extension point for multi-model support.
Anthropic uses its native SDK (streaming, tool_use, cache).
OpenAI-compatible providers use the openai SDK with tool calling.

Design: both providers expose the same interface:
  - create_client(config) → client object
  - call_api_streaming(client, messages, tools, config) → (text, tool_uses)
  - call_api_sync(client, messages, config) → response text
"""

import json
import sys

from .config import Config
from .ui import Spinner, print_streaming_token


def create_client(config: Config):
    """
    Create the appropriate API client based on provider.
    Returns a client object (Anthropic or OpenAI).
    """
    if config.provider == "anthropic":
        import anthropic
        return anthropic.Anthropic(api_key=config.api_key or None)

    elif config.provider in ("openai", "openai-compatible"):
        try:
            from openai import OpenAI
        except ImportError:
            print("Error: openai package required for OpenAI provider.", file=sys.stderr)
            print("Install with: pip install openai", file=sys.stderr)
            sys.exit(1)

        kwargs = {"api_key": config.api_key}
        if config.api_base_url:
            kwargs["base_url"] = config.api_base_url
        return OpenAI(**kwargs)

    else:
        raise ValueError(f"Unknown provider: {config.provider}")


def call_api_streaming(
    client, messages: list[dict], tools: list[dict],
    system_prompt: str, config: Config,
) -> tuple[str, list[dict], dict]:
    """
    Call the LLM API with streaming. Provider-agnostic interface.

    Returns: (text_response, tool_use_blocks, usage_dict)
      - tool_use_blocks: [{"id": str, "name": str, "input": dict}, ...]
      - usage_dict: {"input_tokens": int, "output_tokens": int, ...}
    """
    if config.provider == "anthropic":
        return _stream_anthropic(client, messages, tools, system_prompt, config)
    else:
        return _stream_openai(client, messages, tools, system_prompt, config)


def call_api_sync(client, messages: list[dict], system_prompt: str, config: Config) -> str:
    """Simple sync API call (used by compact). Returns text only."""
    if config.provider == "anthropic":
        response = client.messages.create(
            model=config.model,
            max_tokens=4096,
            system=system_prompt,
            messages=messages,
        )
        return response.content[0].text
    else:
        oai_messages = _to_openai_messages(messages, system_prompt)
        response = client.chat.completions.create(
            model=config.model,
            max_tokens=4096,
            messages=oai_messages,
        )
        return response.choices[0].message.content or ""


# ============================================================================
# Anthropic native streaming (same as original agent.py)
# ============================================================================

def _stream_anthropic(client, messages, tools, system_prompt, config):
    text_parts = []
    tool_uses = []
    current_tool = None
    input_json_str = ""
    usage = {}

    spinner = Spinner("Thinking...")
    spinner.start()
    first_token = True

    with client.messages.stream(
        model=config.model,
        max_tokens=config.max_tokens,
        system=system_prompt,
        tools=tools,
        messages=messages,
    ) as stream:
        for event in stream:
            event_type = event.type

            if event_type == "content_block_start":
                block = event.content_block
                if first_token:
                    spinner.stop()
                    first_token = False
                if block.type == "tool_use":
                    current_tool = {"id": block.id, "name": block.name, "input": {}}
                    input_json_str = ""
                elif block.type == "text":
                    if not text_parts:
                        print()

            elif event_type == "content_block_delta":
                delta = event.delta
                if delta.type == "text_delta":
                    print_streaming_token(delta.text)
                    text_parts.append(delta.text)
                elif delta.type == "input_json_delta":
                    input_json_str += delta.partial_json

            elif event_type == "content_block_stop":
                if current_tool is not None:
                    if input_json_str:
                        try:
                            current_tool["input"] = json.loads(input_json_str)
                        except Exception:
                            current_tool["input"] = {}
                    tool_uses.append(current_tool)
                    current_tool = None
                    input_json_str = ""

        final_message = stream.get_final_message()
        if final_message and final_message.usage:
            u = final_message.usage
            usage = {
                "input_tokens": getattr(u, "input_tokens", 0),
                "output_tokens": getattr(u, "output_tokens", 0),
                "cache_read_input_tokens": getattr(u, "cache_read_input_tokens", 0),
                "cache_creation_input_tokens": getattr(u, "cache_creation_input_tokens", 0),
            }

    if first_token:
        spinner.stop()
    if text_parts:
        print()

    return "".join(text_parts), tool_uses, usage


# ============================================================================
# OpenAI-compatible streaming (GPT, DeepSeek, Qwen, etc.)
# ============================================================================

def _stream_openai(client, messages, tools, system_prompt, config):
    """
    OpenAI-compatible streaming with tool calls.
    Translates between Anthropic's tool_use format and OpenAI's function calling.
    """
    oai_messages = _to_openai_messages(messages, system_prompt)
    oai_tools = _to_openai_tools(tools)

    text_parts = []
    tool_calls_accum = {}  # index → {id, name, arguments_str}
    usage = {}

    spinner = Spinner("Thinking...")
    spinner.start()
    first_token = True

    kwargs = {
        "model": config.model,
        "max_tokens": config.max_tokens,
        "messages": oai_messages,
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    if oai_tools:
        kwargs["tools"] = oai_tools

    stream = client.chat.completions.create(**kwargs)

    for chunk in stream:
        if not chunk.choices:
            # Usage chunk (last one)
            if chunk.usage:
                usage = {
                    "input_tokens": chunk.usage.prompt_tokens or 0,
                    "output_tokens": chunk.usage.completion_tokens or 0,
                    "cache_read_input_tokens": 0,
                    "cache_creation_input_tokens": 0,
                }
            continue

        delta = chunk.choices[0].delta

        # Text content
        if delta.content:
            if first_token:
                spinner.stop()
                first_token = False
                print()
            print_streaming_token(delta.content)
            text_parts.append(delta.content)

        # Tool calls
        if delta.tool_calls:
            if first_token:
                spinner.stop()
                first_token = False
            for tc in delta.tool_calls:
                idx = tc.index
                if idx not in tool_calls_accum:
                    tool_calls_accum[idx] = {
                        "id": tc.id or f"call_{idx}",
                        "name": tc.function.name or "",
                        "arguments_str": "",
                    }
                if tc.id:
                    tool_calls_accum[idx]["id"] = tc.id
                if tc.function and tc.function.name:
                    tool_calls_accum[idx]["name"] = tc.function.name
                if tc.function and tc.function.arguments:
                    tool_calls_accum[idx]["arguments_str"] += tc.function.arguments

    if first_token:
        spinner.stop()
    if text_parts:
        print()

    # Parse accumulated tool calls into our standard format
    tool_uses = []
    for idx in sorted(tool_calls_accum.keys()):
        tc = tool_calls_accum[idx]
        try:
            inp = json.loads(tc["arguments_str"]) if tc["arguments_str"] else {}
        except json.JSONDecodeError:
            inp = {}
        tool_uses.append({
            "id": tc["id"],
            "name": tc["name"],
            "input": inp,
        })

    return "".join(text_parts), tool_uses, usage


# ============================================================================
# Format converters: Anthropic ↔ OpenAI message formats
# ============================================================================

def _to_openai_messages(messages: list[dict], system_prompt: str) -> list[dict]:
    """
    Convert Anthropic-format messages to OpenAI chat format.

    Anthropic: system is separate; tool_result is in user messages
    OpenAI: system is a message; tool results are 'tool' role messages
    """
    oai = [{"role": "system", "content": system_prompt}]

    for msg in messages:
        role = msg["role"]
        content = msg["content"]

        if isinstance(content, str):
            oai.append({"role": role, "content": content})

        elif isinstance(content, list):
            # Check if this is a tool_result message
            if any(isinstance(b, dict) and b.get("type") == "tool_result" for b in content):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_result":
                        oai.append({
                            "role": "tool",
                            "tool_call_id": block.get("tool_use_id", ""),
                            "content": str(block.get("content", "")),
                        })
            # Check if this is an assistant message with tool_use
            elif any(isinstance(b, dict) and b.get("type") == "tool_use" for b in content):
                text_parts = []
                tool_calls = []
                for block in content:
                    if isinstance(block, dict):
                        if block.get("type") == "text":
                            text_parts.append(block.get("text", ""))
                        elif block.get("type") == "tool_use":
                            tool_calls.append({
                                "id": block["id"],
                                "type": "function",
                                "function": {
                                    "name": block["name"],
                                    "arguments": json.dumps(block["input"]),
                                },
                            })
                msg_dict = {"role": "assistant", "content": "\n".join(text_parts) if text_parts else None}
                if tool_calls:
                    msg_dict["tool_calls"] = tool_calls
                oai.append(msg_dict)
            else:
                # Generic list content — concatenate text
                text = " ".join(
                    str(b.get("text", b.get("content", ""))) if isinstance(b, dict) else str(b)
                    for b in content
                )
                oai.append({"role": role, "content": text})
        else:
            oai.append({"role": role, "content": str(content)})

    return oai


def _to_openai_tools(tools: list[dict]) -> list[dict]:
    """
    Convert Anthropic tool definitions to OpenAI function calling format.

    Anthropic: {"name", "description", "input_schema": {...}}
    OpenAI:    {"type": "function", "function": {"name", "description", "parameters": {...}}}
    """
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": t["input_schema"],
            },
        }
        for t in tools
    ]
