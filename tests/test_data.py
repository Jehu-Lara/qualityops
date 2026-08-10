from pathlib import Path
import math
import tempfile
import unittest

import pandas as pd

from qualityops.data import extract_measurements, load_excel, load_measurements


class DataTests(unittest.TestCase):
    def test_load_excel_and_extract_measurements(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workbook = Path(temporary_directory) / "measurements.xlsx"
            pd.DataFrame(
                {"machine": ["A", "A", "B"], "measurement": [15.0, None, 15.2]}
            ).to_excel(workbook, index=False)

            loaded = load_excel(workbook)
            extracted = load_measurements(workbook, "measurement")

            self.assertEqual(list(loaded.columns), ["machine", "measurement"])
            self.assertEqual(extracted.values, (15.0, 15.2))
            self.assertEqual(extracted.source_row_count, 3)
            self.assertEqual(extracted.missing_count, 1)

    def test_missing_file_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            missing = Path(temporary_directory) / "missing.xlsx"
            with self.assertRaisesRegex(FileNotFoundError, "not found"):
                load_excel(missing)

    def test_unsupported_extension_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            csv_file = Path(temporary_directory) / "measurements.csv"
            csv_file.write_text("measurement\n15.0\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "xlsx"):
                load_excel(csv_file)

    def test_missing_column_is_rejected(self) -> None:
        dataframe = pd.DataFrame({"measurement": [1.0, 2.0]})
        with self.assertRaisesRegex(KeyError, "Available columns"):
            extract_measurements(dataframe, "diameter")

    def test_non_numeric_values_are_rejected(self) -> None:
        dataframe = pd.DataFrame({"measurement": [1.0, "invalid", 2.0]})
        with self.assertRaisesRegex(ValueError, "row indexes"):
            extract_measurements(dataframe, "measurement")

    def test_infinite_values_are_rejected(self) -> None:
        dataframe = pd.DataFrame({"measurement": [1.0, math.inf]})
        with self.assertRaisesRegex(ValueError, "non-finite"):
            extract_measurements(dataframe, "measurement")


if __name__ == "__main__":
    unittest.main()
