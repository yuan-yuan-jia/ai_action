#!/usr/bin/env python3
"""Fetch GitHub Trending repos, filter by topic, output JSON to stdout.

Self-fetches trending page via urllib. Configurable via config.json.

Exit codes:
  0 — success (stdout has JSON array, possibly [])
  1 — error   (stderr has message, stdout has [])

No external dependencies (stdlib only).
"""

import json
import re
import sys
import time
import urllib.error
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

CONFIG_PATH = Path(__file__).parent / "config.json"

DEFAULT_CONFIG: dict[str, Any] = {
    "trending_url": "https://github.com/trending?since=weekly",
    "filter_topics": [
        "ai",
        "llm",
        "agent",
        "ml",
        "machine-learning",
        "deep-learning",
        "artificial-intelligence",
        "chatgpt",
        "gpt",
        "rag",
        "ai-agent",
        "agent-framework",
        "multi-agent",
        "os",
        "kernel",
        "operating-system",
        "rust",
        "rust-lang",
    ],
    "fallback_keywords": [
        "ai",
        "artificial intelligence",
        "machine learning",
        "deep learning",
        "llm",
        "large language model",
        "agent",
        "chatbot",
        "gpt",
        "transformer",
        "neural network",
        "natural language",
        "nlp",
        "rag",
        "retrieval augmented",
        "operating system",
        "kernel",
        "os",
        "rust",
    ],
    "timeout_seconds": 60,
    "max_stars_fetches": 30,
    "user_agent": "github-trending-skill/1.0",
}

_STAR_WEEKLY_RE = re.compile(r"([\d,]+)\s*stars?", re.IGNORECASE)
_TOTAL_STARS_ARIA_RE = re.compile(
    r'aria-label="([\d,]+)\s*users?\s*starred\s*this\s*repository"',
    re.IGNORECASE,
)
_TOTAL_STARS_COUNTER_RE = re.compile(
    r'<span[^>]*class="[^"]*\bCounter\b[^"]*"[^>]*>\s*([\d,]+)\s*</span>',
)
_TOTAL_STARS_STARGAZERS_RE = re.compile(
    r'href="/[^/]+/[^/]+/stargazers"[^>]*>[\s\S]*?([\d,]+)',
)


def _log_error(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def _output_json(data: object) -> None:
    json.dump(data, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    sys.stdout.flush()


def _output_empty() -> None:
    _output_json([])


def _load_config() -> dict[str, Any]:
    config = dict(DEFAULT_CONFIG)
    if CONFIG_PATH.is_file():
        try:
            with open(CONFIG_PATH, encoding="utf-8") as f:
                overrides = json.load(f)
            config.update(overrides)
        except (json.JSONDecodeError, OSError) as exc:
            _log_error(f"WARNING: Failed to load config ({exc}), using defaults")
    return config


def _http_get(url: str, timeout: int, user_agent: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": user_agent})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


class TrendingParser(HTMLParser):
    """Extract repo info from GitHub Trending HTML."""

    def __init__(self) -> None:
        super().__init__()
        self.repos: list[dict] = []
        self._repo: dict | None = None
        self._state: str | None = None
        self._star_buf: str = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_d = dict(attrs)
        classes = set(attrs_d.get("class", "").split())

        if tag == "article" and "Box-row" in classes:
            self._repo = {
                "name": "",
                "url": "",
                "stars": 0,
                "stars_this_week": 0,
                "topics": [],
                "description": "",
            }
            self._state = None
            self._star_buf = ""
            return

        if self._repo is None:
            return

        if tag == "h2":
            self._state = "h2"

        elif tag == "a":
            href = attrs_d.get("href", "")
            if href and href.startswith("/topics/"):
                topic = href.rsplit("/", 1)[-1]
                if topic:
                    self._repo["topics"].append(topic)
            elif self._state == "h2" and href:
                repo_path = href.strip("/")
                parts = repo_path.split("/")
                if len(parts) == 2 and parts[0] and parts[1]:
                    self._repo["name"] = repo_path
                    self._repo["url"] = f"https://github.com/{repo_path}"

        elif tag == "p" and "f4" not in classes:
            self._state = "desc"

        elif tag == "span" and "float-sm-right" in classes:
            self._state = "stars"
            self._star_buf = ""

    def handle_endtag(self, tag: str) -> None:
        if tag == "article" and self._repo is not None:
            if self._repo["name"]:
                self.repos.append(self._repo)
            self._repo = None
            self._state = None
            return

        if self._repo is None:
            return

        if tag in {"h2", "p"} and self._state in {"h2", "desc"}:
            self._state = None

        elif tag == "span" and self._state == "stars":
            match = _STAR_WEEKLY_RE.search(self._star_buf)
            if match:
                self._repo["stars_this_week"] = int(match.group(1).replace(",", ""))
            self._state = None
            self._star_buf = ""

    def handle_data(self, data: str) -> None:
        if self._repo is None:
            return
        text = data.strip()
        if not text:
            return

        if self._state == "desc":
            sep = " " if self._repo["description"] else ""
            self._repo["description"] += sep + text

        elif self._state == "stars":
            self._star_buf += " " + text


def _topic_match(repo: dict, filter_topics: list[str]) -> bool:
    topics_set = frozenset(t.lower() for t in filter_topics)
    return bool({t.lower() for t in repo["topics"]} & topics_set)


def _text_match(repo: dict, fallback_keywords: list[str]) -> bool:
    text = f"{repo['name']} {repo['description']}".lower()
    return any(kw in text for kw in fallback_keywords)


def _filter_repos(
    repos: list[dict],
    filter_topics: list[str],
    fallback_keywords: list[str],
) -> list[dict]:
    seen: set[str] = set()
    result: list[dict] = []

    for repo in repos:
        if repo["url"] in seen:
            continue
        if _topic_match(repo, filter_topics) or _text_match(repo, fallback_keywords):
            seen.add(repo["url"])
            result.append(repo)

    return result


def _fetch_total_stars(
    owner: str, repo_name: str, timeout: int, user_agent: str
) -> int:
    url = f"https://github.com/{owner}/{repo_name}"
    html = _http_get(url, timeout, user_agent)

    for pattern in [
        _TOTAL_STARS_ARIA_RE,
        _TOTAL_STARS_COUNTER_RE,
        _TOTAL_STARS_STARGAZERS_RE,
    ]:
        match = pattern.search(html)
        if match:
            return int(match.group(1).replace(",", ""))

    return 0


def _enrich_total_stars(
    repos: list[dict],
    timeout: int,
    user_agent: str,
    max_fetches: int,
) -> None:
    deadline = time.monotonic() + timeout * 0.7  # leave room for other work
    fetched = 0

    for repo in repos:
        if fetched >= max_fetches:
            break
        if time.monotonic() > deadline:
            _log_error(
                "WARNING: total-stars fetch deadline exceeded "
                f"({fetched}/{max_fetches})"
            )
            break

        parts = repo["name"].split("/", 1)
        if len(parts) != 2:
            continue

        owner, repo_name = parts
        try:
            repo["stars"] = _fetch_total_stars(
                owner,
                repo_name,
                timeout=max(3, int(timeout * 0.1)),
                user_agent=user_agent,
            )
        except Exception as exc:
            _log_error(f"WARNING: failed to fetch stars for {repo['name']}: {exc}")
            repo["stars"] = 0
        fetched += 1


def main() -> int:
    config = _load_config()

    url = config["trending_url"]
    timeout = int(config["timeout_seconds"])
    user_agent = str(config["user_agent"])
    filter_topics = [str(t).lower() for t in config["filter_topics"]]
    fallback_keywords = [str(k).lower() for k in config["fallback_keywords"]]
    max_stars_fetches = int(config["max_stars_fetches"])

    try:
        html = _http_get(url, timeout, user_agent)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        _log_error(f"ERROR: Failed to fetch {url}: {exc}")
        _output_empty()
        return 1

    parser = TrendingParser()
    parser.feed(html)

    if not parser.repos:
        _log_error(
            "WARNING: No repos parsed from trending page "
            "(HTML structure may have changed)"
        )
        _output_empty()
        return 0

    filtered = _filter_repos(parser.repos, filter_topics, fallback_keywords)

    if filtered:
        _enrich_total_stars(filtered, timeout, user_agent, max_stars_fetches)
        filtered.sort(key=lambda r: r["stars_this_week"], reverse=True)

    _output_json(filtered)
    return 0


if __name__ == "__main__":
    sys.exit(main())
