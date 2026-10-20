
import os
from pathlib import Path
from datetime import datetime, timezone
from html import escape
import pandas as pd

output_dir = Path(
    os.getenv("TRIAL_OUTPUT_DIR", "exports")
).resolve()

output_dir.mkdir(parents=True, exist_ok=True)
source = output_dir / "reconciliation_report.csv"

if not source.exists():
    raise FileNotFoundError("Run reconcile_findings.py first.")

df = pd.read_csv(
    source,
    dtype=str,
    keep_default_na=False
)

required = [
    "record_id", "site", "event", "issue",
    "withdrawal_reason", "review_status", "resolution"
]

missing = set(required) - set(df.columns)
if missing:
    raise ValueError(f"Missing columns: {missing}")

total = len(df)
site_reviews = (
    df["review_status"] == "Site investigation required"
).sum()
protocol_reviews = (
    df["review_status"] ==
    "Withdrawal and protocol review required"
).sum()

site_counts = df["site"].value_counts()
status_counts = df["review_status"].value_counts()

def make_bars(counts):
    maximum = max(counts.max(), 1) if len(counts) else 1
    items = []

    for label, count in counts.items():
        width = 100 * count / maximum
        items.append(
            f'<div class="bar-row">'
            f'<span>{escape(str(label))}</span>'
            f'<div class="track">'
            f'<div class="fill" style="width:{width:.1f}%">'
            f'</div></div><strong>{count}</strong></div>'
        )

    return "\n".join(items)

details = (
    df[required]
    .sort_values(["site", "record_id"])
    .to_html(index=False, escape=True, border=0)
)

updated = datetime.now(timezone.utc).strftime(
    "%Y-%m-%d %H:%M UTC"
)

html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>REDCap Trial Data Quality Dashboard</title>
<style>
body {{
    font-family: Arial, sans-serif;
    background: #f3f6fa;
    color: #172638;
    margin: 0;
    padding: 28px;
}}
main {{ max-width: 1150px; margin: auto; }}
header, section {{
    background: white;
    padding: 24px;
    border-radius: 12px;
    margin-bottom: 20px;
}}
h1 {{ margin-bottom: 8px; }}
h2 {{ font-size: 19px; }}
.sub {{ color: #5c6b7a; }}
.cards {{
    display: grid;
    grid-template-columns: repeat(auto-fit,minmax(180px,1fr));
    gap: 16px;
    margin-bottom: 20px;
}}
.card {{
    background: white;
    padding: 22px;
    border-radius: 12px;
}}
.number {{
    font-size: 36px;
    font-weight: bold;
    color: #17669b;
    margin-top: 8px;
}}
.bar-row {{
    display: grid;
    grid-template-columns: 220px 1fr 35px;
    align-items: center;
    gap: 12px;
    margin: 15px 0;
}}
.track {{
    height: 18px;
    background: #e5edf5;
    border-radius: 5px;
}}
.fill {{
    height: 100%;
    background: #287fb6;
    border-radius: 5px;
}}
.table-wrap {{ overflow-x: auto; }}
table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 13px;
}}
th, td {{
    padding: 12px;
    border-bottom: 1px solid #dce3eb;
    text-align: left;
}}
th {{ background: #eaf1f8; }}
tr:hover {{ background: #f6f9fc; }}
footer {{ color: #5c6b7a; font-size: 12px; }}
</style>
</head>
<body>
<main>
<header>
<h1>Clinical Trial Data Quality Dashboard</h1>
<p class="sub">Mock Two-Group Longitudinal Trial</p>
<p class="sub">Synthetic REDCap dataset | Updated {updated}</p>
</header>

<div class="cards">
<div class="card">
Total findings
<div class="number">{total}</div>
</div>
<div class="card">
Site investigations
<div class="number">{site_reviews}</div>
</div>
<div class="card">
Withdrawal/protocol reviews
<div class="number">{protocol_reviews}</div>
</div>
</div>

<section>
<h2>Findings by site</h2>
{make_bars(site_counts)}
<p class="sub">Counts, not site-specific error rates.</p>
</section>

<section>
<h2>Findings by review status</h2>
{make_bars(status_counts)}
</section>

<section>
<h2>Participant-level reconciliation</h2>
<div class="table-wrap">{details}</div>
</section>

<footer>
Synthetic training data only.
Findings remain pending until reviewed.
This report does not verify protocol compliance.
</footer>
</main>
</body>
</html>"""

destination = output_dir / "quality_dashboard.html"
destination.write_text(html, encoding="utf-8")

print("\nDASHBOARD GENERATED")
print("Total findings:", total)
print("Site investigations:", site_reviews)
print("Protocol reviews:", protocol_reviews)
print("Saved:", destination.resolve())
