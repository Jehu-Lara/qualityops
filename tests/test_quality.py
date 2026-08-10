import unittest

import pandas as pd

from qualityops.quality import summarize_dataframe


class QualityTests(unittest.TestCase):
    def test_summary_counts_quality_issues(self) -> None:
        dataframe = pd.DataFrame(
            {
                "machine": ["A", "A", None, "A"],
                "measurement": [10.0, 10.0, None, 10.0],
            }
        )

        summary = summarize_dataframe(dataframe)

        self.assertEqual(summary["row_count"], 4)
        self.assertEqual(summary["column_count"], 2)
        self.assertEqual(summary["missing_cell_count"], 2)
        self.assertEqual(summary["empty_rows"], 1)
        self.assertEqual(summary["duplicate_rows"], 2)
        self.assertEqual(summary["missing_values"], {"machine": 1, "measurement": 1})
        self.assertEqual(summary["data_types"]["measurement"], "float64")


if __name__ == "__main__":
    unittest.main()
