

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
    keep_default_na=False,
)

print("Validating:", latest.name)
print("Input path:", latest.resolve())


required = {
    "record_id",
    "redcap_event_name",
    "redcap_repeat_instrument",
    "redcap_repeat_instance",
    "visit_date",
    "sbp",
    "ae_serious",
    "ae_serious_details",
    "redcap_data_access_group",
}

missing_columns = required - set(df.columns)

if missing_columns:
    raise ValueError(f"Missing columns: {missing_columns}")

findings = []

def flag(record_id, event, issue, detail):
    findings.append({
        "record_id": record_id,
        "event": event,
        "issue": issue,
        "detail": detail,
    })

# Separate ordinary visits from repeating instruments.
visits = df[df["redcap_repeat_instrument"] == ""]

expected_events = [
    "baseline_visit_arm_1",
    "week_4_followup_arm_1",
    "week_12_followup_arm_1",
]

# Check missing visits and dates.
for participant in sorted(df["record_id"].unique()):
    participant_visits = visits[
        visits["record_id"] == participant
    ]

    for event in expected_events:
        rows = participant_visits[
            participant_visits["redcap_event_name"] == event
        ]

        if rows.empty:
            flag(participant, event, "Missing visit",
                 "No event record exists")
        elif rows["visit_date"].eq("").all():
            flag(participant, event, "Missing visit date",
                 "Visit date is blank")

# Check systolic blood pressure.
for _, row in visits.iterrows():
    value = row["sbp"].strip()

    if not value:
        continue

    number = pd.to_numeric(value, errors="coerce")

    if pd.isna(number) or not 80 <= number <= 240:
        flag(
            row["record_id"],
            row["redcap_event_name"],
            "Invalid systolic BP",
            value,
        )

# Check serious adverse event documentation.
for _, row in df.iterrows():
    if (
        row["ae_serious"] == "1"
        and not row["ae_serious_details"].strip()
    ):
        flag(
            row["record_id"],
            row["redcap_event_name"],
            "Missing serious AE details",
            row["redcap_repeat_instance"],
        )

# Check duplicate event-instance keys.
key_columns = [
    "record_id",
    "redcap_event_name",
    "redcap_repeat_instrument",
    "redcap_repeat_instance",
]

duplicates = df.duplicated(key_columns, keep=False)

for _, row in df[duplicates].iterrows():
    flag(
        row["record_id"],
        row["redcap_event_name"],
        "Duplicate event-instance key",
        row["redcap_repeat_instance"],
    )

# Check Data Access Group consistency.
for participant, group in df.groupby("record_id"):
    groups = set(
        group["redcap_data_access_group"]
        .loc[lambda x: x != ""]
    )

    if len(groups) > 1:
        flag(
            participant,
            "All events",
            "Inconsistent DAG",
            ", ".join(sorted(groups)),
        )

results = pd.DataFrame(
    findings,
    columns=["record_id", "event", "issue", "detail"],
)

output = export_dir / "quality_findings_latest.csv"
results.to_csv(output, index=False)

print("\nDATA QUALITY SUMMARY")
print("Participants:", df["record_id"].nunique())
print("Total rows:", len(df))
print("Ordinary visit rows:", len(visits))
print("Repeating instrument rows:", len(df) - len(visits))
print("Total findings:", len(results))

if not results.empty:
    print("\nFindings by issue:")
    print(results["issue"].value_counts().to_string())

    print("\nAffected participants:")
    print(", ".join(sorted(results["record_id"].unique())))

print("\nFindings saved:", output)
print("Validation completed.")
