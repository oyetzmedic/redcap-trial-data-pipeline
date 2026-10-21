"""Independent regression tests for the six REDCap data-quality rules.

Each test generates its own fictional trial CSV, runs the actual validator
in a subprocess, and examines only its isolated output. No REDCap access,
credentials, existing export, or previous pipeline run is required.
"""

import csv
import os
import subprocess
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / "validate_trial_data.py"
BASELINE = "baseline_visit_arm_1"
WEEK_4 = "week_4_followup_arm_1"
WEEK_12 = "week_12_followup_arm_1"

COLUMNS = [
    "record_id",
    "redcap_event_name",
    "redcap_repeat_instrument",
    "redcap_repeat_instance",
    "redcap_data_access_group",
    "visit_date",
    "sbp",
    "ae_serious",
    "ae_serious_details",
    "withdrawn",
    "withdrawal_reason",
]


def valid_visit(event, **changes):
    """Build a valid fictional visit, then optionally change one field."""
    row = {
        "record_id": "0101",
        "redcap_event_name": event,
        "redcap_repeat_instrument": "",
        "redcap_repeat_instance": "",
        "redcap_data_access_group": "manchester",
        "visit_date": "2026-01-01",
        "sbp": "120",
        "ae_serious": "0",
        "ae_serious_details": "",
        "withdrawn": "0",
        "withdrawal_reason": "",
    }
    row.update(changes)
    return row


def clean_trial():
    """One participant with all three expected visits and no issues."""
    return [valid_visit(event) for event in (BASELINE, WEEK_4, WEEK_12)]


def issue_counts(findings):
    return Counter(row["issue"] for row in findings)


class TestValidationRules(unittest.TestCase):
    """Exercise each validation rule with deliberately controlled inputs."""

    def run_validator(self, rows, *, omit_column=None):
        """Run the real validator against an isolated temporary dataset."""
        columns = [name for name in COLUMNS if name != omit_column]

        with tempfile.TemporaryDirectory(prefix="redcap_rule_test_") as folder:
            workspace = Path(folder)
            input_file = workspace / "synthetic_input.csv"
            output_dir = workspace / "output"
            output_dir.mkdir()

            with input_file.open("w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
                writer.writeheader()
                writer.writerows(rows)

            env = os.environ.copy()

            # Limit numerical library threads in test subprocesses.
            for variable in (
                "OPENBLAS_NUM_THREADS",
                "OMP_NUM_THREADS",
                "MKL_NUM_THREADS",
                "NUMEXPR_NUM_THREADS",
            ):
                env[variable] = "1"

            env["TRIAL_DATA_FILE"] = str(input_file)
            env["TRIAL_OUTPUT_DIR"] = str(output_dir)


            completed = subprocess.run(
                [sys.executable, str(VALIDATOR)],
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )

            findings_file = output_dir / "quality_findings_latest.csv"
            findings = []
            if findings_file.exists():
                with findings_file.open("r", newline="", encoding="utf-8") as f:
                    findings = list(csv.DictReader(f))

            return completed, findings

    def assert_valid(self, rows):
        result, findings = self.run_validator(rows)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(findings, [], f"Unexpected findings: {findings}")

    def assert_one_finding(self, rows, issue, *, event, detail=None):
        result, findings = self.run_validator(rows)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(len(findings), 1, findings)
        self.assertEqual(findings[0]["record_id"], "0101")
        self.assertEqual(findings[0]["event"], event)
        self.assertEqual(findings[0]["issue"], issue)
        if detail is not None:
            self.assertEqual(findings[0]["detail"], detail)

    def test_clean_complete_visits_have_no_findings(self):
        self.assert_valid(clean_trial())

    def test_missing_baseline_visit_is_detected(self):
        rows = [r for r in clean_trial() if r["redcap_event_name"] != BASELINE]
        self.assert_one_finding(rows, "Missing visit", event=BASELINE)

    def test_missing_week_four_visit_is_detected(self):
        rows = [r for r in clean_trial() if r["redcap_event_name"] != WEEK_4]
        self.assert_one_finding(rows, "Missing visit", event=WEEK_4)

    def test_missing_week_twelve_visit_is_detected(self):
        rows = [r for r in clean_trial() if r["redcap_event_name"] != WEEK_12]
        self.assert_one_finding(rows, "Missing visit", event=WEEK_12)

    def test_blank_visit_date_is_detected(self):
        rows = clean_trial()
        rows[1]["visit_date"] = ""
        self.assert_one_finding(
            rows, "Missing visit date", event=WEEK_4, detail="Visit date is blank"
        )

    def test_sbp_below_80_is_detected(self):
        rows = clean_trial()
        rows[1]["sbp"] = "79"
        self.assert_one_finding(rows, "Invalid systolic BP", event=WEEK_4, detail="79")

    def test_sbp_above_240_is_detected(self):
        rows = clean_trial()
        rows[1]["sbp"] = "241"
        self.assert_one_finding(rows, "Invalid systolic BP", event=WEEK_4, detail="241")

    def test_nonnumeric_sbp_is_detected(self):
        rows = clean_trial()
        rows[1]["sbp"] = "not-a-number"
        self.assert_one_finding(
            rows, "Invalid systolic BP", event=WEEK_4, detail="not-a-number"
        )

    def test_sbp_limits_80_and_240_are_accepted(self):
        for value in ("80", "240"):
            with self.subTest(sbp=value):
                rows = clean_trial()
                rows[1]["sbp"] = value
                self.assert_valid(rows)

    def test_blank_sbp_does_not_trigger_range_error(self):
        rows = clean_trial()
        rows[1]["sbp"] = ""
        self.assert_valid(rows)

    def test_serious_ae_missing_details_is_detected(self):
        rows = clean_trial()
        rows.append(
            valid_visit(
                BASELINE,
                redcap_repeat_instrument="adverse_events",
                redcap_repeat_instance="1",
                visit_date="",
                sbp="",
                ae_serious="1",
                ae_serious_details="",
            )
        )
        self.assert_one_finding(
            rows, "Missing serious AE details", event=BASELINE, detail="1"
        )

    def test_serious_ae_with_details_is_accepted(self):
        rows = clean_trial()
        rows.append(
            valid_visit(
                BASELINE,
                redcap_repeat_instrument="adverse_events",
                redcap_repeat_instance="1",
                visit_date="",
                sbp="",
                ae_serious="1",
                ae_serious_details="Synthetic serious AE documented",
            )
        )
        self.assert_valid(rows)

    def test_nonserious_ae_without_details_is_accepted(self):
        rows = clean_trial()
        rows.append(
            valid_visit(
                BASELINE,
                redcap_repeat_instrument="adverse_events",
                redcap_repeat_instance="1",
                visit_date="",
                sbp="",
                ae_serious="0",
                ae_serious_details="",
            )
        )
        self.assert_valid(rows)

    def test_duplicate_event_instance_keys_are_detected(self):
        rows = clean_trial()
        rows.append(rows[0].copy())
        result, findings = self.run_validator(rows)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        # Current validator emits one finding for EACH row in a duplicate pair.
        self.assertEqual(issue_counts(findings), Counter({"Duplicate event-instance key": 2}))
        self.assertTrue(all(row["event"] == BASELINE for row in findings))

    def test_distinct_repeating_instances_are_accepted(self):
        rows = clean_trial()
        for instance in ("1", "2"):
            rows.append(
                valid_visit(
                    BASELINE,
                    redcap_repeat_instrument="adverse_events",
                    redcap_repeat_instance=instance,
                    visit_date="",
                    sbp="",
                )
            )
        self.assert_valid(rows)

    def test_inconsistent_data_access_groups_are_detected(self):
        rows = clean_trial()
        rows[2]["redcap_data_access_group"] = "liverpool"
        self.assert_one_finding(
            rows,
            "Inconsistent DAG",
            event="All events",
            detail="liverpool, manchester",
        )

    def test_blank_dag_is_not_a_conflicting_site(self):
        rows = clean_trial()
        rows[2]["redcap_data_access_group"] = ""
        self.assert_valid(rows)

    def test_missing_required_column_fails_validation(self):
        result, findings = self.run_validator(clean_trial(), omit_column="visit_date")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Missing columns", result.stdout + result.stderr)
        self.assertEqual(findings, [])


if __name__ == "__main__":
    unittest.main()
