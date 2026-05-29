"""Replay local Feishu scenario fixtures."""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from yinyo.scenario import replay_release_matrix, replay_scenarios


def main() -> int:
    parser = argparse.ArgumentParser(description="Replay Feishu runtime scenario fixtures")
    parser.add_argument("--path", default=str(ROOT / "examples" / "feishu_scenarios.json"))
    parser.add_argument("--corpus", default=str(ROOT / "corpus" / "harness" / "scenarios.v1.json"), help="Versioned local harness corpus")
    parser.add_argument("--matrix", action="store_true", help="Evaluate 3+6 release evidence matrix")
    args = parser.parse_args()

    output = replay_release_matrix(args.path, harness_corpus_path=args.corpus) if args.matrix else replay_scenarios(args.path, harness_corpus_path=args.corpus)
    print(json.dumps(output, ensure_ascii=False, indent=2))
    if args.matrix:
        return 0 if output["ok"] else 1
    if not all(item["passed"] for item in output):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
