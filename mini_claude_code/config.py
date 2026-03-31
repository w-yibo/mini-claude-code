"""
Configuration & settings management.
Maps to: src/utils/config.ts, src/utils/envUtils.ts

Claude Code config hierarchy (3 layers):
  1. ~/.claude/settings.json        (global user settings)
  2. .claude/settings.json          (project, checked in)
  3. .claude/settings.local.json    (project personal, gitignored)
  4. Environment variables          (highest priority)
"""

import json
import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Config:
    """Runtime configuration — merges env vars, settings files, and defaults."""

    # Model & Provider
    model: str = ""
    provider: str = ""                # "anthropic", "openai", "openai-compatible"
    api_key: str = ""                 # Resolved API key (from env or settings)
    api_base_url: str = ""            # Custom base URL for OpenAI-compatible APIs
    max_tokens: int = 16384
    max_turns: int = 100

    # Context window management (from src/constants/system.ts)
    context_window: int = 200_000
    compact_threshold: float = 0.80   # Auto-compact when context > 80%
    compact_reserve: int = 20_000     # Reserve for compact output

    # Paths
    config_dir: str = ""              # ~/.claude equivalent
    cwd: str = ""

    # Behavior
    verbose: bool = False
    auto_compact: bool = True

    # Resolved state
    settings: dict = field(default_factory=dict)

    def __post_init__(self):
        self.cwd = self.cwd or os.getcwd()
        self.config_dir = self.config_dir or os.environ.get(
            "MINI_CC_CONFIG_DIR",
            os.path.join(Path.home(), ".mini-claude-code"),
        )
        self.model = self.model or os.environ.get(
            "MINI_CC_MODEL", "claude-sonnet-4-20250514"
        )
        self.max_tokens = int(os.environ.get("MINI_CC_MAX_TOKENS", self.max_tokens))
        self.max_turns = int(os.environ.get("MINI_CC_MAX_TURNS", self.max_turns))
        self.verbose = os.environ.get("MINI_CC_VERBOSE", "").lower() in ("1", "true")
        self.api_base_url = self.api_base_url or os.environ.get("MINI_CC_API_BASE_URL", "")
        # Load settings hierarchy
        self.settings = self._load_settings()
        # Resolve provider & API key
        self._resolve_provider()

    # ---- Settings file loading (mirrors src/utils/config.ts) ----

    def _load_settings(self) -> dict:
        """Load and merge settings from all layers."""
        merged: dict = {}
        paths = [
            os.path.join(self.config_dir, "settings.json"),           # global
            os.path.join(self.cwd, ".claude", "settings.json"),       # project
            os.path.join(self.cwd, ".claude", "settings.local.json"), # project local
        ]
        for p in paths:
            if os.path.isfile(p):
                try:
                    with open(p) as f:
                        data = json.load(f)
                    merged.update(data)
                except Exception:
                    pass
        return merged

    def _resolve_provider(self):
        """
        Auto-detect the API provider from model name, env vars, or explicit setting.

        Priority:
          1. Explicit MINI_CC_PROVIDER env var
          2. OPENAI_API_KEY set → openai
          3. ANTHROPIC_API_KEY set → anthropic
          4. Model name heuristic (gpt-*, o1-* → openai, claude-* → anthropic)
        """
        if self.provider:
            pass  # Already set via constructor
        elif os.environ.get("MINI_CC_PROVIDER"):
            self.provider = os.environ["MINI_CC_PROVIDER"]
        elif self.model.startswith(("gpt-", "o1-", "o3-", "o4-")):
            self.provider = "openai"
        elif self.model.startswith(("deepseek", "qwen", "mistral", "llama")):
            self.provider = "openai-compatible"
        else:
            # Default: check which API key is available
            if os.environ.get("ANTHROPIC_API_KEY"):
                self.provider = "anthropic"
            elif os.environ.get("OPENAI_API_KEY"):
                self.provider = "openai"
            else:
                self.provider = "anthropic"  # Will fail later with clear error

        # Resolve API key
        if not self.api_key:
            if self.provider == "anthropic":
                self.api_key = os.environ.get("ANTHROPIC_API_KEY", "")
            elif self.provider in ("openai", "openai-compatible"):
                self.api_key = os.environ.get("OPENAI_API_KEY", "")
                if not self.api_key:
                    self.api_key = os.environ.get("ANTHROPIC_API_KEY", "")

        # Resolve base URL for compatible providers
        if not self.api_base_url and self.provider == "openai-compatible":
            self.api_base_url = os.environ.get("MINI_CC_API_BASE_URL", "")
            # Common defaults
            if "deepseek" in self.model and not self.api_base_url:
                self.api_base_url = "https://api.deepseek.com"

        # Adjust context window for known models
        if self.model.startswith("gpt-4o"):
            self.context_window = 128_000
        elif self.model.startswith(("gpt-4-turbo", "gpt-4-0125")):
            self.context_window = 128_000
        elif self.model.startswith("gpt-3.5"):
            self.context_window = 16_000
        elif self.model.startswith("deepseek"):
            self.context_window = 64_000

    def ensure_dirs(self):
        """Create config and session dirs if they don't exist."""
        os.makedirs(self.config_dir, exist_ok=True)
        os.makedirs(os.path.join(self.config_dir, "sessions"), exist_ok=True)


# Singleton, lazily initialized
_config: Config | None = None


def get_config(**overrides) -> Config:
    global _config
    if _config is None:
        _config = Config(**overrides)
        _config.ensure_dirs()
    return _config


def reset_config():
    global _config
    _config = None
