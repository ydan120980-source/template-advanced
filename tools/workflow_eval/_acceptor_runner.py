"""Plain-script acceptor runner.

Executed as a subprocess so candidate imports and monkeypatches stay fully
isolated from the grading host process:

    python tools/workflow_eval/_acceptor_runner.py <task_id> <candidate_root>

Prints one JSON verdict object on stdout. Exit code: 0 ACCEPT, 1 REJECT,
2 BLOCKED. A BLOCKED result means the acceptor could not run (infrastructure
failure); it is never valid evidence that a candidate implements or lacks
the target behavior.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

RUNNER_DIR = Path(__file__).resolve().parent
if str(RUNNER_DIR) not in sys.path:
    sys.path.insert(0, str(RUNNER_DIR))

import acceptors  # noqa: E402 - sibling module of this plain-script runner


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(
            json.dumps(
                {
                    "status": "BLOCKED",
                    "verdict": "BLOCKED",
                    "acceptor_status": "BLOCKED",
                    "message": "usage: _acceptor_runner.py <task_id> <candidate_root>",
                    "scenarios": [],
                }
            )
        )
        return 2
    task_id, candidate_root = argv[1], Path(argv[2])
    if not candidate_root.is_dir():
        print(
            json.dumps(
                {
                    "status": "BLOCKED",
                    "verdict": "BLOCKED",
                    "acceptor_status": "BLOCKED",
                    "message": f"candidate root is not a directory: {candidate_root}",
                    "scenarios": [],
                }
            )
        )
        return 2
    try:
        report = acceptors.run_acceptor(task_id, candidate_root)
    except BaseException as exc:  # noqa: BLE001 - infrastructure boundary
        # SystemExit included: the eval harness raises SystemExit for builder
        # failures, and an escape from the acceptor is infrastructure-level,
        # never valid candidate evidence.
        print(
            json.dumps(
                {
                    "task_id": task_id,
                    "verdict": "BLOCKED",
                    "acceptor_status": "BLOCKED",
                    "status": "BLOCKED",
                    "message": f"acceptor could not run: {type(exc).__name__}: {exc}",
                    "scenarios": [],
                }
            )
        )
        return 2
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    if report.get("verdict") == "ACCEPT":
        return 0
    if report.get("verdict") == "BLOCKED":
        return 2
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
