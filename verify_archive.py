
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent

parser = argparse.ArgumentParser()
parser.add_argument(
    "action",
    choices=["create", "verify"]
)
parser.add_argument(
    "--run",
    required=True,
    help="Run archive folder"
)
args = parser.parse_args()

run_dir = (ROOT / args.run).resolve()
manifest_path = run_dir / "manifest.json"
checksum_path = run_dir / "checksums.json"

if not run_dir.is_dir():
    raise FileNotFoundError(run_dir)

manifest = json.loads(
    manifest_path.read_text(encoding="utf-8")
)

files = [
    "pipeline.log",
    "manifest.json",
    *manifest["snapshots"]
]

def sha256(path):
    digest = hashlib.sha256()

    with path.open("rb") as file:
        for chunk in iter(
            lambda: file.read(1024 * 1024), b""
        ):
            digest.update(chunk)

    return digest.hexdigest()

if args.action == "create":
    hashes = {}

    for name in files:
        path = run_dir / name
        if not path.is_file():
            raise FileNotFoundError(path)

        hashes[name] = sha256(path)

    checksum_path.write_text(
        json.dumps(hashes, indent=2),
        encoding="utf-8"
    )

    print("SHA-256 baseline created.")
    print("Files protected:", len(hashes))

else:
    saved = json.loads(
        checksum_path.read_text(encoding="utf-8")
    )

    if set(saved) != set(files):
        raise ValueError(
            "Checksum file list does not match manifest."
        )

    failures = []

    for name, expected_hash in saved.items():
        path = run_dir / name

        if not path.is_file():
            print("MISSING:", name)
            failures.append(name)
            continue

        actual_hash = sha256(path)

        if actual_hash == expected_hash:
            print("PASS:", name)
        else:
            print("FAIL:", name)
            failures.append(name)

    if failures:
        raise SystemExit(
            f"Integrity verification failed: "
            f"{len(failures)} file(s)"
        )

    print("\nARCHIVE INTEGRITY VERIFIED")
    print("Files verified:", len(saved))
