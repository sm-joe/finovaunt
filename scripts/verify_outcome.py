"""CLI: verify outcomes from baseline, post-change, and change evidence JSON."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

# Support running this file directly from the repository root.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.utils.outcome_verification import build_outcome_verification  # noqa: E402


def _read_json(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            value = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read valid JSON from {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object in {path}")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", required=True, type=Path, help="Baseline cost_evidence.json")
    parser.add_argument("--after", required=True, type=Path, help="Post-change cost_evidence.json")
    parser.add_argument("--change", required=True, type=Path, help="Approved deployment evidence JSON")
    parser.add_argument("--output", type=Path, default=Path("outcome_verification.json"))
    args = parser.parse_args()

    try:
        report = build_outcome_verification(
            _read_json(args.baseline),
            _read_json(args.after),
            _read_json(args.change),
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.output.with_suffix(args.output.suffix + ".tmp")
        with temporary.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(report, handle, indent=2, sort_keys=True, allow_nan=False)
            handle.write("\n")
        temporary.replace(args.output)
    except (ValueError, OSError) as exc:
        print(f"Outcome verification failed: {exc}", file=sys.stderr)
        return 2

    print(f"Outcome report written: {args.output}")
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
