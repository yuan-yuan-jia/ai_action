#!/usr/bin/env python3
"""Quality assessment for knowledge article JSON files across 5 dimensions.

Usage:
    python hooks/check_quality.py <json_file> [json_file2 ...]
    python hooks/check_quality.py knowledge/articles/*.json
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VALID_STATUSES = frozenset({"draft", "review", "published", "archived"})

ID_PATTERN = re.compile(r"^[a-z_]+-\d{8}-\d{3}$")

URL_PATTERN = re.compile(r"^https?://\S+")

TIMESTAMP_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}")

VALID_TAGS = frozenset(
    {
        "AI",
        "LLM",
        "Agent",
        "ML",
        "Rust",
        "OS",
        "OpenSource",
        "Research",
        "Tools",
        "Framework",
        "Deployment",
        "NLP",
        "ComputerVision",
        "Embedding",
        "RAG",
        "Inference",
        "Training",
        "Fine-tuning",
        "Multimodal",
        "Security",
        "Performance",
        "Optimization",
        "Benchmark",
        "API",
        "CLI",
        "Database",
    }
)

TECH_KEYWORDS = frozenset(
    {
        "AI",
        "LLM",
        "agent",
        "machine learning",
        "deep learning",
        "neural network",
        "transformer",
        "GPT",
        "inference",
        "training",
        "fine-tuning",
        "RAG",
        "retrieval",
        "vector",
        "embedding",
        "prompt",
        "RLHF",
        "GPU",
        "Rust",
        "OS",
        "kernel",
        "optimization",
        "benchmark",
        "framework",
        "pipeline",
        "deployment",
        "API",
        "architecture",
        "algorithm",
        "dataset",
        "model",
        "token",
        "multimodal",
        "diffusion",
        "quantization",
    }
)

BUZZWORDS_CN = frozenset(
    {
        "赋能",
        "抓手",
        "闭环",
        "打通",
        "全链路",
        "底层逻辑",
        "颗粒度",
        "对齐",
        "拉通",
        "沉淀",
        "强大的",
    }
)

BUZZWORDS_EN = frozenset(
    {
        "groundbreaking",
        "revolutionary",
        "game-changing",
        "cutting-edge",
        "paradigm-shifting",
        "disruptive",
        "best-in-class",
        "world-class",
        "state-of-the-art",
        "next-generation",
        "bleeding-edge",
        "unprecedented",
    }
)

# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class DimensionScore:
    """Score for a single quality dimension."""

    name: str
    name_cn: str
    score: int
    max_score: int


@dataclass
class QualityReport:
    """Quality assessment result for a single article."""

    filepath: Path
    total: int
    max_total: int
    dimensions: list[DimensionScore] = field(default_factory=list)
    grade: str = "C"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _has_glob_chars(s: str) -> bool:
    """Check if a string contains shell glob characters."""
    return bool(set("*?[]") & set(s))


def _extract_all_text(data: dict[str, Any]) -> str:
    """Extract all string values from the JSON object for scanning."""
    parts: list[str] = []
    for value in data.values():
        if isinstance(value, str):
            parts.append(value)
    return " ".join(parts)


# ---------------------------------------------------------------------------
# File collection
# ---------------------------------------------------------------------------


def collect_json_files(paths: list[str]) -> list[Path]:
    """Resolve file paths and glob patterns to a sorted list of JSON files."""
    result: list[Path] = []
    seen: set[Path] = set()

    for raw in paths:
        pattern = Path(raw)
        if _has_glob_chars(str(pattern)):
            matches = sorted(pattern.parent.glob(pattern.name))
        else:
            matches = [pattern]

        for p in matches:
            resolved = p.resolve()
            if resolved not in seen:
                seen.add(resolved)
                result.append(resolved)

    return result


# ---------------------------------------------------------------------------
# Dimension scorers (each returns int in [0, max_score])
# ---------------------------------------------------------------------------


def _score_summary_quality(data: dict[str, Any]) -> int:
    """Score summary quality (max 25).

    >= 50 chars = full base + keyword bonus.
    >= 20 chars = partial base + keyword bonus.
    Contains technical keywords = extra bonus (capped at 5).
    """
    summary = data.get("summary", "")
    summary_cn = data.get("summary_cn", "")

    if not isinstance(summary, str) and not isinstance(summary_cn, str):
        return 0

    text = f"{summary} {summary_cn}"
    length = len(text)

    if length >= 50:
        base = 20
    elif length >= 20:
        base = 12
    else:
        base = 0

    keyword_hits = sum(1 for kw in TECH_KEYWORDS if kw.lower() in text.lower())
    bonus = min(keyword_hits, 5)

    return min(base + bonus, 25)


def _score_technical_depth(data: dict[str, Any]) -> int:
    """Score technical depth based on the 'score' field (max 25).

    Maps score 1-10 linearly to 0-25.  No score field → 0.
    """
    raw = data.get("score")
    if raw is None or not isinstance(raw, int | float):
        return 0
    if raw < 1 or raw > 10:
        return 0
    return round((raw - 1) * 25 / 9)


def _score_format_spec(data: dict[str, Any]) -> int:
    """Score format specification (max 20).

    5 items × 4 points each: id, title, source_url, status, timestamp.
    """
    points = 0

    if isinstance(data.get("id"), str) and ID_PATTERN.match(data["id"]):
        points += 4

    title = data.get("title")
    if isinstance(title, str) and title.strip():
        points += 4

    source_url = data.get("source_url")
    if isinstance(source_url, str) and URL_PATTERN.match(source_url):
        points += 4

    if data.get("status") in VALID_STATUSES:
        points += 4

    for ts_field in ("collected_at", "analyzed_at"):
        ts = data.get(ts_field)
        if isinstance(ts, str) and TIMESTAMP_PATTERN.match(ts):
            points += 4
            break

    return points


def _score_tag_precision(data: dict[str, Any]) -> int:
    """Score tag precision (max 15).

    1-3 valid tags = optimal (15).  4-5 = -3.  >5 or 0 = -6.
    Each invalid tag = -3 (floor 0).
    """
    tags = data.get("tags", [])
    if not isinstance(tags, list):
        return 0

    total = len(tags)
    if total == 0:
        return 0

    valid_count = sum(1 for t in tags if t in VALID_TAGS)

    if total <= 3:
        base = 15
    elif total <= 5:
        base = 12
    else:
        base = 9

    penalty = (total - valid_count) * 3
    return max(base - penalty, 0)


def _score_buzzword_detection(data: dict[str, Any]) -> int:
    """Score buzzword detection (max 15).

    Start at 15, -3 per unique buzzword found (Chinese or English).
    """
    text = _extract_all_text(data)

    found: set[str] = set()
    for word in BUZZWORDS_CN:
        if word in text:
            found.add(word)
    text_lower = text.lower()
    for word in BUZZWORDS_EN:
        if word in text_lower:
            found.add(word)

    penalty = len(found) * 3
    return max(15 - penalty, 0)


# ---------------------------------------------------------------------------
# Assessment
# ---------------------------------------------------------------------------

_GRADE_THRESHOLDS = [
    (80, "A"),
    (60, "B"),
    (0, "C"),
]


def _total_to_grade(total: int) -> str:
    """Map a total score to a letter grade."""
    for threshold, grade in _GRADE_THRESHOLDS:
        if total >= threshold:
            return grade
    return "C"


def assess_file(filepath: Path, data: dict[str, Any]) -> QualityReport:
    """Run all 5 dimension scorers and build a QualityReport."""
    dimensions = [
        DimensionScore(
            name="summary_quality",
            name_cn="摘要质量",
            score=_score_summary_quality(data),
            max_score=25,
        ),
        DimensionScore(
            name="technical_depth",
            name_cn="技术深度",
            score=_score_technical_depth(data),
            max_score=25,
        ),
        DimensionScore(
            name="format_spec",
            name_cn="格式规范",
            score=_score_format_spec(data),
            max_score=20,
        ),
        DimensionScore(
            name="tag_precision",
            name_cn="标签精度",
            score=_score_tag_precision(data),
            max_score=15,
        ),
        DimensionScore(
            name="buzzword_detection",
            name_cn="空洞词检测",
            score=_score_buzzword_detection(data),
            max_score=15,
        ),
    ]

    total = sum(d.score for d in dimensions)
    return QualityReport(
        filepath=filepath,
        total=total,
        max_total=100,
        dimensions=dimensions,
        grade=_total_to_grade(total),
    )


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def _render_bar(score: int, max_score: int, width: int = 20) -> str:
    """Render a simple ASCII progress bar."""
    filled = round(score / max_score * width)
    filled = max(0, min(filled, width))
    return f"[{'#' * filled}{'·' * (width - filled)}]"


def _render_report(report: QualityReport) -> str:
    """Format a single QualityReport for display."""
    lines: list[str] = []
    header = (
        f"  {report.filepath.name}  [{report.grade}]  "
        f"{report.total} / {report.max_total}"
    )
    width = max(len(header) + 4, 60)
    lines.append("─" * width)
    lines.append(header)
    lines.append("─" * width)

    for dim in report.dimensions:
        bar = _render_bar(dim.score, dim.max_score)
        label = f"{dim.name_cn} ({dim.name})"
        line = f"  {label:<36s} {bar}  {dim.score:>2} / {dim.max_score:<2}"
        # Keep line length reasonable
        lines.append(line)

    lines.append("─" * width)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Quality-check knowledge article JSON files.",
    )
    parser.add_argument(
        "files",
        nargs="+",
        help="JSON file paths or glob patterns (e.g. *.json)",
    )
    args = parser.parse_args(argv)

    json_files = collect_json_files(args.files)

    if not json_files:
        print("No JSON files found")
        sys.exit(0)

    total_files = len(json_files)
    reports: list[QualityReport] = []

    for idx, filepath in enumerate(json_files, start=1):
        print(f"[{idx}/{total_files}] Processing: {filepath.name}")

        try:
            raw = filepath.read_text(encoding="utf-8")
        except OSError as exc:
            logger.error("Cannot read %s: %s", filepath, exc)
            continue

        try:
            data: dict[str, Any] = json.loads(raw)
        except json.JSONDecodeError as exc:
            logger.error("Invalid JSON in %s: %s", filepath, exc)
            continue

        if not isinstance(data, dict):
            logger.error("Root value in %s is not a JSON object", filepath)
            continue

        reports.append(assess_file(filepath, data))

    # --- Summary output ---
    print()
    print(f"{'=' * 60}")
    print(f"  Quality Check:  {total_files} file(s) processed")
    print(f"{'=' * 60}")

    a_b_count = sum(1 for r in reports if r.grade in ("A", "B"))
    c_count = sum(1 for r in reports if r.grade == "C")
    print(f"  Passed (A+B): {a_b_count}    Failed (C): {c_count}")
    print(f"{'=' * 60}")
    print()

    for report in reports:
        print(_render_report(report))

    if c_count > 0:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
