import hashlib
import json
import math
from pathlib import Path
import tempfile
import unittest

from qualityops.spc import (
    analyze_subgroup_capability,
    analyze_xbar_r,
    load_wide_subgroups,
)


ROOT = Path(__file__).parents[1]
DATASET = ROOT / "data" / "spc" / "qualityops_spc_rbar_n4_v1.csv"
COLUMNS = ("measure_1", "measure_2", "measure_3", "measure_4")


class SpcValidationTests(unittest.TestCase):
    def test_canonical_dataset_hash_is_stable(self) -> None:
        digest = hashlib.sha256(DATASET.read_bytes()).hexdigest()
        self.assertEqual(
            digest,
            "2ce0338888071200dcf4835bd21b72dbdbedba8336a6491e5eb3a8c783cb866c",
        )

    def test_manifest_hashes_and_specifications_are_complete(self) -> None:
        manifest_path = ROOT / "data" / "spc" / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(
            manifest["specification_assumptions"],
            {
                "lsl": 495,
                "target": 500,
                "usl": 505,
                "justification": (
                    "controlled symmetric limits selected for formula validation; "
                    "not customer or industry requirements"
                ),
            },
        )
        for relative_path, expected_hash in manifest["files"].items():
            source = (
                ROOT / relative_path
                if relative_path.startswith("docs/")
                else manifest_path.parent / relative_path
            )
            with self.subTest(path=relative_path):
                self.assertTrue(source.is_file())
                self.assertEqual(
                    hashlib.sha256(source.read_bytes()).hexdigest(),
                    expected_hash,
                )

    def test_track_c_matches_unrounded_minitab_reference(self) -> None:
        result = analyze_subgroup_capability(
            load_wide_subgroups(DATASET, COLUMNS),
            lsl=495,
            usl=505,
            target=500,
        )
        expected = {
            "grand_mean": (result.chart.grand_mean, 500.1301299999999),
            "average_range": (result.chart.average_range, 1.8744000000000023),
            "within_sigma": (result.chart.within_sigma, 0.9103448275862079),
            "overall_sigma": (
                result.overall.overall_sample_std,
                0.9275845209658025,
            ),
            "xbar_lcl": (result.chart.xbar_lcl, 498.76461275862056),
            "xbar_ucl": (result.chart.xbar_ucl, 501.49564724137923),
            "range_lcl": (result.chart.range_lcl, 0.0),
            "range_ucl": (result.chart.range_ucl, 4.27716413793104),
            "cp": (result.potential.cp, 1.8308080808080787),
            "cpk": (result.potential.cpk, 1.7831594696970061),
            "pp": (result.overall.pp, 1.7967814565634739),
            "ppk": (result.overall.ppk, 1.7500184223749908),
            "cpm": (result.cpm, 1.7881467512164682),
        }
        for metric, (actual, reference) in expected.items():
            with self.subTest(metric=metric):
                self.assertLessEqual(abs(actual - reference), 1e-9)
        self.assertEqual(result.chart.xbar_test1_violations, ())
        self.assertEqual(result.chart.range_test1_violations, ())

    def test_unequal_subgroups_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "same size"):
            analyze_xbar_r([[1, 2, 3], [4, 5]])

    def test_unsupported_subgroup_size_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "between 2 and 10"):
            analyze_xbar_r([[1], [2]])

    def test_nonfinite_subgroup_value_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "non-finite"):
            analyze_xbar_r([[1, 2], [3, math.inf]])

    def test_test1_reports_one_based_subgroup_numbers(self) -> None:
        result = analyze_xbar_r([[-5, 5]] * 9 + [[25, 35]])
        self.assertEqual(result.xbar_test1_violations, (10,))

    def test_loader_rejects_missing_measurement_column(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "subgroups.csv"
            path.write_text("subgroup,a,b\n1,1,2\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Missing measurement columns"):
                load_wide_subgroups(path, ("a", "b", "c"))

    def test_loader_rejects_invalid_measurement_value(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "subgroups.csv"
            path.write_text("subgroup,a,b\n1,1,invalid\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "row 2"):
                load_wide_subgroups(path, ("a", "b"))


if __name__ == "__main__":
    unittest.main()
