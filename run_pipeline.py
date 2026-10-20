
import os
import argparse
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent
EXPORTS = ROOT / "exports"

parser = argparse.ArgumentParser(
    description="Run the synthetic REDCap trial pipeline."
)

parser.add_argument(
    "--offline",
    action="store_true",
    help="Use the latest saved export instead of calling REDCap."
)

args = parser.parse_args()

started = time.perf_counter()

print("=" * 60, flush=True)
print("REDCAP CLINICAL TRIAL DATA PIPELINE", flush=True)
print("=" * 60, flush=True)
print(
    "Started:",
    datetime.now(timezone.utc).isoformat(),
    flush=True
)
print(
    "Mode:",
    "OFFLINE" if args.offline else "LIVE API",
    flush=True
)


def run_step(name, command):
    print(f"\n{'=' * 60}", flush=True)
    print(name, flush=True)
    print("=" * 60, flush=True)

    subprocess.run(
        [sys.executable, *command],
        cwd=ROOT,
        check=True
    )

    print(f"{name}: PASSED", flush=True)


def export_snapshot():
    return {
        path.name: (
            path.stat().st_size,
            path.stat().st_mtime_ns
        )
        for path in EXPORTS.glob("trial_data_*.csv")
        if path.is_file()
    }


try:
    if args.offline:
        if not list(EXPORTS.glob("trial_data_*.csv")):
            raise FileNotFoundError(
                "No saved trial export found."
            )

        print(
            "OFFLINE MODE: Using existing export.",
            flush=True
        )

    else:
        before = export_snapshot()

        run_step(
            "STEP 1: REDCap data extraction",
            ["export_trial_data.py"]
        )

        after = export_snapshot()

        updated = {
            name
            for name, details in after.items()
            if before.get(name) != details
        }

        if not updated:
            raise RuntimeError(
                "No new or updated REDCap export detected."
            )

        latest = max(
            EXPORTS.glob("trial_data_*.csv"),
            key=lambda path: path.stat().st_mtime_ns
        )

        if latest.name not in updated:
            raise RuntimeError(
                "The latest CSV was not updated by "
                "this API execution."
            )

        print(
            "FRESH EXPORT VERIFIED:",
            latest.name,
            flush=True
        )


    # Select the dataset for this execution.
    external_input = os.getenv("TRIAL_DATA_FILE")

    if args.offline and external_input:
        selected_input = Path(external_input).resolve()

        if not selected_input.is_file():
            raise FileNotFoundError(
                f"Specified dataset not found: {selected_input}"
            )
    else:
        selected_input = max(
            EXPORTS.glob("trial_data_*.csv"),
            key=lambda path: path.stat().st_mtime_ns
        ).resolve()


    # Protect the live run against using an old export.
    if not args.offline:
        if selected_input.name not in updated:
            raise RuntimeError(
                "Selected input was not updated "
                "by the current API extraction."
            )

    os.environ["TRIAL_DATA_FILE"] = str(
        selected_input
    )

    print(
        "\nPINNED DATASET:",
        selected_input.name,
        flush=True
    )

    run_step(
        "STEP 2: Data quality validation",
        ["validate_trial_data.py"]
    )

    run_step(
        "STEP 3: Site reconciliation",
        ["reconcile_findings.py"]
    )

    run_step(
        "STEP 4: Dashboard generation",
        ["build_dashboard.py"]
    )

    run_step(
        "STEP 5: Automated tests",
        [
            "-m", "unittest",
            "discover", "-s", "tests", "-v"
        ]
    )

except (subprocess.CalledProcessError, FileNotFoundError, RuntimeError) as error:
    print("\nPIPELINE FAILED", flush=True)
    print("Reason:", error, flush=True)
    sys.exit(1)

elapsed = time.perf_counter() - started

print("\n" + "=" * 60)
print("PIPELINE COMPLETED SUCCESSFULLY")
print("=" * 60)

print(f"Execution time: {elapsed:.2f} seconds")
output_dir = Path(
    os.getenv("TRIAL_OUTPUT_DIR", str(EXPORTS))
).resolve()

print(f"Validated data: {output_dir}")
print(
    "Reconciliation:",
    output_dir / "reconciliation_report.csv"
)
print(
    "Dashboard:",
    output_dir / "quality_dashboard.html"
)
print("Automated tests: PASSED")
