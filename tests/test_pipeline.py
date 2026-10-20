
import os
import subprocess
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "synthetic_trial.csv"


class TestTrialPipeline(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        pinned_input = os.getenv("TRIAL_DATA_FILE")
        cls.fixture_mode = not bool(pinned_input)

        if pinned_input:
            dataset = Path(pinned_input).resolve()
            output_dir = Path(
                os.getenv(
                    "TRIAL_OUTPUT_DIR",
                    str(ROOT / "exports")
                )
            ).resolve()

        else:
            dataset = FIXTURE.resolve()

            workspace = tempfile.TemporaryDirectory()
            cls.addClassCleanup(workspace.cleanup)

            output_dir = Path(workspace.name)

            env = os.environ.copy()
            env["TRIAL_DATA_FILE"] = str(dataset)
            env["TRIAL_OUTPUT_DIR"] = str(output_dir)

            for script in (
                "validate_trial_data.py",
                "reconcile_findings.py"
            ):
                subprocess.run(
                    [sys.executable, str(ROOT / script)],
                    cwd=ROOT,
                    env=env,
                    check=True,
                    capture_output=True,
                    text=True
                )

        if not dataset.is_file():
            raise FileNotFoundError(dataset)

        print(f"\nTEST DATASET: {dataset.name}")

        cls.data = pd.read_csv(
            dataset,
            dtype=str,
            keep_default_na=False
        )

        cls.findings = pd.read_csv(
            output_dir / "quality_findings_latest.csv",
            dtype=str,
            keep_default_na=False
        )

        cls.report = pd.read_csv(
            output_dir / "reconciliation_report.csv",
            dtype=str,
            keep_default_na=False
        )

    def test_required_columns_exist(self):
        required = {
            "record_id",
            "redcap_event_name",
            "redcap_repeat_instrument",
            "redcap_repeat_instance",
            "redcap_data_access_group",
            "withdrawn",
            "withdrawal_reason"
        }

        self.assertTrue(
            required.issubset(self.data.columns)
        )

    def test_no_duplicate_event_instances(self):
        keys = [
            "record_id",
            "redcap_event_name",
            "redcap_repeat_instrument",
            "redcap_repeat_instance"
        ]

        self.assertEqual(
            int(self.data.duplicated(keys).sum()),
            0
        )

    def test_participant_ids_preserved(self):
        ids = self.data["record_id"]

        self.assertTrue(
            ids.str.fullmatch(r"\d{4}").all()
        )

    def test_findings_match_reconciliation(self):
        columns = ["record_id", "event", "issue"]

        source_keys = Counter(
            map(tuple, self.findings[columns].values)
        )

        report_keys = Counter(
            map(tuple, self.report[columns].values)
        )

        self.assertEqual(source_keys, report_keys)

        if self.fixture_mode:
            self.assertEqual(len(self.findings), 5)

            expected = {
                "Missing visit": 2,
                "Missing visit date": 1,
                "Invalid systolic BP": 1,
                "Missing serious AE details": 1
            }

            actual = (
                self.findings["issue"]
                .value_counts()
                .to_dict()
            )

            self.assertEqual(actual, expected)

    def test_withdrawal_classification(self):
        withdrawn_ids = set(
            self.data.loc[
                self.data["withdrawn"] == "1",
                "record_id"
            ]
        )

        flagged_withdrawn = withdrawn_ids.intersection(
            set(self.report["record_id"])
        )

        if self.fixture_mode:
            self.assertEqual(
                flagged_withdrawn,
                {"0002"}
            )

        if not flagged_withdrawn:
            self.skipTest(
                "No withdrawn participants have findings."
            )

        for participant_id in flagged_withdrawn:
            participant = self.report[
                self.report["record_id"] == participant_id
            ]

            self.assertTrue(
                participant["review_status"]
                .eq(
                    "Withdrawal and protocol review required"
                )
                .all()
            )

        if self.fixture_mode:
            participant = self.report[
                self.report["record_id"] == "0002"
            ]

            self.assertTrue(
                participant["withdrawal_reason"]
                .eq("Participant request")
                .all()
            )


if __name__ == "__main__":
    unittest.main()
