"""
Auto-compact: conversation context compression.
Maps to: auto-compact logic in src/query.ts + compact-related code.

When the conversation approaches the context window limit,
Claude Code summarizes the conversation to free space. This module
implements that same pattern.
"""

from .config import get_config
from .ui import dim, yellow


# The compact prompt — asks the model to summarize the conversation
COMPACT_SYSTEM_PROMPT = """You are a conversation summarizer. Your job is to condense the conversation
so far into a compact summary that preserves all essential context for continuing the work.

Rules:
- Preserve ALL file paths, function names, variable names, and code snippets mentioned
- Preserve the current task/goal and its progress
- Preserve any decisions made and their rationale
- Preserve any errors encountered and their solutions
- Drop verbose tool outputs — keep only the key findings
- Drop pleasantries and filler
- Be concise but complete — nothing important should be lost
- Output in a structured format with sections"""


def should_compact(messages: list[dict], config=None) -> bool:
    """
    Decide if we need to compact.
    Maps to: shouldAutoCompact() in Claude Code.

    Claude Code triggers at ~93.5% of context window (187k/200k).
    We use a simpler token estimation: ~4 chars per token.
    """
    if config is None:
        config = get_config()

    if not config.auto_compact:
        return False

    estimated_tokens = _estimate_tokens(messages)
    threshold = int(config.context_window * config.compact_threshold)
    return estimated_tokens > threshold


def compact_messages(client, messages: list[dict], config) -> list[dict]:
    """
    Compact the conversation by asking the model to summarize.

    Strategy (mirrors Claude Code):
    1. Take all messages so far
    2. Ask a separate API call to summarize them
    3. Replace the message history with a single summary message

    Returns new message list starting with the summary.
    """
    if len(messages) <= 2:
        return messages

    print(f"  {yellow('⚡ Auto-compacting conversation...')}")

    # Build the conversation text for summarization
    conv_text = _messages_to_text(messages)

    try:
        from .providers import call_api_sync
        summary = call_api_sync(
            client,
            [{"role": "user", "content": f"Summarize this conversation so it can be continued:\n\n{conv_text}"}],
            COMPACT_SYSTEM_PROMPT,
            config,
        )

        # Replace history with a single user message containing the summary
        return [{
            "role": "user",
            "content": (
                f"[Previous conversation summary]\n{summary}\n"
                f"[End of summary — continue from here]"
            ),
        }]

    except Exception as e:
        print(f"  {dim(f'Compact failed: {e} — continuing without compaction')}")
        # Fallback: just keep the last N messages
        return messages[-10:]


def _estimate_tokens(messages: list[dict]) -> int:
    """
    Rough token count estimation.
    Claude Code uses actual tokenizer counts; we approximate (~4 chars/token).
    """
    total_chars = 0
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str):
            total_chars += len(content)
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    total_chars += len(str(block.get("content", "")))
                    total_chars += len(str(block.get("text", "")))
                else:
                    # Anthropic SDK objects
                    total_chars += len(str(getattr(block, "text", "")))
                    total_chars += len(str(getattr(block, "input", "")))
    return total_chars // 4


def _messages_to_text(messages: list[dict]) -> str:
    """Convert messages to readable text for the summarizer."""
    parts = []
    for msg in messages:
        role = msg.get("role", "unknown")
        content = msg.get("content", "")

        if isinstance(content, str):
            parts.append(f"[{role}]: {content[:2000]}")
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    btype = block.get("type", "")
                    if btype == "tool_use":
                        parts.append(f"[{role} tool_use]: {block.get('name', '')}({str(block.get('input', ''))[:500]})")
                    elif btype == "tool_result":
                        result_text = str(block.get("content", ""))[:500]
                        parts.append(f"[tool_result]: {result_text}")
                    elif btype == "text":
                        parts.append(f"[{role}]: {block.get('text', '')[:1000]}")
                else:
                    # SDK objects
                    if hasattr(block, "text"):
                        parts.append(f"[{role}]: {block.text[:1000]}")
                    elif hasattr(block, "name"):
                        parts.append(f"[{role} tool_use]: {block.name}")

    return "\n".join(parts[-50:])  # Keep last 50 entries max
