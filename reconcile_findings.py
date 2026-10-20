

import os
from pathlib import Path
import pandas as pd

export_dir = Path(
    os.getenv("TRIAL_OUTPUT_DIR", "exports")
).resolve()

export_dir.mkdir(parents=True, exist_ok=True)
pinned_input = os.getenv("TRIAL_DATA_FILE")

if pinned_input:
    latest = Path(pinned_input).resolve()

    if not latest.is_file():
        raise FileNotFoundError(
            f"Pinned trial dataset not found: {latest}"
        )
else:
    files = list(export_dir.glob("trial_data_*.csv"))

    if not files:
        raise FileNotFoundError(
            "No trial export found."
        )

    latest = max(
        files,
        key=lambda p: p.stat().st_mtime_ns
    )

df = pd.read_csv(
    latest,
    dtype=str,
    keep_default_na=False
)

print("Reconciling:", latest.name)
print("Input path:", latest.resolve())


findings = pd.read_csv(
    export_dir / "quality_findings_latest.csv",
    dtype=str,
    keep_default_na=False
)

reason_codes = {
    "1": "Adverse event",
    "2": "Participant request",
    "3": "Lost to follow-up",
    "4": "Other"
}

report = []

for _, finding in findings.iterrows():
    participant = finding["record_id"]

    records = df[df["record_id"] == participant]

    sites = sorted(set(
        records["redcap_data_access_group"]
        .loc[lambda x: x != ""]
    ))

    site = sites[0] if len(sites) == 1 else "Review DAG"

    withdrawals = records[
        records["withdrawn"] == "1"
    ]

    if withdrawals.empty:
        status = "Site investigation required"
        reason = "No withdrawal recorded"
    else:
        codes = [
            code for code in
            withdrawals["withdrawal_reason"].unique()
            if code
        ]

        reasons = [
            reason_codes.get(code, f"Unknown code {code}")
            for code in codes
        ]

        reason = ", ".join(reasons) or "Not specified"
        status = "Withdrawal and protocol review required"

    report.append({
        "record_id": participant,
        "site": site,
        "event": finding["event"],
        "issue": finding["issue"],
        "withdrawal_reason": reason,
        "review_status": status,
        "resolution": "Pending review"
    })

report = pd.DataFrame(report)

output = export_dir / "reconciliation_report.csv"
report.to_csv(output, index=False)

print("\nREDCAP RECONCILIATION REPORT")
print("=" * 50)

print(report.to_string(index=False))

print("\nFINDINGS BY SITE")
print(report.groupby("site").size().to_string())

print("\nFINDINGS BY REVIEW STATUS")
print(
    report["review_status"].value_counts().to_string()
)

print("\nSaved:", output)
print("Reconciliation report completed.")
