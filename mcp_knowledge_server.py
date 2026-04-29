"""MCP Knowledge Server — 本地知识库检索服务.

Reads JSON articles from ``knowledge/articles/`` and exposes three tools
via MCP (Model Context Protocol) over stdio with JSON-RPC 2.0.
"""

import json
import logging
import sys
from collections import Counter
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

ARTICLES_DIR = Path(__file__).resolve().parent / "knowledge" / "articles"

SERVER_NAME = "mcp-knowledge-server"
SERVER_VERSION = "0.1.0"
PROTOCOL_VERSION = "2024-11-05"


def _load_articles() -> list[dict[str, Any]]:
    """Load all JSON article files from the articles directory."""
    articles: list[dict[str, Any]] = []
    if not ARTICLES_DIR.is_dir():
        logger.warning("Articles directory not found: %s", ARTICLES_DIR)
        return articles
    for path in sorted(ARTICLES_DIR.glob("*.json")):
        try:
            articles.append(json.loads(path.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError) as exc:
            logger.error("Failed to load %s: %s", path.name, exc)
    return articles


def search_articles(keyword: str, limit: int = 5) -> dict[str, Any]:
    """Search articles by keyword in title and summary fields.

    Args:
        keyword: Search keyword (case-insensitive substring match).
        limit: Maximum number of results to return.

    Returns:
        Dict with ``count`` and ``results`` keys.
    """
    keyword_lower = keyword.lower()
    results: list[dict[str, Any]] = []
    for article in _load_articles():
        title = (article.get("title") or "").lower()
        title_cn = (article.get("title_cn") or "").lower()
        summary = (article.get("summary") or "").lower()
        summary_cn = (article.get("summary_cn") or "").lower()
        if (
            keyword_lower in title
            or keyword_lower in title_cn
            or keyword_lower in summary
            or keyword_lower in summary_cn
        ):
            results.append(article)
    results.sort(key=lambda a: a.get("score", 0), reverse=True)
    return {"count": len(results), "results": results[:limit]}


def get_article(article_id: str) -> dict[str, Any] | None:
    """Get a single article by its ID.

    Args:
        article_id: Unique article identifier.

    Returns:
        Article dict or ``None`` if not found.
    """
    for article in _load_articles():
        if article.get("id") == article_id:
            return article
    return None


def knowledge_stats() -> dict[str, Any]:
    """Return statistics about the knowledge base.

    Returns:
        Dict with ``total_articles``, ``source_distribution``, ``top_tags``.
    """
    articles = _load_articles()
    total = len(articles)
    source_dist = Counter(a.get("source", "unknown") for a in articles)
    all_tags: Counter[str] = Counter()
    for a in articles:
        all_tags.update(a.get("tags", []))
    return {
        "total_articles": total,
        "source_distribution": dict(source_dist),
        "top_tags": all_tags.most_common(10),
    }


# ---------------------------------------------------------------------------
# Tools schema
# ---------------------------------------------------------------------------

TOOLS_DEF: list[dict[str, Any]] = [
    {
        "name": "search_articles",
        "description": (
            "按关键词搜索知识库文章，匹配标题、中文标题、摘要、中文摘要，按评分降序排列"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "keyword": {
                    "type": "string",
                    "description": "搜索关键词",
                },
                "limit": {
                    "type": "integer",
                    "description": "返回结果数量上限，默认 5",
                    "default": 5,
                },
            },
            "required": ["keyword"],
        },
    },
    {
        "name": "get_article",
        "description": "按文章 ID 获取完整内容",
        "inputSchema": {
            "type": "object",
            "properties": {
                "article_id": {
                    "type": "string",
                    "description": "文章唯一 ID",
                },
            },
            "required": ["article_id"],
        },
    },
    {
        "name": "knowledge_stats",
        "description": "返回知识库统计信息：文章总数、来源分布、热门标签 Top 10",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
]

# ---------------------------------------------------------------------------
# JSON-RPC 2.0 helpers
# ---------------------------------------------------------------------------


def _jsonrpc_result(request_id: Any, result: Any) -> str:
    return json.dumps(
        {"jsonrpc": "2.0", "id": request_id, "result": result},
        ensure_ascii=False,
    )


def _jsonrpc_error(request_id: Any, code: int, message: str, data: Any = None) -> str:
    error: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return json.dumps(
        {"jsonrpc": "2.0", "id": request_id, "error": error},
        ensure_ascii=False,
    )


def _send_line(line: str) -> None:
    sys.stdout.write(line + "\n")
    sys.stdout.flush()


# ---------------------------------------------------------------------------
# Request dispatch
# ---------------------------------------------------------------------------


def _dispatch(request: dict[str, Any]) -> str | None:
    method = request.get("method", "")
    params = request.get("params", {})
    req_id = request.get("id")

    if method == "initialize":
        return _jsonrpc_result(
            req_id,
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": {
                    "name": SERVER_NAME,
                    "version": SERVER_VERSION,
                },
            },
        )

    if method == "notifications/initialized":
        return None

    if method == "ping":
        return _jsonrpc_result(req_id, {})

    if method == "tools/list":
        return _jsonrpc_result(req_id, {"tools": TOOLS_DEF})

    if method == "tools/call":
        tool_name = params.get("name", "").strip() if isinstance(params, dict) else ""
        arguments = params.get("arguments", {}) if isinstance(params, dict) else {}
        try:
            if tool_name == "search_articles":
                result = search_articles(
                    keyword=arguments.get("keyword", ""),
                    limit=arguments.get("limit", 5),
                )
            elif tool_name == "get_article":
                article = get_article(arguments.get("article_id", ""))
                if article is None:
                    return _jsonrpc_error(
                        req_id,
                        -32000,
                        f"Article not found: {arguments.get('article_id', '')}",
                    )
                result = article
            elif tool_name == "knowledge_stats":
                result = knowledge_stats()
            else:
                return _jsonrpc_error(req_id, -32601, f"Unknown tool: {tool_name}")

        except KeyError as exc:
            return _jsonrpc_error(req_id, -32602, f"Missing required parameter: {exc}")
        except Exception as exc:
            logger.exception("Tool execution failed")
            return _jsonrpc_error(req_id, -32000, str(exc))

        return _jsonrpc_result(
            req_id,
            {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(result, ensure_ascii=False, indent=2),
                    }
                ]
            },
        )

    return _jsonrpc_error(req_id, -32601, f"Unknown method: {method}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def run() -> None:
    """Run the MCP stdio event loop.

    Reads JSON-RPC requests line-by-line from stdin and writes responses
    to stdout.  All diagnostic output goes to stderr.
    """
    logging.basicConfig(
        level=logging.WARNING,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stderr,
    )
    logger.info("MCP Knowledge Server starting (stdio)")

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError as exc:
            logger.error("Invalid JSON-RPC request: %s", exc)
            continue
        response = _dispatch(request)
        if response is not None:
            _send_line(response)


if __name__ == "__main__":
    run()
