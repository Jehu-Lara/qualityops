import math
import unittest

from qualityops.inferential import one_way_anova


class OneWayAnovaTests(unittest.TestCase):
    def test_known_one_way_anova_result(self) -> None:
        result = one_way_anova(
            {
                "A": [8, 9, 10, 9, 8],
                "B": [10, 11, 12, 11, 10],
                "C": [13, 14, 15, 14, 13],
            }
        )

        self.assertEqual(result.group_count, 3)
        self.assertEqual(result.observation_count, 15)
        self.assertEqual(result.df_between, 2)
        self.assertEqual(result.df_within, 12)
        self.assertAlmostEqual(result.ss_between, 63.33333333333333)
        self.assertAlmostEqual(result.ss_within, 8.4)
        self.assertAlmostEqual(result.ss_total, 71.73333333333333)
        self.assertAlmostEqual(result.ms_between, 31.666666666666664)
        self.assertAlmostEqual(result.ms_within, 0.7)
        self.assertAlmostEqual(result.f_statistic, 45.23809523809513)
        self.assertAlmostEqual(result.p_value, 2.578396142261877e-06)

    def test_requires_at_least_two_groups(self) -> None:
        with self.assertRaisesRegex(ValueError, "at least two groups"):
            one_way_anova({"A": [1, 2, 3]})

    def test_requires_two_observations_per_group(self) -> None:
        with self.assertRaisesRegex(ValueError, "at least two observations"):
            one_way_anova(
                {
                    "A": [1],
                    "B": [2, 3],
                }
            )

    def test_rejects_non_finite_observations(self) -> None:
        with self.assertRaisesRegex(ValueError, "finite"):
            one_way_anova(
                {
                    "A": [1, math.nan],
                    "B": [2, 3],
                }
            )

    def test_rejects_zero_within_group_variation(self) -> None:
        with self.assertRaisesRegex(ValueError, "variation must be positive"):
            one_way_anova(
                {
                    "A": [1, 1],
                    "B": [2, 2],
                }
            )


if __name__ == "__main__":
    unittest.main()