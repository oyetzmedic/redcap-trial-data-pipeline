
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent
FIXTURE = ROOT / "tests" / "fixtures" / "synthetic_trial.csv"
RUNS = ROOT / "runs"


def main():
    if not FIXTURE.is_file():
        raise FileNotFoundError(
            f"Synthetic fixture missing: {FIXTURE}"
        )

    run_id = datetime.now(timezone.utc).strftime(
        "demo_%Y%m%d_%H%M%S_%f"
    )

    run_dir = RUNS / run_id
    input_dir = run_dir / "input"
    output_dir = run_dir / "output"

    input_dir.mkdir(parents=True)
    output_dir.mkdir()

    dataset = input_dir / FIXTURE.name
    shutil.copy2(FIXTURE, dataset)

    env = os.environ.copy()
    env["TRIAL_DATA_FILE"] = str(dataset.resolve())
    env["TRIAL_OUTPUT_DIR"] = str(output_dir.resolve())

    steps = [
        ("Validation", ["validate_trial_data.py"]),
        ("Reconciliation", ["reconcile_findings.py"]),
        ("Dashboard", ["build_dashboard.py"]),
        (
            "Automated tests",
            ["-m", "unittest", "discover", "-s", "tests", "-v"]
        ),
    ]

    print("=" * 55)
    print("SYNTHETIC REDCAP DATA QUALITY DEMONSTRATION")
    print("=" * 55)
    print("Dataset:", dataset)
    print("Output:", output_dir)

    for title, command in steps:
        print(f"\nSTEP: {title}", flush=True)

        subprocess.run(
            [sys.executable, *command],
            cwd=ROOT,
            env=env,
            check=True
        )

    dashboard = output_dir / "quality_dashboard.html"

    if not dashboard.is_file():
        raise FileNotFoundError(dashboard)

    print("\n" + "=" * 55)
    print("SYNTHETIC DEMONSTRATION COMPLETED SUCCESSFULLY")
    print("=" * 55)
    print("Dashboard:", dashboard)
    print("Run folder:", run_dir)


if __name__ == "__main__":
    main()
