import json
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
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

    def test_spc_command_derives_within_sigma_from_subgroups(self) -> None:
        source = (
            Path(__file__).parents[1]
            / "data"
            / "spc"
            / "qualityops_spc_rbar_n4_v1.csv"
        )
        output = StringIO()
        with redirect_stdout(output):
            exit_code = main(
                [
                    "spc",
                    "--file",
                    str(source),
                    "--columns",
                    "measure_1",
                    "measure_2",
                    "measure_3",
                    "measure_4",
                    "--lsl",
                    "495",
                    "--usl",
                    "505",
                    "--target",
                    "500",
                ]
            )

        payload = json.loads(output.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertAlmostEqual(
            payload["analysis"]["chart"]["within_sigma"],
            0.9103448275862079,
        )
        self.assertAlmostEqual(
            payload["analysis"]["potential"]["cpk"],
            1.7831594696970061,
        )


if __name__ == "__main__":
    unittest.main()
