#!/usr/bin/env python3
"""Validate knowledge article JSON files against the project schema.

Usage:
    python hooks/validate_json.py <json_file> [json_file2 ...]
    python hooks/validate_json.py knowledge/articles/*.json
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

REQUIRED_FIELDS: dict[str, type] = {
    "id": str,
    "title": str,
    "source_url": str,
    "summary": str,
    "tags": list,
    "status": str,
}

VALID_STATUSES = frozenset({"draft", "review", "published", "archived"})

ID_PATTERN = re.compile(r"^[a-z_]+-\d{8}-\d{3}$")

URL_PATTERN = re.compile(r"^https?://\S+")

VALID_AUDIENCES = frozenset({"beginner", "intermediate", "advanced"})

SUMMARY_MIN_LENGTH = 20
SCORE_MIN = 1
SCORE_MAX = 10


def _has_glob_chars(s: str) -> bool:
    """Check if a string contains shell glob characters."""
    return bool(set("*?[]") & set(s))


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


def validate_file(filepath: Path) -> list[str]:
    """Run all validation checks on a single JSON file.

    Returns a list of error message strings (empty means valid).
    """
    errors: list[str] = []

    # --- 1. Parse JSON ---
    try:
        raw_text = filepath.read_text(encoding="utf-8")
    except OSError as exc:
        return [f"Cannot read file: {exc}"]

    try:
        data: dict[str, Any] = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        lines = raw_text.splitlines()
        lineno = exc.lineno - 1
        context = ""
        if 0 <= lineno < len(lines):
            context = f": {lines[lineno].strip()}"
        return [
            f"Invalid JSON at line {exc.lineno}, "
            f"column {exc.colno}: {exc.msg}{context} "
            f"(hint: check for unescaped newlines or tab characters inside strings)"
        ]

    if not isinstance(data, dict):
        return ["Root value must be a JSON object (dict)"]

    # --- 2. Required fields existence + types ---
    for field, expected_type in REQUIRED_FIELDS.items():
        if field not in data:
            errors.append(f"Missing required field: {field!r}")
            continue
        value = data[field]
        if not isinstance(value, expected_type):
            errors.append(
                f"Field {field!r}: expected {expected_type.__name__}, "
                f"got {type(value).__name__}"
            )

    # --- 3. ID format: {source}-{YYYYMMDD}-{NNN} ---
    if "id" in data and isinstance(data["id"], str):
        if not ID_PATTERN.match(data["id"]):
            errors.append(
                f"Invalid id format: {data['id']!r} "
                f"(expected {{source}}-{{YYYYMMDD}}-{{NNN}}, "
                f"e.g. github-20260317-001)"
            )

    # --- 4. Status ---
    if "status" in data and isinstance(data["status"], str):
        if data["status"] not in VALID_STATUSES:
            errors.append(
                f"Invalid status: {data['status']!r} "
                f"(must be one of: {', '.join(sorted(VALID_STATUSES))})"
            )

    # --- 5. URL format ---
    if "source_url" in data and isinstance(data["source_url"], str):
        if not URL_PATTERN.match(data["source_url"]):
            errors.append(f"Invalid URL format: {data['source_url']!r}")

    # --- 6. Summary minimum length ---
    if "summary" in data and isinstance(data["summary"], str):
        if len(data["summary"]) < SUMMARY_MIN_LENGTH:
            errors.append(
                f"Summary too short: {len(data['summary'])} chars "
                f"(minimum {SUMMARY_MIN_LENGTH})"
            )

    # --- 7. Tags at least 1 ---
    if "tags" in data and isinstance(data["tags"], list):
        if len(data["tags"]) == 0:
            errors.append("Tags list is empty (at least 1 required)")

    # --- 8. Optional: score in 1-10 ---
    if "score" in data:
        score = data["score"]
        if not isinstance(score, int | float):
            errors.append(
                f"Field 'score': expected int/float, got {type(score).__name__}"
            )
        elif not (SCORE_MIN <= score <= SCORE_MAX):
            errors.append(
                f"Field 'score': value {score} out of range [{SCORE_MIN}, {SCORE_MAX}]"
            )

    # --- 9. Optional: audience ---
    if "audience" in data:
        audience = data["audience"]
        if not isinstance(audience, str):
            errors.append(
                f"Field 'audience': expected str, got {type(audience).__name__}"
            )
        elif audience not in VALID_AUDIENCES:
            errors.append(
                f"Field 'audience': {audience!r} "
                f"(must be one of: {', '.join(sorted(VALID_AUDIENCES))})"
            )

    return errors


def format_error_list(filepath: Path, errors: list[str]) -> str:
    """Format a single file's errors for display."""
    lines = [f"\n  {filepath}"]
    for err in errors:
        lines.append(f"    - {err}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Validate knowledge article JSON files.",
    )
    parser.add_argument(
        "files",
        nargs="+",
        help="JSON file paths or glob patterns (e.g. *.json)",
    )
    args = parser.parse_args(argv)

    json_files = collect_json_files(args.files)

    if not json_files:
        print("Validation OK (no JSON files found)")
        sys.exit(0)

    total = len(json_files)
    passed = 0
    failed = 0
    all_errors: list[str] = []

    for filepath in json_files:
        errors = validate_file(filepath)
        if errors:
            failed += 1
            all_errors.append(format_error_list(filepath, errors))
        else:
            passed += 1

    # --- Summary ---
    print()
    print(f"{'=' * 60}")
    print(f"  Summary: {total} file(s) checked")
    print(f"    Passed: {passed}")
    print(f"    Failed: {failed}")
    print(f"{'=' * 60}")

    if all_errors:
        print()
        print("Errors:")
        print("\n".join(all_errors))
        print()
        sys.exit(1)
    else:
        print("\nValidation OK\n")
        sys.exit(0)


if __name__ == "__main__":
    main()
