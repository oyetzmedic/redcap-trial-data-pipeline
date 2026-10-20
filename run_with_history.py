
import hashlib
import argparse
import json
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

    with Path(path).open("rb") as file:
        for chunk in iter(
            lambda: file.read(1024 * 1024),
            b""
        ):
            digest.update(chunk)

    return digest.hexdigest()

parser = argparse.ArgumentParser()
parser.add_argument("--offline", action="store_true")
args = parser.parse_args()

run_id = datetime.now(timezone.utc).strftime(
    "%Y%m%d_%H%M%S_%f"
)

run_dir = RUNS / run_id
run_dir.mkdir(parents=True, exist_ok=False)

log_file = run_dir / "pipeline.log"

started = datetime.now(timezone.utc)

command = [
    sys.executable,
    str(ROOT / "run_pipeline.py")
]

if args.offline:
    command.append("--offline")

print("Run ID:", run_id)
print("Mode:", "Offline" if args.offline else "Live API")
print("Log:", log_file)

selected_export_name = None
with log_file.open("w", encoding="utf-8") as log:
    process = subprocess.Popen(
        command,
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1
    )

    for line in process.stdout:
        print(line, end="", flush=True)
        log.write(line)
        log.flush()

        if line.startswith("PINNED DATASET:"):
            selected_export_name = line.split(
                ":", 1
            )[1].strip()


    return_code = process.wait()

manifest = {
    "run_id": run_id,
    "started_utc": started.isoformat(),
    "finished_utc": datetime.now(
        timezone.utc
    ).isoformat(),
    "mode": "offline" if args.offline else "live",
    "status": "passed" if return_code == 0 else "failed",
    "exit_code": return_code,
    "snapshots": []
}


if return_code == 0:
    if not selected_export_name:
        raise RuntimeError(
            "Pipeline did not report its pinned dataset."
        )

    if (
        Path(selected_export_name).name != selected_export_name
        or not selected_export_name.startswith("trial_data_")
        or not selected_export_name.endswith(".csv")
    ):
        raise ValueError("Invalid pinned dataset filename.")

    selected_export = (
        EXPORTS / selected_export_name
    ).resolve()

    if not selected_export.is_file():
        raise FileNotFoundError(selected_export)

    input_hash = sha256_file(selected_export)

    manifest["input_dataset"] = selected_export.name
    manifest["input_sha256"] = input_hash

    outputs = [
        selected_export,
        EXPORTS / "quality_findings_latest.csv",
        EXPORTS / "reconciliation_report.csv",
        EXPORTS / "quality_dashboard.html"
    ]

    for source in outputs:
        if not source.is_file():
            raise FileNotFoundError(
                f"Expected output missing: {source}"
            )

    for source in outputs:
        destination = run_dir / source.name

        shutil.copy2(source, destination)

        if sha256_file(source) != sha256_file(destination):
            raise RuntimeError(
                f"Snapshot integrity mismatch: {source.name}"
            )

        manifest["snapshots"].append(source.name)


if return_code == 0:
    if not selected_export_name:
        raise RuntimeError(
            "No pinned dataset was captured."
        )

    selected_export = EXPORTS / selected_export_name

    if not selected_export.is_file():
        raise FileNotFoundError(selected_export)

    manifest["input_dataset"] = selected_export.name
    manifest["input_sha256"] = sha256_file(
        selected_export
    )

manifest_file = run_dir / "manifest.json"
manifest_file.write_text(
    json.dumps(manifest, indent=2),
    encoding="utf-8"
)
# Automatically create and verify archive checksums
if return_code == 0:
    print("\nARCHIVE INTEGRITY CHECK", flush=True)

    for action in ("create", "verify"):
        subprocess.run(
            [
                sys.executable,
                str(ROOT / "verify_archive.py"),
                action,
                "--run",
                str(run_dir.relative_to(ROOT))
            ],
            cwd=ROOT,
            check=True
        )

    print("Archive checksum verification: PASSED", flush=True)

print("\nRUN HISTORY")
print("Status:", manifest["status"])
print("Archive:", run_dir)
print("Saved snapshots:", len(manifest["snapshots"]))

if return_code:
    sys.exit(return_code)
