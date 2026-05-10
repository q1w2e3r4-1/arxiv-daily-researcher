from __future__ import annotations

import os
import subprocess
import sys

from common import get_run_id


def run(cmd: list[str], env: dict[str, str]) -> None:
    print("+", " ".join(cmd))
    subprocess.run(cmd, check=True, env=env)


def main() -> None:
    run_id = get_run_id()
    env = os.environ.copy()
    env["EUROSYS_RUN_ID"] = run_id
    py = sys.executable
    run([py, "experiments/eurosys_2026_mlsys_eval/fetch_eurosys.py", "--run-id", run_id], env)
    run([py, "experiments/eurosys_2026_mlsys_eval/build_ground_truth.py", "--run-id", run_id], env)
    run([py, "experiments/eurosys_2026_mlsys_eval/run_eval.py", "--run-id", run_id], env)
    run([py, "experiments/eurosys_2026_mlsys_eval/report_eval.py", "--run-id", run_id], env)
    print(f"run_id={run_id}")


if __name__ == "__main__":
    main()
