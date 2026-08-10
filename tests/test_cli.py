import json
from contextlib import redirect_stdout
from io import StringIO
import unittest

from qualityops.cli import main


class CliTests(unittest.TestCase):
    def test_inline_analysis_outputs_valid_json(self) -> None:
        output = StringIO()
        with redirect_stdout(output):
            exit_code = main(
                [
                    "analyze",
                    "--values",
                    "9",
                    "10",
                    "11",
                    "--lsl",
                    "7",
                    "--usl",
                    "13",
                ]
            )

        payload = json.loads(output.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["analysis"]["overall"]["ppk"], 1.0)
        self.assertIsNone(payload["analysis"]["potential"])

    def test_within_sigma_enables_cp_and_cpk(self) -> None:
        output = StringIO()
        with redirect_stdout(output):
            main(
                [
                    "analyze",
                    "--values",
                    "9",
                    "10",
                    "11",
                    "--lsl",
                    "7",
                    "--usl",
                    "13",
                    "--within-sigma",
                    "0.5",
                ]
            )

        payload = json.loads(output.getvalue())
        self.assertEqual(payload["analysis"]["potential"]["cpk"], 2.0)


if __name__ == "__main__":
    unittest.main()
