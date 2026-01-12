import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


# Windows disallowed characters in filenames: <>:"/\|?*
INVALID_WINDOWS_CHARS = re.compile(r"[<>:\"/\\|?*]")


def _safe_filename(name: str, max_len: int = 180) -> str:
    name = str(name).strip()
    name = INVALID_WINDOWS_CHARS.sub("_", name)
    # Windows: no trailing dots/spaces
    name = name.rstrip(" .")
    if not name:
        name = "_"
    if len(name) > max_len:
        name = name[:max_len].rstrip(" .")
        if not name:
            name = "_"
    return name


def _load_json_text(path: Path) -> Optional[str]:
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        # Some files may have BOM or non-utf8; try utf-8-sig then fallback.
        try:
            text = path.read_text(encoding="utf-8-sig")
        except Exception:
            try:
                text = path.read_text(encoding="gb18030")
            except Exception:
                return None
    except Exception:
        return None

    if text.strip() == "":
        return ""
    return text


def _extract_problems(obj: Any) -> List[Dict[str, Any]]:
    # Case 1: top-level list
    if isinstance(obj, list):
        return [x for x in obj if isinstance(x, dict)]

    # Case 2: top-level dict
    if isinstance(obj, dict):
        # Common container keys
        for key in ("problems", "items", "data", "questions", "results"):
            value = obj.get(key)
            if isinstance(value, list):
                problems = [x for x in value if isinstance(x, dict)]
                if problems:
                    return problems

        # Heuristic: any list value with dict elements
        for value in obj.values():
            if isinstance(value, list) and any(isinstance(x, dict) for x in value):
                problems = [x for x in value if isinstance(x, dict)]
                if problems:
                    return problems

        # Single problem dict
        if "problem_id" in obj:
            return [obj]

    return []


def _get_problem_id(problem: Dict[str, Any]) -> Optional[str]:
    # Datasets may use different casing/conventions.
    for key in ("problem_id", "Problem_ID", "problemId", "ProblemId", "id", "ID"):
        if key in problem:
            value = problem.get(key)
            break
    else:
        return None
    if value is None:
        return None
    return str(value)


@dataclass
class SplitStats:
    files_total: int = 0
    files_empty: int = 0
    files_parse_failed: int = 0
    files_no_problems: int = 0
    problems_found: int = 0
    problems_written: int = 0
    problems_skipped_missing_id: int = 0
    outputs_collided: int = 0


def _iter_json_files(root: Path) -> Iterable[Path]:
    for path in root.rglob("*.json"):
        if path.is_file():
            yield path


def _choose_output_path(
    input_path: Path,
    output_dir: Path,
    problem_id: str,
    overwrite: bool,
) -> Tuple[Path, bool]:
    """Returns (output_path, collided)."""
    base_name = _safe_filename(problem_id)
    candidate = output_dir / f"{base_name}.json"

    if not candidate.exists() or overwrite:
        return candidate, candidate.exists() and not overwrite

    # Collision: add numeric suffix
    i = 2
    while True:
        candidate2 = output_dir / f"{base_name}_{i}.json"
        if not candidate2.exists():
            return candidate2, True
        i += 1


def split_file(
    path: Path,
    dry_run: bool,
    overwrite: bool,
    verbose: bool,
    stats: SplitStats,
) -> None:
    stats.files_total += 1

    text = _load_json_text(path)
    if text is None:
        stats.files_parse_failed += 1
        if verbose:
            print(f"[read-failed] {path}")
        return
    if text == "":
        stats.files_empty += 1
        return

    try:
        obj = json.loads(text)
    except Exception:
        stats.files_parse_failed += 1
        if verbose:
            print(f"[json-parse-failed] {path}")
        return

    # Treat trivial empties as empty
    if obj == [] or obj == {}:
        stats.files_empty += 1
        return

    problems = _extract_problems(obj)
    if not problems:
        stats.files_no_problems += 1
        if verbose:
            print(f"[no-problems] {path}")
        return

    stats.problems_found += len(problems)

    output_dir = path.parent

    for problem in problems:
        pid = _get_problem_id(problem)
        if not pid:
            stats.problems_skipped_missing_id += 1
            if verbose:
                print(f"[missing-problem_id] {path}")
            continue

        out_path, collided = _choose_output_path(
            input_path=path,
            output_dir=output_dir,
            problem_id=pid,
            overwrite=overwrite,
        )

        # If input already is the target (single-problem file), skip to avoid self-overwrite.
        # This protects reruns on folders that already contain split files.
        if out_path.resolve() == path.resolve() and len(problems) == 1:
            if verbose:
                print(f"[skip-existing-single] {path}")
            continue

        if collided:
            stats.outputs_collided += 1

        if verbose or dry_run:
            print(f"{path} -> {out_path}")

        if dry_run:
            continue

        try:
            out_path.write_text(
                json.dumps(problem, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            stats.problems_written += 1
        except Exception:
            # Keep going; report as parse_failed for simplicity
            stats.files_parse_failed += 1
            if verbose:
                print(f"[write-failed] {out_path}")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Split dataset JSON files into one-problem-per-file JSONs named by problem_id. "
            "Outputs are written into each source JSON's directory."
        )
    )
    parser.add_argument(
        "roots",
        nargs="*",
        help="Root directories to scan recursively for *.json.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be written, without writing files.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing problem_id.json if it exists. Default: auto-suffix on collisions.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Process at most N JSON files (0 = no limit).",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Verbose logging.",
    )

    args = parser.parse_args(argv)

    if not args.roots:
        print("No roots provided. Example:\n  python util/split_json_by_problem_id.py data/smp_100_verified_non-instead data/smp_100_verified_non-instead_and_non-question --dry-run")
        return 2

    stats = SplitStats()
    processed = 0

    for root_str in args.roots:
        root = Path(root_str)
        if not root.exists():
            print(f"[missing-root] {root}", file=sys.stderr)
            continue

        for path in _iter_json_files(root):
            split_file(
                path=path,
                dry_run=args.dry_run,
                overwrite=args.overwrite,
                verbose=args.verbose,
                stats=stats,
            )
            processed += 1
            if args.limit and processed >= args.limit:
                break
        if args.limit and processed >= args.limit:
            break

    print("\n=== Summary ===")
    print(f"files_total={stats.files_total}")
    print(f"files_empty={stats.files_empty}")
    print(f"files_parse_failed={stats.files_parse_failed}")
    print(f"files_no_problems={stats.files_no_problems}")
    print(f"problems_found={stats.problems_found}")
    if args.dry_run:
        print("problems_written=0 (dry-run)")
    else:
        print(f"problems_written={stats.problems_written}")
    print(f"problems_skipped_missing_id={stats.problems_skipped_missing_id}")
    print(f"outputs_collided={stats.outputs_collided} (auto-suffixed unless --overwrite)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
