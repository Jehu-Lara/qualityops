import copy
from dataclasses import FrozenInstanceError
from io import StringIO
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch

import pandas as pd

from qualityops import SecomAuditResult, audit_secom, load_secom
from qualityops.cli import main
from qualityops import secom


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DATA_DIRECTORY = REPOSITORY_ROOT / "data" / "external" / "secom" / "raw"
REPORT_PATH = REPOSITORY_ROOT / "data" / "external" / "secom" / "quality-report.json"


class SecomLayerTests(unittest.TestCase):
    def test_sha256_normalization_is_case_and_whitespace_insensitive(self) -> None:
        digest = "ab" * 32
        self.assertEqual(secom._normalize_sha256(f"  {digest}\n"), digest.upper())
        with self.assertRaisesRegex(ValueError, "64 hexadecimal"):
            secom._normalize_sha256("not-a-digest")

    def test_hash_verification_accepts_normalized_acquisition_hashes(self) -> None:
        metadata = tuple(
            secom._FileMetadata(
                filename=filename,
                size_bytes=size,
                sha256=f" {digest.lower()} ",
            )
            for filename, (size, digest) in secom._EXPECTED_FILES.items()
        )
        secom._verify_secom_hashes(metadata)

    def test_hash_failure_stops_before_parsing(self) -> None:
        metadata = tuple(
            secom._FileMetadata(
                filename=filename,
                size_bytes=size,
                sha256=("0" * 64 if filename == "secom.data" else digest),
            )
            for filename, (size, digest) in secom._EXPECTED_FILES.items()
        )
        with (
            patch.object(secom, "_resolve_secom_paths"),
            patch.object(secom, "_compute_file_metadata", return_value=metadata),
            patch.object(secom, "_parse_secom_files") as parser,
        ):
            with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
                load_secom("unused")
        parser.assert_not_called()

    def test_parser_can_be_tested_without_hash_bypass_in_public_api(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            data_path = directory / "secom.data"
            labels_path = directory / "secom_labels.data"
            names_path = directory / "secom.names"
            data_path.write_text("1 NaN\n2 3\n", encoding="utf-8")
            labels_path.write_text(
                '-1 "19/07/2008 11:55:00"\n1 "20/07/2008 12:00:00"\n',
                encoding="utf-8",
            )
            names_path.write_text("fixture", encoding="utf-8")
            parsed = secom._parse_secom_files(
                secom._SecomPaths(data_path, labels_path, names_path)
            )

        self.assertEqual(parsed["source_row"].tolist(), [1, 2])
        self.assertEqual(parsed["label"].tolist(), [-1, 1])
        self.assertTrue(math.isnan(parsed.loc[0, "sensor_001"]))

    def test_duplicate_detection_excludes_source_row_and_matches_nan(self) -> None:
        dataframe = pd.DataFrame(
            {
                "source_row": [1, 2],
                "timestamp": pd.to_datetime(["2008-01-01", "2008-01-01"]),
                "label": [-1, -1],
                "sensor_000": [math.nan, math.nan],
            }
        )
        self.assertEqual(
            secom._count_duplicate_records(dataframe, ("sensor_000",)),
            1,
        )

    def test_constant_definition_ignores_missing_values(self) -> None:
        dataframe = pd.DataFrame(
            {
                "sensor_000": [1.0, math.nan, 1.0],
                "sensor_001": [1.0, 2.0, math.nan],
                "sensor_002": [math.nan, math.nan, math.nan],
            }
        )
        self.assertEqual(
            secom._constant_sensor_names(
                dataframe,
                ("sensor_000", "sensor_001", "sensor_002"),
            ),
            ("sensor_000",),
        )


class SecomAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.dataframe = load_secom(DATA_DIRECTORY)
        cls.audit = audit_secom(DATA_DIRECTORY)
        cls.report = cls.audit.to_dict()

    def test_public_result_is_immutable(self) -> None:
        self.assertIsInstance(self.audit, SecomAuditResult)
        with self.assertRaises(FrozenInstanceError):
            self.audit.row_count = 0  # type: ignore[misc]

    def test_loads_expected_structure_with_one_based_source_rows(self) -> None:
        self.assertEqual(self.dataframe.shape, (1567, 593))
        self.assertEqual(self.dataframe["source_row"].iloc[0], 1)
        self.assertEqual(self.dataframe["source_row"].iloc[-1], 1567)
        self.assertEqual(self.dataframe.columns[3], "sensor_000")
        self.assertEqual(self.dataframe.columns[-1], "sensor_589")

    def test_numeric_oracle(self) -> None:
        quality = self.report["quality"]
        timestamps = quality["timestamps"]
        self.assertEqual(self.report["structure"]["row_count"], 1567)
        self.assertEqual(self.report["structure"]["sensor_count"], 590)
        self.assertEqual(quality["missing_cell_count"], 41951)
        self.assertEqual(quality["sensors_with_missing_count"], 538)
        self.assertEqual(quality["all_missing_sensor_count"], 0)
        self.assertEqual(quality["constant_sensor_count"], 116)
        self.assertEqual(quality["duplicate_records"]["occurrences_after_first"], 0)
        self.assertEqual(quality["labels"]["pass_count"], 1463)
        self.assertEqual(quality["labels"]["fail_count"], 104)
        self.assertEqual(timestamps["invalid_count"], 0)
        self.assertEqual(timestamps["duplicate_occurrences_after_first"], 33)
        self.assertEqual(timestamps["distinct_values_repeated"], 32)
        self.assertEqual(timestamps["earliest"], "2008-07-19T11:55:00")
        self.assertEqual(timestamps["latest"], "2008-10-17T06:07:00")

    def test_file_sizes_and_acquisition_hashes(self) -> None:
        expected = {
            filename: {
                "size_bytes": size,
                "sha256_acquisition": digest,
            }
            for filename, (size, digest) in secom._EXPECTED_FILES.items()
        }
        self.assertEqual(self.report["verified_files"], expected)
        self.assertEqual(
            self.report["dataset"]["archive_acquisition_record"],
            {
                "filename": "secom.zip",
                "size_bytes": 1964989,
                "sha256_acquisition": (
                    "EEA568BAF3C2229096D7D294CF0B096B5502BD96D92C0B80A65B84714059BE8E"
                ),
                "committed": False,
                "verified_by_cli": False,
            },
        )

    def test_contract_contains_exact_sensor_keys_and_consistent_lists(self) -> None:
        quality = self.report["quality"]
        self.assertEqual(
            tuple(quality["missing_by_sensor"]),
            tuple(f"sensor_{index:03d}" for index in range(590)),
        )
        self.assertEqual(len(quality["constant_sensors"]), 116)
        self.assertEqual(
            quality["constant_sensor_count"],
            len(quality["constant_sensors"]),
        )
        self.assertEqual(
            quality["missing_cell_count"],
            sum(quality["missing_by_sensor"].values()),
        )

    def test_contract_rejects_missing_and_additional_keys(self) -> None:
        missing = copy.deepcopy(self.report)
        missing["quality"].pop("labels")
        with self.assertRaisesRegex(ValueError, "missing=.*labels"):
            secom._validate_report_contract(missing)

        additional = copy.deepcopy(self.report)
        additional["dataset"]["path"] = "relative"
        with self.assertRaisesRegex(ValueError, "additional=.*path"):
            secom._validate_report_contract(additional)

    def test_json_is_finite_portable_and_allows_only_documented_urls(self) -> None:
        json.dumps(self.report, allow_nan=False)
        secom._validate_portable_json(self.report)

        with self.assertRaisesRegex(ValueError, "absolute paths"):
            secom._validate_portable_json({"value": "C:\\private\\dataset"})
        with self.assertRaisesRegex(ValueError, "forbidden"):
            secom._validate_portable_json({"hostname": "build-agent"})
        with self.assertRaisesRegex(ValueError, "documented source fields"):
            secom._validate_portable_json({"reference": "https://example.com"})
        with self.assertRaisesRegex(ValueError, "NaN or Infinity"):
            secom._validate_portable_json({"value": math.inf})

    def test_committed_report_matches_regenerated_report_logically(self) -> None:
        committed = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
        self.assertEqual(committed, self.report)


class SecomCliTests(unittest.TestCase):
    def test_success_exit_code_and_json_output(self) -> None:
        stdout = StringIO()
        with redirect_stdout(stdout):
            exit_code = main(
                ["audit-secom", "--data-dir", str(DATA_DIRECTORY)]
            )
        self.assertEqual(exit_code, 0)
        self.assertEqual(json.loads(stdout.getvalue())["schema_version"], 1)

    def test_missing_argument_exits_with_code_two(self) -> None:
        stderr = StringIO()
        with redirect_stderr(stderr):
            with self.assertRaises(SystemExit) as raised:
                main(["audit-secom"])
        self.assertEqual(raised.exception.code, 2)
        self.assertIn("--data-dir", stderr.getvalue())

    def test_missing_files_and_integrity_errors_exit_with_code_two(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            empty_stderr = StringIO()
            empty_stdout = StringIO()
            with redirect_stderr(empty_stderr), redirect_stdout(empty_stdout):
                with self.assertRaises(SystemExit) as missing:
                    main(["audit-secom", "--data-dir", temporary_directory])
            self.assertEqual(missing.exception.code, 2)
            self.assertEqual(empty_stdout.getvalue(), "")
            self.assertIn("Required SECOM file", empty_stderr.getvalue())

            directory = Path(temporary_directory)
            for filename in secom._SOURCE_FILENAMES:
                (directory / filename).write_bytes(b"altered")
            hash_stderr = StringIO()
            hash_stdout = StringIO()
            with redirect_stderr(hash_stderr), redirect_stdout(hash_stdout):
                with self.assertRaises(SystemExit) as invalid:
                    main(["audit-secom", "--data-dir", temporary_directory])
            self.assertEqual(invalid.exception.code, 2)
            self.assertEqual(hash_stdout.getvalue(), "")
            self.assertIn("Unexpected size", hash_stderr.getvalue())

    def test_parsing_and_invariant_errors_exit_with_code_two(self) -> None:
        for message in (
            "Unable to parse SECOM source files",
            "SECOM data must contain exactly 1567 aligned rows",
        ):
            with self.subTest(message=message):
                stderr = StringIO()
                stdout = StringIO()
                with (
                    patch("qualityops.cli.audit_secom", side_effect=ValueError(message)),
                    redirect_stderr(stderr),
                    redirect_stdout(stdout),
                ):
                    with self.assertRaises(SystemExit) as raised:
                        main(["audit-secom", "--data-dir", str(DATA_DIRECTORY)])
                self.assertEqual(raised.exception.code, 2)
                self.assertEqual(stdout.getvalue(), "")
                self.assertIn(message, stderr.getvalue())

    def test_cli_stdout_is_byte_identical_across_processes(self) -> None:
        command = [
            sys.executable,
            "-m",
            "qualityops",
            "audit-secom",
            "--data-dir",
            str(DATA_DIRECTORY),
        ]
        first = subprocess.run(
            command,
            cwd=REPOSITORY_ROOT,
            check=True,
            capture_output=True,
        )
        second = subprocess.run(
            command,
            cwd=REPOSITORY_ROOT,
            check=True,
            capture_output=True,
        )
        self.assertEqual(first.stdout, second.stdout)
        self.assertEqual(first.stderr, b"")
        self.assertTrue(first.stdout.endswith(b"\n"))


if __name__ == "__main__":
    unittest.main()
