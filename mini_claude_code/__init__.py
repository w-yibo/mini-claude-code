"""
mini-claude-code: A minimal, readable Python re-implementation of Claude Code.

Architecture (maps 1:1 to the real Claude Code):
    cli.py          ← src/entrypoints/cli.tsx      Entry point & arg parsing
    agent.py        ← src/query.ts                  Core agent loop
    tools/          ← src/tools/                    Tool implementations
    prompts.py      ← src/constants/prompts.ts      System prompt builder
    config.py       ← src/utils/config.ts           Configuration & settings
    cost.py         ← src/cost-tracker.ts           Token & cost tracking
    compact.py      ← context compaction logic       Auto-compact
    history.py      ← src/history.ts                Session persistence
    ui.py           ← terminal display (replaces React/Ink)
"""
