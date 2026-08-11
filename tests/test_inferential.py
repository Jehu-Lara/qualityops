import math
import unittest

from qualityops.inferential import (
    one_way_anova,
    pearson_correlation,
    simple_linear_regression,
)


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


class PearsonCorrelationTests(unittest.TestCase):
    def test_known_pearson_correlation_result(self) -> None:
        result = pearson_correlation(
            [10, 12, 14, 16, 18, 20, 22, 24, 26, 28, 30, 32],
            [21, 24, 27, 31, 33, 37, 39, 43, 46, 48, 52, 55],
        )

        self.assertEqual(result.observation_count, 12)
        self.assertAlmostEqual(
            result.correlation,
            0.9992054933198898,
            places=12,
        )
        self.assertTrue(
            math.isclose(
                result.p_value,
                2.4897925182246257e-15,
                rel_tol=1e-10,
            )
        )

    def test_requires_equal_lengths(self) -> None:
        with self.assertRaisesRegex(ValueError, "equal-length"):
            pearson_correlation(
                [1, 2, 3],
                [1, 2, 3, 4],
            )

    def test_requires_three_paired_observations(self) -> None:
        with self.assertRaisesRegex(ValueError, "at least three"):
            pearson_correlation(
                [1, 2],
                [3, 4],
            )

    def test_rejects_non_finite_observations(self) -> None:
        with self.assertRaisesRegex(ValueError, "finite"):
            pearson_correlation(
                [1, 2, math.nan],
                [3, 4, 5],
            )

    def test_rejects_constant_variables(self) -> None:
        constant_cases = [
            ([1, 1, 1], [2, 3, 4]),
            ([1, 2, 3], [4, 4, 4]),
        ]

        for x_values, y_values in constant_cases:
            with self.subTest(
                x_values=x_values,
                y_values=y_values,
            ):
                with self.assertRaisesRegex(ValueError, "variation"):
                    pearson_correlation(
                        x_values,
                        y_values,
                    )


class SimpleLinearRegressionTests(unittest.TestCase):
    def test_known_simple_linear_regression_result(self) -> None:
        result = simple_linear_regression(
            [10, 12, 14, 16, 18, 20, 22, 24, 26, 28, 30, 32],
            [21, 24, 27, 31, 33, 37, 39, 43, 46, 48, 52, 55],
        )

        self.assertEqual(result.observation_count, 12)
        self.assertAlmostEqual(
            result.slope,
            1.5384615384615385,
            places=12,
        )
        self.assertAlmostEqual(
            result.intercept,
            5.692307692307693,
            places=12,
        )
        self.assertAlmostEqual(
            result.r_squared,
            0.9984116178806445,
            places=12,
        )
        self.assertAlmostEqual(
            result.slope_standard_error,
            0.019404806888827415,
            places=12,
        )
        self.assertTrue(
            math.isclose(
                result.p_value,
                2.4897925182241042e-15,
                rel_tol=1e-10,
            )
        )

    def test_requires_equal_lengths(self) -> None:
        with self.assertRaisesRegex(ValueError, "equal-length"):
            simple_linear_regression(
                [1, 2, 3],
                [1, 2, 3, 4],
            )

    def test_requires_three_paired_observations(self) -> None:
        with self.assertRaisesRegex(ValueError, "at least three"):
            simple_linear_regression(
                [1, 2],
                [3, 4],
            )

    def test_rejects_non_finite_observations(self) -> None:
        with self.assertRaisesRegex(ValueError, "finite"):
            simple_linear_regression(
                [1, 2, math.inf],
                [3, 4, 5],
            )

    def test_rejects_constant_predictor(self) -> None:
        with self.assertRaisesRegex(ValueError, "Predictor"):
            simple_linear_regression(
                [1, 1, 1],
                [2, 3, 4],
            )

    def test_rejects_constant_response(self) -> None:
        with self.assertRaisesRegex(ValueError, "Response"):
            simple_linear_regression(
                [1, 2, 3],
                [4, 4, 4],
            )

if __name__ == "__main__":
    unittest.main()