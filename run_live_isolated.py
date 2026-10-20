"""Run the synthetic REDCap API extraction and reports in a fresh private run folder.

Requires existing export_trial_data.py and run_pipeline.py. Keep runs/ in .gitignore.
"""

import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RUNS = ROOT / "runs"
OUTPUT_NAMES = (
    "quality_findings_latest.csv",
    "reconciliation_report.csv",
    "quality_dashboard.html",
)


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def run_command(label, command, env, logfile):
    print(f"\n{label}", flush=True)
    with logfile.open("a", encoding="utf-8") as log:
        log.write(f"\n{label}\n")
        with subprocess.Popen(
            command,
            cwd=ROOT,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        ) as process:
            for line in process.stdout:
                print(line, end="", flush=True)
                log.write(line)
            code = process.wait()
    if code != 0:
        raise RuntimeError(f"{label} failed with exit code {code}")


def main():
    run_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
    run_dir = RUNS / run_id
    input_dir = run_dir / "input"
    output_dir = run_dir / "output"
    input_dir.mkdir(parents=True, exist_ok=False)
    output_dir.mkdir()
    logfile = run_dir / "pipeline.log"
    start = datetime.now(timezone.utc).isoformat()
    pinned = None
    error = None

    print("RUN ID:", run_id)
    print("Run folder:", run_dir)

    try:
        api_env = os.environ.copy()
        api_env.pop("TRIAL_DATA_FILE", None)
        api_env["TRIAL_OUTPUT_DIR"] = str(input_dir.resolve())

        run_command(
            "STEP 1: Live REDCap API export",
            [sys.executable, "-u", str(ROOT / "export_trial_data.py")],
            api_env,
            logfile,
        )

        exports = list(input_dir.glob("trial_data_*.csv"))
        if len(exports) != 1 or exports[0].stat().st_size == 0:
            raise RuntimeError("Expected exactly one nonempty fresh trial CSV")
        pinned = exports[0].resolve()

        pipeline_env = os.environ.copy()
        pipeline_env["TRIAL_DATA_FILE"] = str(pinned)
        pipeline_env["TRIAL_OUTPUT_DIR"] = str(output_dir.resolve())

        # Offline here means: analyse the CSV just obtained from the live API.
        run_command(
            "STEP 2: Isolated validation, reporting and tests",
            [sys.executable, "-u", str(ROOT / "run_pipeline.py"), "--offline"],
            pipeline_env,
            logfile,
        )

        for name in OUTPUT_NAMES:
            path = output_dir / name
            if not path.is_file() or path.stat().st_size == 0:
                raise RuntimeError(f"Missing or empty output: {name}")

    except Exception as exc:
        error = str(exc)
        print("RUN FAILED:", error)

    manifest = {
        "run_id": run_id,
        "mode": "isolated_live_api",
        "started_utc": start,
        "finished_utc": datetime.now(timezone.utc).isoformat(),
        "status": "failed" if error else "passed",
        "input_dataset": f"input/{pinned.name}" if pinned else None,
        "input_sha256": sha256_file(pinned) if pinned else None,
        "outputs": [
            f"output/{name}"
            for name in OUTPUT_NAMES
            if (output_dir / name).is_file()
        ],
        "error": error,
    }
    manifest_path = run_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    protected = [logfile, manifest_path]
    if pinned:
        protected.append(pinned)
    protected.extend(output_dir / name for name in OUTPUT_NAMES if (output_dir / name).is_file())

    hashes = {str(path.relative_to(run_dir)): sha256_file(path) for path in protected}
    (run_dir / "checksums.json").write_text(
        json.dumps(hashes, indent=2), encoding="utf-8"
    )
    for relative_path, expected_hash in hashes.items():
        if sha256_file(run_dir / relative_path) != expected_hash:
            raise RuntimeError(f"Checksum failed: {relative_path}")

    print("\nRUN SUMMARY")
    print("Status:", manifest["status"])
    print("Archive:", run_dir)
    print("Verified files:", len(hashes))
    if error:
        raise SystemExit(1)
    print("LIVE ISOLATED PIPELINE COMPLETED SUCCESSFULLY")


if __name__ == "__main__":
    main()
