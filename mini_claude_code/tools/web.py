"""
Web tools: WebFetch and WebSearch.
Maps to: src/tools/WebFetchTool/, src/tools/WebSearchTool/

These provide the agent with ability to access the web.
WebFetch downloads a URL; WebSearch uses a search API (optional).
"""

import json
import re
import subprocess
from urllib.parse import urlparse

from . import ToolSpec


# ============================================================================
# WebFetch Tool
# ============================================================================

def run_webfetch(inp: dict) -> str:
    url = inp.get("url", "")
    prompt = inp.get("prompt", "Extract the main content")

    if not url:
        return "Error: url is required"

    # Validate URL
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return "Error: only http/https URLs are supported"

    try:
        # Use curl to fetch, with timeout and size limit
        result = subprocess.run(
            [
                "curl", "-sL",
                "--max-time", "30",
                "--max-filesize", "5000000",
                "-H", "User-Agent: Mini-Claude-Code/1.0",
                url,
            ],
            capture_output=True, text=True, timeout=35,
        )

        if result.returncode != 0:
            return f"Error fetching {url}: {result.stderr}"

        content = result.stdout
        if not content:
            return "Error: empty response"

        # Basic HTML → text conversion (very simplified)
        text = _html_to_text(content)

        # Truncate
        if len(text) > 50_000:
            text = text[:50_000] + "\n\n[Content truncated]"

        return f"Content from {url}:\n\n{text}"

    except subprocess.TimeoutExpired:
        return f"Error: request timed out after 30s"
    except FileNotFoundError:
        return "Error: curl not found. Install curl to use WebFetch."
    except Exception as e:
        return f"Error: {e}"


def _html_to_text(html: str) -> str:
    """Very basic HTML to text conversion."""
    # Remove script and style blocks
    text = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)
    # Convert common elements
    text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'</?p[^>]*>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'</?div[^>]*>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'<h[1-6][^>]*>(.*?)</h[1-6]>', r'\n## \1\n', text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r'<li[^>]*>(.*?)</li>', r'- \1\n', text, flags=re.IGNORECASE | re.DOTALL)
    # Strip remaining tags
    text = re.sub(r'<[^>]+>', '', text)
    # Decode common entities
    text = text.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
    text = text.replace('&quot;', '"').replace('&#39;', "'").replace('&nbsp;', ' ')
    # Clean up whitespace
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


webfetch_spec = ToolSpec(
    name="WebFetch",
    description=(
        "Fetch content from a URL. Downloads the page and extracts text. "
        "Use for reading documentation, API references, or any public web content."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "The URL to fetch (http/https)"},
            "prompt": {"type": "string", "description": "What to look for in the content"},
        },
        "required": ["url"],
    },
    run=run_webfetch,
)


# ============================================================================
# WebSearch Tool (using SearXNG, DuckDuckGo, or fallback)
# ============================================================================

def run_websearch(inp: dict) -> str:
    query = inp.get("query", "")
    if not query:
        return "Error: query is required"

    # Try DuckDuckGo HTML search (no API key needed)
    try:
        result = subprocess.run(
            [
                "curl", "-sL",
                "--max-time", "15",
                "-H", "User-Agent: Mini-Claude-Code/1.0",
                f"https://html.duckduckgo.com/html/?q={query}",
            ],
            capture_output=True, text=True, timeout=20,
        )

        if result.returncode == 0 and result.stdout:
            # Extract search results from DDG HTML
            results = _parse_ddg_results(result.stdout)
            if results:
                return f"Search results for '{query}':\n\n" + "\n\n".join(results[:10])

        return f"No results found for '{query}'. Try a different query."

    except Exception as e:
        return f"Search failed: {e}. Note: WebSearch requires internet access and curl."


def _parse_ddg_results(html: str) -> list[str]:
    """Extract search results from DuckDuckGo HTML."""
    results = []
    # Find result blocks
    snippets = re.findall(
        r'class="result__a"[^>]*href="([^"]*)"[^>]*>(.*?)</a>.*?class="result__snippet"[^>]*>(.*?)</span>',
        html, re.DOTALL,
    )
    for url, title, snippet in snippets:
        title = re.sub(r'<[^>]+>', '', title).strip()
        snippet = re.sub(r'<[^>]+>', '', snippet).strip()
        if title:
            results.append(f"**{title}**\n{url}\n{snippet}")
    return results


websearch_spec = ToolSpec(
    name="WebSearch",
    description=(
        "Search the web and return results. "
        "Returns titles, URLs, and snippets from search results."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "The search query"},
        },
        "required": ["query"],
    },
    run=run_websearch,
)
