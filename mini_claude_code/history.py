"""
Session history & persistence.
Maps to: src/history.ts

Claude Code stores conversation history per-project as JSONL files
in ~/.claude/sessions/. We do the same.
"""

import json
import os
import uuid
from datetime import datetime
from pathlib import Path

from .config import get_config


def generate_session_id() -> str:
    """Generate a unique session ID."""
    return datetime.now().strftime("%Y%m%d_%H%M%S_") + uuid.uuid4().hex[:8]


def save_session(session_id: str, messages: list[dict], metadata: dict | None = None):
    """
    Save a conversation session to disk.
    Maps to: addToHistory() in src/history.ts
    """
    config = get_config()
    session_dir = os.path.join(config.config_dir, "sessions")
    os.makedirs(session_dir, exist_ok=True)

    session_file = os.path.join(session_dir, f"{session_id}.json")

    # Serialize messages — handle Anthropic SDK content blocks
    serializable_messages = []
    for msg in messages:
        serializable_messages.append(_serialize_message(msg))

    data = {
        "session_id": session_id,
        "timestamp": datetime.now().isoformat(),
        "cwd": config.cwd,
        "model": config.model,
        "messages": serializable_messages,
        **(metadata or {}),
    }

    try:
        with open(session_file, "w") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, default=str)
    except Exception:
        pass  # Non-critical — don't crash on save failure


def load_session(session_id: str) -> list[dict] | None:
    """Load a previous session's messages."""
    config = get_config()
    session_file = os.path.join(config.config_dir, "sessions", f"{session_id}.json")

    if not os.path.isfile(session_file):
        return None

    try:
        with open(session_file) as f:
            data = json.load(f)
        return data.get("messages", [])
    except Exception:
        return None


def list_sessions(limit: int = 20) -> list[dict]:
    """List recent sessions — maps to getHistory() in src/history.ts."""
    config = get_config()
    session_dir = os.path.join(config.config_dir, "sessions")

    if not os.path.isdir(session_dir):
        return []

    sessions = []
    for f in sorted(Path(session_dir).glob("*.json"), reverse=True)[:limit]:
        try:
            with open(f) as fh:
                data = json.load(fh)
            # Extract first user message as preview
            first_msg = ""
            for msg in data.get("messages", []):
                if msg.get("role") == "user":
                    content = msg.get("content", "")
                    if isinstance(content, str):
                        first_msg = content[:100]
                    break
            sessions.append({
                "session_id": data.get("session_id", f.stem),
                "timestamp": data.get("timestamp", ""),
                "cwd": data.get("cwd", ""),
                "preview": first_msg,
            })
        except Exception:
            continue

    return sessions


def _serialize_message(msg: dict) -> dict:
    """Convert a message with possible SDK objects to plain dicts."""
    result = {"role": msg.get("role", "user")}
    content = msg.get("content", "")

    if isinstance(content, str):
        result["content"] = content
    elif isinstance(content, list):
        serialized = []
        for block in content:
            if isinstance(block, dict):
                serialized.append(block)
            elif hasattr(block, "type"):
                # Anthropic SDK content block
                if block.type == "text":
                    serialized.append({"type": "text", "text": block.text})
                elif block.type == "tool_use":
                    serialized.append({
                        "type": "tool_use",
                        "id": block.id,
                        "name": block.name,
                        "input": block.input,
                    })
                else:
                    serialized.append({"type": block.type, "data": str(block)})
            else:
                serialized.append(str(block))
        result["content"] = serialized
    else:
        result["content"] = str(content)

    return result
