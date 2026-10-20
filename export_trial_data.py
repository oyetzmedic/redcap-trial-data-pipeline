
import os
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from redcap import Project

load_dotenv()

api_url = os.getenv("REDCAP_API_URL")
api_token = os.getenv("REDCAP_API_TOKEN")

if not api_url or not api_token:
    raise RuntimeError("Missing REDCap API configuration.")

print("Connecting to REDCap...")

project = Project(api_url, api_token)

print("Exporting synthetic trial records...")

records = project.export_records(
    raw_or_label="raw",
    event_name="unique",
    export_data_access_groups=True,
)

if not records:
    raise RuntimeError("No records returned by REDCap.")

df = pd.DataFrame(records)

# Preserve participant IDs with leading zeros.
df["record_id"] = df["record_id"].astype("string")

# Create a local export directory.

output_dir = Path(
    os.getenv("TRIAL_OUTPUT_DIR", "exports")
).resolve()

output_dir.mkdir(
    parents=True,
    exist_ok=True
)


timestamp = datetime.now(timezone.utc).strftime(
    "%Y%m%d_%H%M%S"
)

output_file = output_dir / f"trial_data_{timestamp}.csv"

df.to_csv(output_file, index=False)

print("\nEXPORT SUMMARY")
print("Total rows:", len(df))
print("Total columns:", len(df.columns))
print("Unique participants:", df["record_id"].nunique())

if "redcap_event_name" in df.columns:
    print("\nRows by event:")
    print(df["redcap_event_name"].value_counts().to_string())

if "redcap_repeat_instrument" in df.columns:
    repeats = df[
        df["redcap_repeat_instrument"].notna()
        & (df["redcap_repeat_instrument"] != "")
    ]
    print("\nRepeating instrument rows:", len(repeats))

print("\nExport saved:", output_file)
print("Read-only extraction completed.")
