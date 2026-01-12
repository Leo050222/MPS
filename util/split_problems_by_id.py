#!/usr/bin/env python3
"""Split a dataset JSON (list of problem records) into one JSON per Problem_ID.

Input format (expected):
- Top-level JSON array
- Each element is an object containing an integer field `Problem_ID`

Output:
- Creates an output directory
- Writes one file per record: Problem_<Problem_ID>.json (or configurable pattern)

This script preserves Unicode and pretty-prints deterministically.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any


def _safe_int(value: Any) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    raise ValueError(f"Problem_ID must be int-like, got: {value!r}")


def split_json_by_problem_id(input_path: Path, output_dir: Path, overwrite: bool) -> tuple[int, int]:
    raw = input_path.read_text(encoding="utf-8")
    data = json.loads(raw)

    if not isinstance(data, list):
        raise ValueError("Top-level JSON must be a list/array.")

    output_dir.mkdir(parents=True, exist_ok=True)

    seen_ids: set[int] = set()
    written = 0

    for idx, record in enumerate(data):
        if not isinstance(record, dict):
            raise ValueError(f"Element {idx} is not an object/dict.")
        if "Problem_ID" not in record:
            raise ValueError(f"Element {idx} missing Problem_ID.")

        pid = _safe_int(record["Problem_ID"])
        if pid in seen_ids:
            raise ValueError(f"Duplicate Problem_ID detected: {pid}")
        seen_ids.add(pid)

        out_path = output_dir / f"{pid}.json"
        # Safety: avoid clobbering the input file if output_dir == input dir
        if out_path.resolve() == input_path.resolve():
            raise ValueError(
                f"Output path would overwrite input file for Problem_ID={pid}: {out_path}"
            )
        if out_path.exists() and not overwrite:
            raise FileExistsError(f"Refusing to overwrite existing file: {out_path}")

        out_path.write_text(
            json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        written += 1

    return (len(data), written)


def main() -> None:
    parser = argparse.ArgumentParser(description="Split a problems JSON file into one JSON per Problem_ID")
    parser.add_argument("--input", "-i", type=Path, required=True, help="Path to input JSON file")
    parser.add_argument(
        "--output-dir",
        "-o",
        type=Path,
        required=True,
        help="Directory to write per-problem JSON files",
    )
    parser.add_argument("--overwrite", action="store_true", help="Overwrite output files if they exist")

    args = parser.parse_args()

    input_path: Path = args.input
    output_dir: Path = args.output_dir

    if not input_path.exists():
        raise FileNotFoundError(f"Input not found: {input_path}")

    total, written = split_json_by_problem_id(input_path, output_dir, overwrite=args.overwrite)
    print(f"Read {total} records; wrote {written} files to {output_dir}")


if __name__ == "__main__":
    main()
