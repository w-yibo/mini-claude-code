"""
Token cost tracking.
Maps to: src/cost-tracker.ts, src/costHook.ts

Claude Code tracks per-model pricing with cache-aware accounting.
"""

from dataclasses import dataclass, field

# Pricing per 1M tokens (from src/cost-tracker.ts)
# (input, output, cache_read, cache_write)
MODEL_PRICING: dict[str, tuple[float, float, float, float]] = {
    # Claude 4 family
    "claude-opus-4-0-20250514":    (15.0, 75.0, 1.5,  18.75),
    "claude-sonnet-4-20250514":     (3.0, 15.0, 0.3,   3.75),
    # Claude 3.5 family
    "claude-3-5-sonnet-20241022":   (3.0, 15.0, 0.3,   3.75),
    "claude-3-5-haiku-20241022":    (1.0,  5.0, 0.1,   1.25),
    # Claude 3 family
    "claude-3-opus-20240229":      (15.0, 75.0, 1.5,  18.75),
    "claude-3-haiku-20240307":      (0.25, 1.25, 0.03, 0.30),
    # OpenAI models
    "gpt-4o":                       (2.5, 10.0, 0.0, 0.0),
    "gpt-4o-mini":                  (0.15, 0.60, 0.0, 0.0),
    "gpt-4-turbo":                  (10.0, 30.0, 0.0, 0.0),
    "o1":                           (15.0, 60.0, 0.0, 0.0),
    "o3-mini":                      (1.1, 4.4, 0.0, 0.0),
    # DeepSeek
    "deepseek-chat":                (0.27, 1.10, 0.0, 0.0),
    "deepseek-reasoner":            (0.55, 2.19, 0.0, 0.0),
}

# Fallback pricing for unknown models
DEFAULT_PRICING = (3.0, 15.0, 0.3, 3.75)


@dataclass
class CostTracker:
    """
    Tracks token usage and estimated costs across the session.
    Mirrors CostTracker in src/cost-tracker.ts.
    """
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0

    # Per-turn tracking for display
    turn_input: int = 0
    turn_output: int = 0

    def record_usage(self, usage, model: str = ""):
        """Record usage from an Anthropic API response object."""
        inp = getattr(usage, "input_tokens", 0) or 0
        out = getattr(usage, "output_tokens", 0) or 0
        cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
        cache_write = getattr(usage, "cache_creation_input_tokens", 0) or 0

        self.input_tokens += inp
        self.output_tokens += out
        self.cache_read_tokens += cache_read
        self.cache_write_tokens += cache_write

        self.turn_input = inp + cache_read + cache_write
        self.turn_output = out

    def record_usage_dict(self, usage: dict, model: str = ""):
        """Record usage from a dict (provider-agnostic format from providers.py)."""
        inp = usage.get("input_tokens", 0)
        out = usage.get("output_tokens", 0)
        cache_read = usage.get("cache_read_input_tokens", 0)
        cache_write = usage.get("cache_creation_input_tokens", 0)

        self.input_tokens += inp
        self.output_tokens += out
        self.cache_read_tokens += cache_read
        self.cache_write_tokens += cache_write

        self.turn_input = inp + cache_read + cache_write
        self.turn_output = out

    @property
    def total_tokens(self) -> int:
        return (
            self.input_tokens
            + self.output_tokens
            + self.cache_read_tokens
            + self.cache_write_tokens
        )

    def estimate_cost(self, model: str = "") -> float:
        """Estimate total cost in USD."""
        pricing = self._get_pricing(model)
        cost = (
            self.input_tokens * pricing[0]
            + self.output_tokens * pricing[1]
            + self.cache_read_tokens * pricing[2]
            + self.cache_write_tokens * pricing[3]
        ) / 1_000_000
        return cost

    def get_summary(self, model: str = "") -> dict:
        """Return a summary dict for display."""
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_read": self.cache_read_tokens,
            "cache_write": self.cache_write_tokens,
            "total_tokens": self.total_tokens,
            "total_cost": self.estimate_cost(model),
        }

    def _get_pricing(self, model: str) -> tuple[float, float, float, float]:
        """Look up pricing for a model, with fuzzy matching."""
        if model in MODEL_PRICING:
            return MODEL_PRICING[model]
        # Fuzzy: match by substring
        for key, pricing in MODEL_PRICING.items():
            if key in model or model in key:
                return pricing
        return DEFAULT_PRICING
