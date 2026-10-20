
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
EXPORTS = ROOT / "exports"
RUNS = ROOT / "runs"

def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

def main():
    sources = list(EXPORTS.glob("trial_data_*.csv"))
    if not sources:
        raise FileNotFoundError("No saved REDCap export.")

    source = max(
        sources,
        key=lambda p: p.stat().st_mtime_ns
    )

    run_id = datetime.now(timezone.utc).strftime(
        "%Y%m%d_%H%M%S_%f"
    )

    run_dir = RUNS / run_id
    input_dir = run_dir / "input"
    output_dir = run_dir / "output"

    input_dir.mkdir(parents=True)
    output_dir.mkdir()

    pinned = input_dir / source.name
    shutil.copy2(source, pinned)

    source_hash = sha256_file(source)
    if sha256_file(pinned) != source_hash:
        raise RuntimeError("Input copy failed integrity check.")

    env = os.environ.copy()
    env["TRIAL_DATA_FILE"] = str(pinned.resolve())
    env["TRIAL_OUTPUT_DIR"] = str(output_dir.resolve())

    started = datetime.now(timezone.utc)
    log_path = run_dir / "pipeline.log"

    print("RUN ID:", run_id)
    print("INPUT:", pinned)
    print("OUTPUT:", output_dir)

    with log_path.open("w", encoding="utf-8") as log:
        process = subprocess.Popen(
            [
                sys.executable,
                "-u",
                str(ROOT / "run_pipeline.py"),
                "--offline",
            ],
            cwd=ROOT,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

        for line in process.stdout:
            print(line, end="", flush=True)
            log.write(line)

        exit_code = process.wait()

    required = [
        "quality_findings_latest.csv",
        "reconciliation_report.csv",
        "quality_dashboard.html",
    ]

    missing = [
        name for name in required
        if not (output_dir / name).is_file()
    ]

    passed = exit_code == 0 and not missing

    manifest = {
        "run_id": run_id,
        "mode": "isolated_offline",
        "started_utc": started.isoformat(),
        "finished_utc": datetime.now(
            timezone.utc
        ).isoformat(),
        "status": "passed" if passed else "failed",
        "exit_code": exit_code,
        "input_dataset": f"input/{pinned.name}",
        "input_sha256": sha256_file(pinned),
        "outputs": [
            f"output/{name}" for name in required
            if (output_dir / name).is_file()
        ],
        "missing_outputs": missing,
    }

    manifest_path = run_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2),
        encoding="utf-8"
    )

    protected = [
        log_path,
        manifest_path,
        pinned,
        *[
            output_dir / name for name in required
            if (output_dir / name).is_file()
        ],
    ]

    hashes = {
        str(p.relative_to(run_dir)): sha256_file(p)
        for p in protected
    }

    (run_dir / "checksums.json").write_text(
        json.dumps(hashes, indent=2),
        encoding="utf-8"
    )

    for name, expected in hashes.items():
        actual = sha256_file(run_dir / name)
        if actual != expected:
            raise RuntimeError(
                f"Integrity check failed: {name}"
            )

    print("\nISOLATED RUN SUMMARY")
    print("Status:", manifest["status"])
    print("Archive:", run_dir)
    print("Files verified:", len(hashes))

    if not passed:
        raise SystemExit(
            f"Pipeline failed. Missing outputs: {missing}"
        )

    print("ISOLATED PIPELINE COMPLETED SUCCESSFULLY")

if __name__ == "__main__":
    main()
