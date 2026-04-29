#!/usr/bin/env python3
"""Four-step knowledge base automation pipeline.

collect -> analyze -> organize -> save

Usage:
    python pipeline/pipeline.py --sources github,rss --limit 20
    python pipeline/pipeline.py --sources github --limit 5
    python pipeline/pipeline.py --sources rss --limit 10
    python pipeline/pipeline.py --sources github --limit 5 --dry-run
    python pipeline/pipeline.py --verbose
"""

import argparse
import asyncio
import hashlib
import json
import logging
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import httpx
from model_client import chat_with_retry

logger = logging.getLogger(__name__)

# ── Paths ───────────────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = PROJECT_ROOT / "knowledge" / "raw"
ARTICLES_DIR = PROJECT_ROOT / "knowledge" / "articles"

# ── Source configuration ────────────────────────────────────────────────────

GITHUB_SEARCH_QUERIES = [
    "topic:ai",
    "topic:llm",
    "topic:agent",
    "topic:machine-learning",
    "topic:rust",
    "topic:operating-system",
]

RSS_FEEDS = [
    "https://hnrss.org/frontpage",
    "https://hnrss.org/newest?q=ai+OR+llm+OR+agent+OR+rust",
    "https://arxiv.org/rss/cs.AI",
    "https://arxiv.org/rss/cs.CL",
]

# ── RSS regex patterns ──────────────────────────────────────────────────────

RE_ITEM = re.compile(r"<item>(.*?)</item>", re.DOTALL)
RE_ENTRY = re.compile(r"<entry>(.*?)</entry>", re.DOTALL)
RE_TITLE = re.compile(r"<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>", re.DOTALL)
RE_LINK = re.compile(r"<link(?:[^>]*)?>(.*?)</link>", re.DOTALL)
RE_LINK_HREF = re.compile(r'<link[^>]*href="(.*?)"', re.DOTALL)
RE_DESCRIPTION = re.compile(
    r"<description>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</description>", re.DOTALL
)
RE_SUMMARY = re.compile(
    r"<summary>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</summary>", re.DOTALL
)
RE_PUBDATE = re.compile(r"<pubDate>(.*?)</pubDate>", re.DOTALL)
RE_UPDATED = re.compile(r"<updated>(.*?)</updated>", re.DOTALL)

# ── Valid tags for output ───────────────────────────────────────────────────

VALID_TAGS = {
    "AI",
    "LLM",
    "Agent",
    "ML",
    "Rust",
    "OS",
    "GitHub",
    "Paper",
    "Tool",
    "Framework",
    "Research",
    "OpenSource",
    "DevTools",
    "NLP",
    "CV",
    "RL",
    "Data",
    "System",
}

REQUIRED_FIELDS = {
    "id",
    "title",
    "title_cn",
    "source",
    "source_url",
    "summary",
    "summary_cn",
    "tags",
    "status",
    "collected_at",
    "analyzed_at",
}


# ── CLI ─────────────────────────────────────────────────────────────────────


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments.

    Returns:
        Populated Namespace with sources, limit, dry_run, and verbose.
    """
    parser = argparse.ArgumentParser(description="Knowledge base automation pipeline")
    parser.add_argument(
        "--sources",
        type=str,
        default="github,rss",
        help="Comma-separated sources: github, rss (default: github,rss)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Max items to collect (default: 20)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run pipeline without writing article files to disk",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug-level logging output",
    )
    return parser.parse_args()


# ── Step 1: Collect ─────────────────────────────────────────────────────────


async def collect_github(limit: int) -> list[dict]:
    """Fetch trending repositories from the GitHub Search API.

    Queries multiple AI-related topics and merges results.  Uses the
    public search endpoint; unauthenticated calls are rate-limited to
    10 req/min.

    Args:
        limit: Maximum number of items to return.

    Returns:
        List of raw item dicts with keys: title, source_url, description,
        stars, language, topics, collected_at, source, raw_type.
    """
    items: list[dict] = []
    async with httpx.AsyncClient(
        timeout=30.0,
        headers={"Accept": "application/vnd.github.v3+json"},
    ) as client:
        for query in GITHUB_SEARCH_QUERIES:
            if len(items) >= limit:
                break
            url = "https://api.github.com/search/repositories"
            params = {
                "q": query,
                "sort": "stars",
                "order": "desc",
                "per_page": min(limit, 100),
            }
            logger.info("GitHub Search API: %s?q=%s", url, query)
            try:
                resp = await client.get(url, params=params)
                resp.raise_for_status()
                data = resp.json()
                for repo in data.get("items", []):
                    items.append(
                        {
                            "title": repo.get("full_name", ""),
                            "source_url": repo.get("html_url", ""),
                            "description": repo.get("description") or "",
                            "stars": repo.get("stargazers_count", 0),
                            "language": repo.get("language") or "",
                            "topics": repo.get("topics", []),
                            "collected_at": datetime.now(UTC).isoformat(),
                            "source": "github_trending",
                            "raw_type": "github_repo",
                        }
                    )
                logger.info(
                    "GitHub '%s' returned %d repos",
                    query,
                    len(data.get("items", [])),
                )
            except httpx.HTTPError as exc:
                logger.error("GitHub API error for '%s': %s", query, exc)
    return items[:limit]


async def collect_rss(limit: int) -> list[dict]:
    """Fetch articles from RSS/Atom feeds via httpx and regex parsing.

    Args:
        limit: Maximum number of items to return.

    Returns:
        List of raw item dicts with keys: title, source_url, description,
        published_at, collected_at, source, raw_type.
    """
    items: list[dict] = []
    async with httpx.AsyncClient(timeout=30.0) as client:
        for feed_url in RSS_FEEDS:
            if len(items) >= limit:
                break
            logger.info("RSS fetch: %s", feed_url)
            try:
                resp = await client.get(feed_url)
                resp.raise_for_status()
                parsed = parse_feed(resp.text, feed_url)
                for entry in parsed:
                    items.append(
                        {
                            "title": entry.get("title", ""),
                            "source_url": entry.get("link", ""),
                            "description": entry.get("description", ""),
                            "published_at": entry.get("published_at", ""),
                            "collected_at": datetime.now(UTC).isoformat(),
                            "source": ("hacker_news" if "hnrss" in feed_url else "rss"),
                            "raw_type": "rss_article",
                        }
                    )
                logger.info("RSS '%s' returned %d entries", feed_url, len(parsed))
            except httpx.HTTPError as exc:
                logger.error("RSS fetch error for '%s': %s", feed_url, exc)
    return items[:limit]


def parse_feed(xml_text: str, feed_url: str = "") -> list[dict]:
    """Parse RSS 2.0 or Atom XML content with regex.

    Args:
        xml_text: Raw XML / RSS / Atom string.
        feed_url: Source URL for logging context.

    Returns:
        List of parsed entry dicts with keys: title, link, description,
        published_at.
    """
    entries: list[dict] = []

    blocks = RE_ITEM.findall(xml_text)
    if not blocks:
        blocks = RE_ENTRY.findall(xml_text)

    for block in blocks:
        entry: dict = {}

        title_m = RE_TITLE.search(block)
        entry["title"] = _strip_tags(title_m.group(1).strip()) if title_m else ""

        link_m = RE_LINK.search(block) or RE_LINK_HREF.search(block)
        entry["link"] = link_m.group(1).strip() if link_m else ""

        desc_m = RE_DESCRIPTION.search(block) or RE_SUMMARY.search(block)
        entry["description"] = _strip_tags(desc_m.group(1).strip()) if desc_m else ""

        date_m = RE_PUBDATE.search(block) or RE_UPDATED.search(block)
        entry["published_at"] = date_m.group(1).strip() if date_m else ""

        entries.append(entry)

    logger.debug("Parsed %d entries from feed '%s'", len(entries), feed_url)
    return entries


def _strip_tags(text: str) -> str:
    """Remove HTML/XML tags from a string."""
    return re.sub(r"<[^>]+>", "", text).strip()


async def _save_raw(items: list[dict], source_label: str) -> None:
    """Persist raw collected data to ``knowledge/raw/``.

    Args:
        items: Raw collected item dicts.
        source_label: Label used in the output filename.
    """
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    filepath = RAW_DIR / f"{source_label}_{timestamp}.json"
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)
    logger.info("Saved %d raw items to %s", len(items), filepath)


# ── Step 2: Analyze ─────────────────────────────────────────────────────────

ANALYZE_PROMPT = """\
You are a technical content analyst. Analyze the item below and return a JSON object:

{{
    "title_cn": "Chinese translation of the title (keep it concise)",
    "summary": "English summary within 200 characters",
    "summary_cn": "Chinese summary within 200 characters",
    "tags": ["tag1", "tag2"],
    "quality_score": 0
}}

Valid tags: AI, LLM, Agent, ML, Rust, OS, GitHub, Paper, Tool, Framework,
Research, OpenSource, DevTools, NLP, CV, RL, Data, System.

Quality score: 90-100 exceptional, 70-89 solid, 50-69 average, <50 noise.

Content:

Title: {title}
URL: {source_url}
Description: {description}

Return ONLY the JSON object, no markdown fences, no extra text."""


async def analyze_item(item: dict, index: int = 0) -> dict:
    """Call LLM to analyze a single content item.

    Args:
        item: Raw item dict from the collect step.
        index: Item index for logging.

    Returns:
        The item dict augmented with title_cn, summary, summary_cn, tags,
        quality_score, and analyzed_at.
    """
    try:
        prompt = ANALYZE_PROMPT.format(
            title=item.get("title", ""),
            source_url=item.get("source_url", ""),
            description=item.get("description", ""),
        )
        response = await chat_with_retry(prompt, max_tokens=1024, temperature=0.3)
        content = response.content.strip()

        content = (
            content.removeprefix("```json")
            .removeprefix("```")
            .removesuffix("```")
            .strip()
        )

        analysis = json.loads(content)
        item["title_cn"] = analysis.get("title_cn", "")
        item["summary"] = analysis.get("summary", "")
        item["summary_cn"] = analysis.get("summary_cn", "")
        item["tags"] = analysis.get("tags", [])
        item["quality_score"] = int(analysis.get("quality_score", 0))
        item["analyzed_at"] = datetime.now(UTC).isoformat()
        logger.debug(
            "Analyzed [%d]: %s (score=%d)",
            index,
            item.get("title"),
            item["quality_score"],
        )
    except (json.JSONDecodeError, KeyError, ValueError) as exc:
        logger.warning(
            "LLM analysis failed [%d] '%s': %s",
            index,
            item.get("title"),
            exc,
        )
        item["title_cn"] = ""
        item["summary"] = ""
        item["summary_cn"] = ""
        item["tags"] = []
        item["quality_score"] = 0
        item["analyzed_at"] = datetime.now(UTC).isoformat()
    return item


async def analyze(items: list[dict]) -> list[dict]:
    """Analyze all collected items concurrently via LLM.

    Args:
        items: List of raw item dicts.

    Returns:
        Items augmented with LLM-generated analysis fields.
    """
    if not items:
        logger.warning("No items to analyze.")
        return []

    _check_api_key()

    logger.info("Analyzing %d items via LLM...", len(items))
    tasks = [analyze_item(item, i) for i, item in enumerate(items)]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    out: list[dict] = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logger.error("Analysis task %d failed: %s", i, result)
        else:
            out.append(result)
    return out


def _check_api_key() -> None:
    """Warn if no LLM API key is configured."""
    env_vars = (
        os.getenv("DEEPSEEK_API_KEY"),
        os.getenv("DASHSCOPE_API_KEY"),
        os.getenv("OPENAI_API_KEY"),
        os.getenv("LLM_API_KEY"),
    )
    if not any(env_vars):
        logger.warning(
            "No LLM API key found. Set DEEPSEEK_API_KEY, OPENAI_API_KEY, "
            "or LLM_API_KEY in your environment. Analysis will likely fail."
        )


# ── Step 3: Organize ────────────────────────────────────────────────────────


def organize(items: list[dict]) -> list[dict]:
    """Deduplicate, standardize format, and validate items.

    Deduplication is based on a SHA-256 hash of the source URL.  Only
    fields matching the standard knowledge-entry schema are kept.

    Args:
        items: List of analyzed item dicts.

    Returns:
        Clean, validated article dicts ready for persistence.
    """
    seen: set[str] = set()
    out: list[dict] = []

    for item in items:
        article_id = _generate_id(item)
        if article_id in seen:
            logger.debug("Duplicate skipped: %s", item.get("title"))
            continue
        seen.add(article_id)

        tags = item.get("tags", [])
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.split(",")]
        tags = [t for t in tags if t in VALID_TAGS]

        article = {
            "id": article_id,
            "title": item.get("title", ""),
            "title_cn": item.get("title_cn", ""),
            "source": item.get("source", "unknown"),
            "source_url": item.get("source_url", ""),
            "summary": _truncate(item.get("summary", ""), 200),
            "summary_cn": _truncate(item.get("summary_cn", ""), 200),
            "tags": tags,
            "status": "draft",
            "collected_at": item.get("collected_at", ""),
            "analyzed_at": item.get("analyzed_at", ""),
        }

        errors = validate(article)
        if errors:
            logger.warning("Validation failed for '%s': %s", article["title"], errors)
            continue

        out.append(article)

    logger.info("Organized %d articles (filtered from %d)", len(out), len(items))
    return out


def _generate_id(item: dict) -> str:
    """Generate a deterministic dedup ID from the source URL.

    Args:
        item: Item dict.

    Returns:
        Hex string (16 chars).
    """
    url = item.get("source_url", "")
    if url:
        return hashlib.sha256(url.encode()).hexdigest()[:16]
    return uuid4().hex[:16]


def _truncate(text: str, max_len: int) -> str:
    """Truncate text to *max_len* characters, appending ellipsis if cut.

    Args:
        text: Input string.
        max_len: Maximum character count.

    Returns:
        Truncated string.
    """
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "…"


def validate(article: dict) -> list[str]:
    """Check that an article dict contains all required fields.

    Args:
        article: Article dict to validate.

    Returns:
        List of missing field names (empty if valid).
    """
    return [f for f in REQUIRED_FIELDS if f not in article]


# ── Step 4: Save ────────────────────────────────────────────────────────────


def save(articles: list[dict], dry_run: bool = False) -> None:
    """Persist each article as a standalone JSON file.

    Files are written to ``knowledge/articles/``, named ``<id>.json``.

    Args:
        articles: List of validated article dicts.
        dry_run: If True, log only, do not write files.
    """
    ARTICLES_DIR.mkdir(parents=True, exist_ok=True)

    for article in articles:
        article_id = article["id"]
        filepath = ARTICLES_DIR / f"{article_id}.json"
        if dry_run:
            logger.info("[DRY-RUN] Would save: %s", filepath)
            continue
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(article, f, ensure_ascii=False, indent=2)
        logger.debug("Saved: %s", filepath)

    logger.info(
        "%s %d articles to %s",
        "[DRY-RUN] Would save" if dry_run else "Saved",
        len(articles),
        ARTICLES_DIR,
    )


# ── Pipeline runner ─────────────────────────────────────────────────────────


async def run_pipeline(args: argparse.Namespace) -> None:
    """Execute the full collect -> analyze -> organize -> save pipeline.

    Args:
        args: Parsed CLI arguments.
    """
    sources = [s.strip() for s in args.sources.split(",")]

    raw_items: list[dict] = []

    if "github" in sources:
        logger.info("=== Step 1: Collect from GitHub ===")
        github_items = await collect_github(args.limit)
        raw_items.extend(github_items)
        logger.info("GitHub collected: %d items", len(github_items))

    if "rss" in sources:
        logger.info("=== Step 1: Collect from RSS ===")
        rss_items = await collect_rss(args.limit)
        raw_items.extend(rss_items)
        logger.info("RSS collected: %d items", len(rss_items))

    if not raw_items:
        logger.warning("No items collected from sources: %s", args.sources)
        return

    await _save_raw(raw_items, "+".join(sources))

    logger.info("=== Step 2: Analyze ===")
    analyzed = await analyze(raw_items)

    logger.info("=== Step 3: Organize ===")
    articles = organize(analyzed)

    logger.info("=== Step 4: Save ===")
    save(articles, dry_run=args.dry_run)

    logger.info(
        "Pipeline complete. %d articles processed, %d saved.",
        len(articles),
        len(articles) if not args.dry_run else 0,
    )


# ── Entry point ─────────────────────────────────────────────────────────────


def main() -> None:
    """Parse arguments and run the async pipeline."""
    args = parse_args()

    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    asyncio.run(run_pipeline(args))


if __name__ == "__main__":
    main()
