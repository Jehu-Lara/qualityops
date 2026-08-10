import math
import unittest

from qualityops.analysis import (
    analyze_capability,
    analyze_overall_performance,
    analyze_process,
    calculate_cp,
    calculate_cpk,
    calculate_mean,
    calculate_pp,
    calculate_ppk,
    calculate_sample_std,
)


class AnalysisTests(unittest.TestCase):
    def test_mean_and_overall_sample_standard_deviation(self) -> None:
        values = [9.0, 10.0, 11.0]
        self.assertAlmostEqual(calculate_mean(values), 10.0)
        self.assertAlmostEqual(calculate_sample_std(values), 1.0)

    def test_overall_performance_reports_pp_and_ppk(self) -> None:
        result = analyze_overall_performance(
            [9.0, 10.0, 11.0], lsl=7.0, usl=13.0
        )
        self.assertEqual(result.count, 3)
        self.assertAlmostEqual(result.pp, 1.0)
        self.assertAlmostEqual(result.ppk, 1.0)
        self.assertAlmostEqual(result.ppl, 1.0)
        self.assertAlmostEqual(result.ppu, 1.0)

    def test_potential_capability_uses_supplied_within_sigma(self) -> None:
        result = analyze_capability(
            [9.0, 10.0, 11.0], lsl=7.0, usl=13.0, within_sigma=0.5
        )
        self.assertAlmostEqual(result.cp, 2.0)
        self.assertAlmostEqual(result.cpk, 2.0)
        self.assertAlmostEqual(result.cpl, 2.0)
        self.assertAlmostEqual(result.cpu, 2.0)

    def test_combined_analysis_omits_potential_metrics_without_sigma(self) -> None:
        result = analyze_process([9.0, 10.0, 11.0], lsl=7.0, usl=13.0)
        self.assertIsNone(result.potential)

    def test_ppk_and_cpk_use_nearest_specification_limit(self) -> None:
        self.assertAlmostEqual(
            calculate_ppk(mean=11.0, overall_sigma=1.0, lsl=7.0, usl=13.0),
            2 / 3,
        )
        self.assertAlmostEqual(
            calculate_cpk(mean=11.0, within_sigma=1.0, lsl=7.0, usl=13.0),
            2 / 3,
        )

    def test_spread_indices_are_independent_of_mean(self) -> None:
        self.assertAlmostEqual(
            calculate_pp(overall_sigma=0.5, lsl=8.0, usl=14.0), 2.0
        )
        self.assertAlmostEqual(
            calculate_cp(within_sigma=0.5, lsl=8.0, usl=14.0), 2.0
        )

    def test_invalid_observations_are_rejected(self) -> None:
        cases = [
            ([], "At least one"),
            ([1.0, math.nan], "finite"),
            ([1.0, math.inf], "finite"),
        ]
        for values, message in cases:
            with self.subTest(values=values):
                with self.assertRaisesRegex(ValueError, message):
                    calculate_mean(values)

    def test_sample_standard_deviation_requires_two_observations(self) -> None:
        with self.assertRaisesRegex(ValueError, "at least two"):
            calculate_sample_std([1.0])

    def test_constant_process_is_rejected_for_ratio_metrics(self) -> None:
        with self.assertRaisesRegex(ValueError, "positive"):
            analyze_overall_performance([5.0, 5.0], lsl=4.0, usl=6.0)

    def test_invalid_sigma_is_rejected(self) -> None:
        for sigma in [0.0, -1.0, math.inf, math.nan]:
            with self.subTest(sigma=sigma):
                with self.assertRaisesRegex(ValueError, "positive"):
                    calculate_cp(within_sigma=sigma, lsl=7.0, usl=13.0)

    def test_reversed_specification_limits_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "LSL"):
            calculate_cpk(
                mean=10.0, within_sigma=1.0, lsl=13.0, usl=7.0
            )


if __name__ == "__main__":
    unittest.main()
