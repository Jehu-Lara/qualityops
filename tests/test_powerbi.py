from __future__ import annotations

from collections import Counter
import csv
from datetime import date, datetime
import hashlib
import json
import math
from pathlib import Path
import re
import struct
import subprocess
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
POWERBI_ROOT = REPOSITORY_ROOT / "powerbi"
REPORT_ROOT = POWERBI_ROOT / "QualityOpsProcessHealth.Report"
MODEL_ROOT = POWERBI_ROOT / "QualityOpsProcessHealth.SemanticModel"
TABLE_ROOT = MODEL_ROOT / "definition" / "tables"
DAX_ROOT = MODEL_ROOT / "DAXQueries"
VALIDATION_ROOT = POWERBI_ROOT / "validation"
RESULT_ROOT = VALIDATION_ROOT / "query-results"
DATA_ROOT = REPOSITORY_ROOT / "data" / "external" / "secom"

DATASET_CODE = "uci-secom"
VERSION_LABEL = "uci-secom-acquisition-2026-08-10"
FINGERPRINT = "57856B2CA3ED8E782F88E6A9DEDC61623A4B370ED8442BB89B03BC3B44610BF7"
READER_ROLE = "qualityops_powerbi_reader"
SOURCE_MAIN_COMMIT = "c2c299fb80d22c8d4b1c8efc0bfd7eddea380f94"

QUERY_NAMES = (
    "01_dataset_provenance",
    "03_load_reconciliation",
    "04_outcome_distribution",
    "05_daily_yield",
    "07_sensor_missingness",
    "13_standardized_mean_difference",
)
EXPECTED_ROWS = dict(zip(QUERY_NAMES, (1, 1, 2, 86, 590, 590), strict=True))

ALLOWED_SQL_RELATIONS = {
    "dataset",
    "dataset_version",
    "observation",
    "sensor",
    "measurement",
}


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _json(path: Path) -> dict[str, object]:
    return json.loads(_read(path))


def _compact_code(value: str) -> str:
    result: list[str] = []
    delimiter: str | None = None
    closing = {"'": "'", '"': '"', "[": "]"}
    for character in value:
        if delimiter is None:
            if character in closing:
                delimiter = closing[character]
                result.append(character)
            elif not character.isspace():
                result.append(character)
        else:
            result.append(character)
            if character == delimiter:
                delimiter = None
    return "".join(result)


def _indented_block(text: str, kind: str, name: str) -> str:
    escaped = re.escape(name)
    pattern = re.compile(
        rf"(?ms)^\t{kind} (?:'{escaped}'|{escaped})(?:\s*=.*?)?\n"
        rf"(?P<body>.*?)(?=^\t(?:column|measure|partition) |\Z)"
    )
    match = pattern.search(text)
    if match is None:
        raise AssertionError(f"Missing {kind} block: {name}")
    return match.group(0)


def _tsv_rows(name: str) -> list[dict[str, str]]:
    path = RESULT_ROOT / f"{name}.tsv"
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def _is_close(actual: float, expected: float) -> bool:
    return math.isclose(actual, expected, rel_tol=1e-9, abs_tol=1e-12)


class _Welford:
    __slots__ = ("count", "mean", "m2")

    def __init__(self) -> None:
        self.count = 0
        self.mean = 0.0
        self.m2 = 0.0

    def add(self, value: float) -> None:
        self.count += 1
        delta = value - self.mean
        self.mean += delta / self.count
        self.m2 += delta * (value - self.mean)

    @property
    def variance(self) -> float | None:
        return self.m2 / (self.count - 1) if self.count >= 2 else None


class PowerBIContractTests(unittest.TestCase):
    maxDiff = None

    def test_01_artifact_allowlist_and_local_state_exclusions(self) -> None:
        required_ignores = {
            "powerbi/**/*.pbix",
            "powerbi/**/*.pbit",
            "powerbi/**/*.pbids",
            "powerbi/**/.pbi/localSettings.json",
            "powerbi/**/.pbi/cache.abf",
            "powerbi/**/.pbi/unappliedChanges.json",
            "powerbi/**/.pbi/daxQueries.json",
            "powerbi/**/.pbi/tmdlscripts.json",
            "powerbi/**/TMDLScripts/",
            "powerbi/**/.platform",
            "powerbi/validation/raw/",
        }
        gitignore_lines = set(_read(REPOSITORY_ROOT / ".gitignore").splitlines())
        self.assertTrue(required_ignores.issubset(gitignore_lines))

        expected_attributes = (
            "data/external/secom/raw/secom.data -text -diff\n"
            "data/external/secom/raw/secom_labels.data -text -diff\n"
            "data/external/secom/raw/secom.names -text -diff\n"
            ".gitattributes text eol=lf\n"
            "powerbi/validation/query-results/*.tsv text eol=lf\n"
            "powerbi/validation/validation-summary.json text eol=lf\n"
        ).encode("utf-8")
        self.assertEqual((REPOSITORY_ROOT / ".gitattributes").read_bytes(), expected_attributes)

        forbidden_names = {
            "localSettings.json",
            "cache.abf",
            "unappliedChanges.json",
            "daxQueries.json",
            "tmdlscripts.json",
            "model.bim",
            "mobileState.json",
        }
        forbidden_suffixes = {".pbix", ".pbit", ".pbids", ".pbiviz"}
        unignored: list[Path] = []
        for path in POWERBI_ROOT.rglob("*"):
            if not path.is_file():
                continue
            completed = subprocess.run(
                ["git", "check-ignore", "-q", "--", str(path)],
                cwd=REPOSITORY_ROOT,
                check=False,
            )
            if completed.returncode != 0:
                unignored.append(path)
        for path in unignored:
            self.assertNotIn(path.name, forbidden_names)
            self.assertNotIn(path.suffix.lower(), forbidden_suffixes)
            self.assertNotIn("TMDLScripts", path.parts)
            self.assertNotEqual(path.name, ".platform")

        relative_resources = sorted(
            path.relative_to(REPOSITORY_ROOT).as_posix()
            for path in (REPORT_ROOT / "StaticResources").rglob("*.json")
        )
        self.assertEqual(
            relative_resources,
            [
                "powerbi/QualityOpsProcessHealth.Report/StaticResources/RegisteredResources/QualityOps_Process_Health3526366761134794.json",
                "powerbi/QualityOpsProcessHealth.Report/StaticResources/SharedResources/BaseThemes/CY26SU07.json",
            ],
        )
        for resource in relative_resources:
            payload = (REPOSITORY_ROOT / resource).read_bytes()
            self.assertFalse(payload.startswith(b"\xef\xbb\xbf"))
            json.loads(payload.decode("utf-8"))

    def test_02_pbip_references_pbir_tmdl_and_one_page(self) -> None:
        pbip = _json(POWERBI_ROOT / "QualityOpsProcessHealth.pbip")
        self.assertEqual(pbip["version"], "1.0")
        self.assertEqual(
            pbip["artifacts"],
            [{"report": {"path": "QualityOpsProcessHealth.Report"}}],
        )
        pbir = _json(REPORT_ROOT / "definition.pbir")
        self.assertEqual(pbir["version"], "4.0")
        self.assertEqual(
            pbir["datasetReference"]["byPath"]["path"],
            "../QualityOpsProcessHealth.SemanticModel",
        )
        self.assertEqual(_json(MODEL_ROOT / "definition.pbism")["version"], "4.2")
        self.assertIn("compatibilityLevel: 1606", _read(MODEL_ROOT / "definition" / "database.tmdl"))

        pages = _json(REPORT_ROOT / "definition" / "pages" / "pages.json")
        self.assertEqual(len(pages["pageOrder"]), 1)
        self.assertEqual(pages["activePageName"], pages["pageOrder"][0])
        page = _json(
            REPORT_ROOT
            / "definition"
            / "pages"
            / pages["activePageName"]
            / "page.json"
        )
        self.assertEqual(page["displayName"], "Process Health")
        self.assertEqual((page["width"], page["height"]), (1280, 720))
        self.assertNotIn("mobileState", json.dumps(page))

    def test_03_semantic_model_tables_columns_visibility_and_relationships(self) -> None:
        table_files = sorted(path.name for path in TABLE_ROOT.glob("*.tmdl"))
        self.assertEqual(
            table_files,
            [
                "DatasetVersion.tmdl",
                "Measurement.tmdl",
                "Observation.tmdl",
                "Process Health Measures.tmdl",
                "Sensor.tmdl",
            ],
        )
        model = _read(MODEL_ROOT / "definition" / "model.tmdl")
        self.assertIn("culture: en-US", model)
        self.assertIn("sourceQueryCulture: en-US", model)
        self.assertIn("discourageImplicitMeasures", model)
        self.assertIn("__PBI_TimeIntelligenceEnabled = 0", model)
        self.assertNotRegex(model, r"LocalDateTable|DateTableTemplate")

        expected_columns = {
            "DatasetVersion.tmdl": {
                "dataset_version_id": ("int64", True),
                "dataset_code": ("string", False),
                "name": ("string", False),
                "publisher": ("string", False),
                "doi": ("string", False),
                "source_url": ("string", False),
                "license_spdx": ("string", False),
                "version_label": ("string", False),
                "content_fingerprint": ("string", True),
                "acquired_on": ("dateTime", False),
                "loaded_at": ("dateTime", True),
                "audit_schema_version": ("int64", True),
                "observation_count": ("int64", True),
                "sensor_count": ("int64", True),
                "measurement_count": ("int64", True),
                "missing_measurement_count": ("int64", True),
            },
            "Observation.tmdl": {
                "source_row": ("int64", True),
                "observed_at": ("dateTime", False),
                "observed_date": ("dateTime", False),
                "outcome": ("int64", True),
                "outcome_name": ("string", False),
            },
            "Sensor.tmdl": {
                "sensor_index": ("int64", True),
                "sensor_key": ("string", False),
            },
            "Measurement.tmdl": {
                "source_row": ("int64", True),
                "sensor_index": ("int64", True),
                "value": ("double", False),
                "is_missing": ("boolean", True),
            },
        }
        for filename, columns in expected_columns.items():
            text_value = _read(TABLE_ROOT / filename)
            actual_names = set(re.findall(r"(?m)^\tcolumn ([A-Za-z_][A-Za-z0-9_]*)", text_value))
            self.assertEqual(actual_names, set(columns), filename)
            for column, (data_type, hidden) in columns.items():
                block = _indented_block(text_value, "column", column)
                self.assertIn(f"dataType: {data_type}", block)
                self.assertEqual("\n\t\tisHidden" in block, hidden)
        self.assertIn("sortByColumn: outcome", _indented_block(_read(TABLE_ROOT / "Observation.tmdl"), "column", "outcome_name"))
        self.assertIn("sortByColumn: sensor_index", _indented_block(_read(TABLE_ROOT / "Sensor.tmdl"), "column", "sensor_key"))

        relationships = _read(MODEL_ROOT / "definition" / "relationships.tmdl")
        self.assertEqual(len(re.findall(r"(?m)^relationship ", relationships)), 2)
        self.assertIn("fromColumn: Measurement.source_row", relationships)
        self.assertIn("toColumn: Observation.source_row", relationships)
        self.assertIn("fromColumn: Measurement.sensor_index", relationships)
        self.assertIn("toColumn: Sensor.sensor_index", relationships)
        self.assertNotRegex(relationships, r"crossFilteringBehavior|isActive: false|joinOnDateBehavior")

    def test_04_power_query_import_canonical_guard_and_no_native_sql(self) -> None:
        expressions = _read(MODEL_ROOT / "definition" / "expressions.tmdl")
        parameters = {
            "PostgreSQLServer": "127.0.0.1:5432",
            "PostgreSQLDatabase": "qualityops_test_secom",
            "DatasetCode": DATASET_CODE,
            "VersionLabel": VERSION_LABEL,
            "ContentFingerprint": FINGERPRINT,
        }
        for name, value in parameters.items():
            self.assertRegex(
                expressions,
                rf'(?m)^expression {re.escape(name)} = "{re.escape(value)}" meta '
                rf'\[IsParameterQuery=true, Type="Text", IsParameterQueryRequired=true\]$',
            )
        self.assertIn("PostgreSQL.Database(", expressions)
        self.assertIn("[CreateNavigationProperties = false]", expressions)
        for forbidden in ("Value.NativeQuery", "Query =", "QUALITYOPS_DATABASE_URL", "QUALITYOPS_TEST_DATABASE_URL"):
            self.assertNotIn(forbidden, expressions)
        self.assertIn('Item = "dataset"', expressions)
        self.assertIn('Item = "dataset_version"', expressions)
        self.assertIn("[dataset_code] = DatasetCode", expressions)
        self.assertIn("[version_label] = VersionLabel", expressions)
        self.assertIn("[content_fingerprint] = ContentFingerprint", expressions)
        self.assertIn("Table.Buffer(CanonicalVersionRows)", expressions)
        self.assertIn("if RowCount <> 1 then", expressions)
        self.assertIn("dataset_version_id] <= 0", expressions)

        for filename, item, selected in (
            ("Observation.tmdl", "observation", '{"source_row", "observed_at", "outcome"}'),
            ("Sensor.tmdl", "sensor", '{"sensor_index", "sensor_key"}'),
            ("Measurement.tmdl", "measurement", '{"source_row", "sensor_index", "value"}'),
        ):
            table = _read(TABLE_ROOT / filename)
            self.assertIn("mode: import", table)
            self.assertIn(f'Item = "{item}"', table)
            self.assertIn("CanonicalVersionRows", table)
            self.assertIn("JoinKind.Inner", table)
            self.assertIn(selected, table)
            self.assertNotIn("Table.TransformColumnTypes", table)
            self.assertRegex(table, r"(?s)Selected = Table\.SelectColumns\(.*?\)\s*in\s*Selected\s*$")
        dataset_version = _read(TABLE_ROOT / "DatasetVersion.tmdl")
        self.assertIn('"loaded_at", type datetimezone', dataset_version)
        self.assertIn('DateTimeZone.ToUtc(_)', dataset_version)
        self.assertIn('"en-US"', dataset_version)

    def test_05_measure_names_metadata_formats_and_visibility(self) -> None:
        text_value = _read(TABLE_ROOT / "Process Health Measures.tmdl")
        measure_names = re.findall(r"(?m)^\tmeasure '([^']+)'", text_value)
        expected = [
            "Observation Count", "Pass Count", "Fail Count", "Fail Rate",
            "Measurement Count", "Missing Measurement Count", "Nonmissing Count",
            "Missing Rate", "Outcome Share", "Dataset Version Row Count",
            "Expected Observation Count", "Expected Sensor Count",
            "Expected Measurement Count", "Expected Missing Measurement Count",
            "Actual Observation Count", "Actual Sensor Count", "Actual Measurement Count",
            "Actual Missing Measurement Count", "Observations With Invalid Measurement Count",
            "Reconciliation Status", "Pass Nonmissing Count", "Fail Nonmissing Count",
            "Pass Mean", "Fail Mean", "Pass Sample Variance", "Fail Sample Variance",
            "Pooled Variance", "Standardized Mean Difference",
            "Absolute Standardized Mean Difference", "Missingness Rank",
            "Standardized Difference Rank",
        ]
        self.assertEqual(measure_names, expected)
        hidden = {
            "Dataset Version Row Count", "Expected Observation Count", "Expected Sensor Count",
            "Expected Measurement Count", "Expected Missing Measurement Count",
            "Actual Observation Count", "Actual Sensor Count", "Actual Measurement Count",
            "Actual Missing Measurement Count", "Observations With Invalid Measurement Count",
            "Missingness Rank", "Standardized Difference Rank",
        }
        for name in expected:
            block = _indented_block(text_value, "measure", name)
            self.assertRegex(
                text_value,
                rf"(?m)^\t/// .+\n\tmeasure '{re.escape(name)}'\s*=",
            )
            self.assertRegex(block, r"(?m)^\t\tdisplayFolder: (Health|Reconciliation|Sensor diagnostics)$")
            self.assertEqual("\n\t\tisHidden" in block, name in hidden)
            if name != "Reconciliation Status":
                self.assertRegex(block, r"(?m)^\t\tformatString: .+$")
            else:
                self.assertNotIn("formatString:", block)
        anchor = _indented_block(text_value, "column", "measure_anchor")
        self.assertIn("isHidden", anchor)
        self.assertIn('DATATABLE("measure_anchor", INTEGER, {{1}})', text_value)

    def test_06_measure_formulas_are_contractual(self) -> None:
        compact = _compact_code(_read(TABLE_ROOT / "Process Health Measures.tmdl"))
        required = (
            "measure'Observation Count'=COUNTROWS(Observation)",
            "measure'Pass Count'=CALCULATE([Observation Count],REMOVEFILTERS(Observation[outcome],Observation[outcome_name]),Observation[outcome]=-1)",
            "measure'Fail Count'=CALCULATE([Observation Count],REMOVEFILTERS(Observation[outcome],Observation[outcome_name]),Observation[outcome]=1)",
            "measure'Fail Rate'=DIVIDE([Fail Count],[Observation Count])",
            "measure'Missing Measurement Count'=CALCULATE([Measurement Count],Measurement[is_missing]=TRUE())",
            "measure'Nonmissing Count'=CALCULATE([Measurement Count],Measurement[is_missing]=FALSE())",
            "measure'Missing Rate'=DIVIDE([Missing Measurement Count],[Measurement Count])",
            "measure'Dataset Version Row Count'=CALCULATE(COUNTROWS(DatasetVersion),REMOVEFILTERS())",
            "measure'Actual Missing Measurement Count'=CALCULATE(COUNTROWS(Measurement),REMOVEFILTERS(),Measurement[is_missing]=TRUE())",
            "TREATAS({CurrentSourceRow},Observation[source_row])",
            '"MATCH","CONFLICT"',
            "VAR.S(Measurement[value])",
            "(NFail-1)*FailVariance+(NPass-1)*PassVariance",
            "DIVIDE(FailAverage-PassAverage,SQRT(Pooled))",
            "ABS(Difference)",
            "CandidateValue=CurrentValue&&CandidateIndex<CurrentSensorIndex",
        )
        for expression in required:
            self.assertIn(_compact_code(expression), compact)
        self.assertNotIn("VAR.P(", compact)
        self.assertNotIn("RANKX(", compact)
        self.assertNotIn("ALLSELECTED(", compact)
        observation = _compact_code(_read(TABLE_ROOT / "Observation.tmdl"))
        measurement = _compact_code(_read(TABLE_ROOT / "Measurement.tmdl"))
        self.assertIn("DATE(YEAR(Observation[observed_at]),MONTH(Observation[observed_at]),DAY(Observation[observed_at]))", observation)
        self.assertIn('SWITCH(Observation[outcome],-1,"pass",1,"fail",BLANK())', observation)
        self.assertIn("columnis_missing=ISBLANK(Measurement[value])", measurement)

    def test_07_dax_queries_and_sql_dependencies_are_exact(self) -> None:
        actual = sorted(path.name for path in DAX_ROOT.glob("*.dax"))
        self.assertEqual(actual, [f"{name}.dax" for name in QUERY_NAMES])
        expected_headers = {
            "01_dataset_provenance": ["dataset_version_id", "dataset_code", "name", "publisher", "doi", "source_url", "license_spdx", "version_label", "acquired_on", "loaded_at", "audit_schema_version", "content_fingerprint"],
            "03_load_reconciliation": ["dataset_version_id", "expected_observation_count", "actual_observation_count", "observations_match", "expected_sensor_count", "actual_sensor_count", "sensors_match", "expected_measurement_count", "actual_measurement_count", "measurements_match", "expected_missing_measurement_count", "actual_missing_measurement_count", "missing_measurements_match", "measurements_per_observation_match"],
            "04_outcome_distribution": ["dataset_version_id", "outcome", "outcome_name", "observation_count", "observation_percentage"],
            "05_daily_yield": ["dataset_version_id", "observed_date", "observation_count", "pass_count", "fail_count", "fail_rate"],
            "07_sensor_missingness": ["dataset_version_id", "sensor_index", "sensor_key", "measurement_count", "nonmissing_count", "missing_count", "missing_rate"],
            "13_standardized_mean_difference": ["dataset_version_id", "sensor_index", "sensor_key", "pass_count", "pass_mean", "pass_sample_variance", "fail_count", "fail_mean", "fail_sample_variance", "pooled_variance", "standardized_mean_difference"],
        }
        for name in QUERY_NAMES:
            dax = _read(DAX_ROOT / f"{name}.dax")
            self.assertTrue(dax.endswith("\n"))
            self.assertIn("EVALUATE", dax)
            self.assertIn("dataset_version_id", dax)
            self.assertIn("ORDER BY", dax if name != "03_load_reconciliation" else dax + " ORDER BY")
            self.assertNotRegex(dax, r"(?i)\b(?:INFO|CREATE|ALTER|DROP|INSERT|UPDATE|DELETE|MERGE)\b")
            aliases = re.findall(r'^\s*"([a-z][a-z0-9_]*)",', dax, re.MULTILINE)
            projected = [alias for alias in aliases if not alias.endswith("_value")]
            if name != "03_load_reconciliation":
                self.assertEqual(projected[-len(expected_headers[name]):], expected_headers[name])
            sql = _read(REPOSITORY_ROOT / "sql" / "queries" / f"{name}.sql")
            relations = set(re.findall(r"\bqualityops\.([a-z_]+)\b", sql))
            self.assertTrue(relations)
            self.assertTrue(relations.issubset(ALLOWED_SQL_RELATIONS), (name, relations))
            self.assertNotRegex(sql, r"qualityops\.(?:source_file|v_measurement_fact)|public\.alembic_version")
        self.assertEqual(_read(DAX_ROOT / "05_daily_yield.dax").count("COALESCE("), 3)
        self.assertEqual(_read(DAX_ROOT / "07_sensor_missingness.dax").count("COALESCE("), 2)
        self.assertEqual(
            sum(_read(path).count("COALESCE(") for path in DAX_ROOT.glob("*.dax")),
            5,
        )

    def test_08_report_visuals_layout_filters_and_interactions(self) -> None:
        page_paths = list((REPORT_ROOT / "definition" / "pages").glob("*/page.json"))
        self.assertEqual(len(page_paths), 1)
        page = _json(page_paths[0])
        visual_paths = sorted(page_paths[0].parent.glob("visuals/*/visual.json"))
        self.assertEqual(len(visual_paths), 12)
        visuals = [_json(path) for path in visual_paths]

        expected = {
            "title": ((24, 16, 960, 50), "textbox"),
            "status": ((1000, 16, 256, 50), "cardVisual"),
            "observation": ((24, 82, 240, 100), "cardVisual"),
            "pass": ((272, 82, 240, 100), "cardVisual"),
            "fail": ((520, 82, 240, 100), "cardVisual"),
            "fail_rate": ((768, 82, 240, 100), "cardVisual"),
            "missing_rate": ((1016, 82, 240, 100), "cardVisual"),
            "outcome": ((24, 198, 360, 210), "donutChart"),
            "daily": ((400, 198, 856, 210), "lineChart"),
            "missingness": ((24, 424, 600, 230), "barChart"),
            "smd": ((640, 424, 616, 230), "barChart"),
            "footer": ((24, 670, 1232, 26), "textbox"),
        }

        def locate(bounds: tuple[int, int, int, int]) -> dict[str, object]:
            matches = []
            for item in visuals:
                actual = tuple(float(item["position"][key]) for key in ("x", "y", "width", "height"))
                if all(abs(left - right) <= 2 for left, right in zip(actual, bounds, strict=True)):
                    matches.append(item)
            self.assertEqual(len(matches), 1, bounds)
            return matches[0]

        located = {name: locate(bounds) for name, (bounds, _) in expected.items()}
        for name, (_, visual_type) in expected.items():
            self.assertEqual(located[name]["visual"]["visualType"], visual_type, name)

        for left_index, left in enumerate(visuals):
            left_position = left["position"]
            self.assertGreaterEqual(float(left_position["x"]), 0)
            self.assertGreaterEqual(float(left_position["y"]), 0)
            self.assertLessEqual(float(left_position["x"]) + float(left_position["width"]), 1280)
            self.assertLessEqual(float(left_position["y"]) + float(left_position["height"]), 720)
            for right in visuals[left_index + 1:]:
                right_position = right["position"]
                overlap = not (
                    float(left_position["x"]) + float(left_position["width"]) <= float(right_position["x"])
                    or float(right_position["x"]) + float(right_position["width"]) <= float(left_position["x"])
                    or float(left_position["y"]) + float(left_position["height"]) <= float(right_position["y"])
                    or float(right_position["y"]) + float(right_position["height"]) <= float(left_position["y"])
                )
                self.assertFalse(overlap, (left["name"], right["name"]))

        def query_refs(item: dict[str, object], role: str) -> list[str]:
            projections = item["visual"]["query"]["queryState"][role]["projections"]
            return [projection["queryRef"] for projection in projections]

        self.assertEqual(query_refs(located["status"], "Data"), ["Process Health Measures.Reconciliation Status"])
        card_measures = {
            "observation": "Observation Count",
            "pass": "Pass Count",
            "fail": "Fail Count",
            "fail_rate": "Fail Rate",
            "missing_rate": "Missing Rate",
        }
        for name, measure_name in card_measures.items():
            self.assertEqual(query_refs(located[name], "Data"), [f"Process Health Measures.{measure_name}"])

        self.assertEqual(query_refs(located["outcome"], "Category"), ["Observation.outcome_name"])
        self.assertEqual(query_refs(located["outcome"], "Y"), ["Process Health Measures.Observation Count"])
        self.assertEqual(query_refs(located["outcome"], "Tooltips"), ["Process Health Measures.Outcome Share"])
        self.assertEqual(query_refs(located["daily"], "Category"), ["Observation.observed_date"])
        self.assertEqual(query_refs(located["daily"], "Y"), ["Process Health Measures.Fail Rate"])
        self.assertEqual(
            query_refs(located["daily"], "Tooltips"),
            [
                "Process Health Measures.Observation Count",
                "Process Health Measures.Pass Count",
                "Process Health Measures.Fail Count",
                "Process Health Measures.Fail Rate",
            ],
        )
        self.assertEqual(query_refs(located["missingness"], "Category"), ["Sensor.sensor_key"])
        self.assertEqual(query_refs(located["missingness"], "Y"), ["Process Health Measures.Missing Rate"])
        self.assertEqual(query_refs(located["smd"], "Category"), ["Sensor.sensor_key"])
        self.assertEqual(query_refs(located["smd"], "Y"), ["Process Health Measures.Standardized Mean Difference"])

        for name, rank in (("missingness", "Missingness Rank"), ("smd", "Standardized Difference Rank")):
            item = located[name]
            filters = item["filterConfig"]["filters"]
            self.assertEqual(len(filters), 1)
            self.assertEqual(filters[0]["type"], "Advanced")
            self.assertEqual(filters[0]["field"]["Measure"]["Property"], rank)
            comparison = filters[0]["filter"]["Where"][0]["Condition"]["Comparison"]
            self.assertEqual(comparison["ComparisonKind"], 4)
            self.assertEqual(comparison["Right"]["Literal"]["Value"], "10L")
            sort = item["visual"]["query"]["sortDefinition"]
            self.assertTrue(sort["isDefaultSort"])
            self.assertEqual(sort["sort"], [{"field": {"Measure": {"Expression": {"SourceRef": {"Entity": "Process Health Measures"}}, "Property": rank}}, "direction": "Ascending"}])

        outcome_objects = located["outcome"]["visual"]["objects"]
        self.assertEqual(outcome_objects["labels"][0]["properties"]["labelStyle"]["expr"]["Literal"]["Value"], "'Category, data value, percent of total'")
        daily_objects = located["daily"]["visual"]["objects"]
        self.assertEqual(daily_objects["categoryAxis"][0]["properties"]["axisType"]["expr"]["Literal"]["Value"], "'Scalar'")
        self.assertEqual(daily_objects["lineStyles"][0]["properties"]["showMarker"]["expr"]["Literal"]["Value"], "true")
        self.assertEqual(daily_objects["lineStyles"][0]["properties"]["lineChartType"]["expr"]["Literal"]["Value"], "'linear'")
        smd_objects = located["smd"]["visual"]["objects"]
        self.assertIn("Conditional", smd_objects["dataPoint"][0]["properties"]["fill"]["solid"]["color"]["expr"])
        self.assertEqual(smd_objects["xAxisReferenceLine"][0]["properties"]["value"]["expr"]["Literal"]["Value"], "0D")

        informative_names = {located[name]["name"] for name in expected if name not in {"title", "footer"}}
        interactions = page["visualInteractions"]
        self.assertEqual(len(interactions), 90)
        self.assertEqual(
            {(item["source"], item["target"], item["type"]) for item in interactions},
            {(source, target, "NoFilter") for source in informative_names for target in informative_names if source != target},
        )
        self.assertEqual(
            sum(len(item.get("filterConfig", {}).get("filters", [])) for item in visuals),
            2,
        )
        serialized = json.dumps({"page": page, "visuals": visuals}, sort_keys=True)
        self.assertNotRegex(serialized, r"(?i)customVisual|drillthrough|bookmark|slicer|persistedSelection")

    def test_09_accessibility_theme_and_persistent_state(self) -> None:
        theme = _json(POWERBI_ROOT / "theme" / "qualityops-process-health.json")
        serialized_theme = json.dumps(theme).upper()
        for color in ("#F7F9FC", "#17233C", "#175CD3", "#1B7F5A", "#B42318", "#B54708", "#FFFFFF"):
            self.assertIn(color, serialized_theme)
        visual_paths = sorted((REPORT_ROOT / "definition" / "pages").rglob("visual.json"))
        self.assertEqual(len(visual_paths), 12)
        visuals = [_json(path) for path in visual_paths]
        informative = [item for item in visuals if item.get("visual", {}).get("visualType") != "textbox"]
        self.assertEqual(len(informative), 10)
        tab_orders = sorted(int(item["position"]["tabOrder"]) for item in informative)
        self.assertEqual(tab_orders, list(range(1, 11)))
        decorative = [item for item in visuals if item.get("visual", {}).get("visualType") == "textbox"]
        self.assertEqual([int(item["position"]["tabOrder"]) for item in decorative], [0, 0])
        for item in informative:
            general = item["visual"]["visualContainerObjects"]["general"]
            self.assertEqual(len(general), 1)
            encoded = general[0]["properties"]["altText"]["expr"]["Literal"]["Value"]
            self.assertTrue(encoded.startswith("'") and encoded.endswith("'"))
            alt_text = encoded[1:-1].replace("''", "'")
            self.assertTrue(alt_text.strip())
            self.assertLessEqual(len(alt_text), 250)

        textboxes = []
        for item in decorative:
            paragraph = item["visual"]["objects"]["general"][0]["properties"]["paragraphs"][0]
            textboxes.append("".join(run["value"] for run in paragraph["textRuns"]))
        self.assertEqual(
            sorted(textboxes),
            sorted(
                [
                    "SECOM Process Health",
                    "Source: UCI SECOM · DOI 10.24432/C54305 · CC BY 4.0 · Descriptive portfolio demonstration; associations do not establish causality or process capability.",
                ]
            ),
        )

        def luminance(hex_color: str) -> float:
            channels = [int(hex_color[index:index + 2], 16) / 255 for index in (1, 3, 5)]
            linear = [value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4 for value in channels]
            return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]

        def contrast(left: str, right: str) -> float:
            light, dark = sorted((luminance(left), luminance(right)), reverse=True)
            return (light + 0.05) / (dark + 0.05)

        self.assertGreaterEqual(contrast("#17233C", "#F7F9FC"), 4.5)
        self.assertGreaterEqual(contrast("#FFFFFF", "#1B7F5A"), 4.5)
        self.assertGreaterEqual(contrast("#FFFFFF", "#B42318"), 4.5)

        status = next(
            item for item in informative
            if item["visual"]["query"]["queryState"]["Data"]["projections"][0]["queryRef"]
            == "Process Health Measures.Reconciliation Status"
        )
        conditional = status["visual"]["objects"]["fillCustom"][0]["properties"]["fillColor"]["solid"]["color"]["expr"]["Conditional"]
        self.assertEqual(conditional["Cases"][0]["Condition"]["Comparison"]["Right"]["Literal"]["Value"], "'MATCH'")
        self.assertEqual(conditional["Cases"][0]["Value"]["Literal"]["Value"], "'#1B7F5A'")
        self.assertEqual(conditional["DefaultValue"]["Literal"]["Value"], "'#B42318'")

        page = _json(next((REPORT_ROOT / "definition" / "pages").glob("*/page.json")))
        self.assertNotIn("filterConfig", page)
        serialized = json.dumps({"page": page, "visuals": visuals}, sort_keys=True)
        self.assertNotRegex(serialized, r"(?i)slicerState|persistedSelection|selectedDataPoint|bookmark")

    def test_10_validation_results_oracles_documentation_claims_and_secrets(self) -> None:
        expected_headers = {
            "01_dataset_provenance": ["dataset_version_id", "dataset_code", "name", "publisher", "doi", "source_url", "license_spdx", "version_label", "acquired_on", "loaded_at", "audit_schema_version", "content_fingerprint"],
            "03_load_reconciliation": ["dataset_version_id", "expected_observation_count", "actual_observation_count", "observations_match", "expected_sensor_count", "actual_sensor_count", "sensors_match", "expected_measurement_count", "actual_measurement_count", "measurements_match", "expected_missing_measurement_count", "actual_missing_measurement_count", "missing_measurements_match", "measurements_per_observation_match"],
            "04_outcome_distribution": ["dataset_version_id", "outcome", "outcome_name", "observation_count", "observation_percentage"],
            "05_daily_yield": ["dataset_version_id", "observed_date", "observation_count", "pass_count", "fail_count", "fail_rate"],
            "07_sensor_missingness": ["dataset_version_id", "sensor_index", "sensor_key", "measurement_count", "nonmissing_count", "missing_count", "missing_rate"],
            "13_standardized_mean_difference": ["dataset_version_id", "sensor_index", "sensor_key", "pass_count", "pass_mean", "pass_sample_variance", "fail_count", "fail_mean", "fail_sample_variance", "pooled_variance", "standardized_mean_difference"],
        }
        for name, headers in expected_headers.items():
            path = RESULT_ROOT / f"{name}.tsv"
            data = path.read_bytes()
            self.assertFalse(data.startswith(b"\xef\xbb\xbf"))
            self.assertNotIn(b"\r", data)
            self.assertTrue(data.endswith(b"\n"))
            self.assertFalse(data.endswith(b"\n\n"))
            with path.open("r", encoding="utf-8", newline="") as handle:
                reader = csv.DictReader(handle, delimiter="\t")
                self.assertEqual(reader.fieldnames, headers)
                rows = list(reader)
            self.assertEqual(len(rows), EXPECTED_ROWS[name])
            self.assertRegex(hashlib.sha256(data).hexdigest().upper(), r"^[0-9A-F]{64}$")
            self.assertEqual({row["dataset_version_id"] for row in rows}, {"NON_NULL_BIGINT"})
        self.assertEqual(
            _tsv_rows("01_dataset_provenance")[0]["loaded_at"],
            "NON_NULL_TIMESTAMPTZ",
        )

        self._assert_independent_source_oracles()

        powerbi_readme = _read(POWERBI_ROOT / "README.md")
        architecture = _read(REPOSITORY_ROOT / "docs" / "powerbi-process-health.md")
        roadmap = _read(REPOSITORY_ROOT / "ROADMAP.md")
        claims = _read(REPOSITORY_ROOT / "docs" / "portfolio-claims.md")
        for required in ("PBIP", "PBIR", "TMDL", "Import", READER_ROLE, "DAX"):
            self.assertIn(required, powerbi_readme + architecture)
        self.assertIn(
            "complete — gate a and gate b complete; draft pr #19 created; four required checks passed; merge pending explicit authorization",
            roadmap.lower(),
        )
        self.assertIn("gate a and gate b are complete", claims.lower())
        self.assertIn("vista power bi reproducible de una página", claims.lower())
        self.assertIn("do not establish causality", architecture)
        self.assertIn("PBIR_SCHEMA_UNREACHABLE", architecture)
        self.assertIn("visualContainer/2.11.0", architecture)
        self.assertIn("internal scrollbar", architecture)

        workflow = _read(REPOSITORY_ROOT / ".github" / "workflows" / "ci.yml")
        create_reader = _read(
            POWERBI_ROOT / "postgresql" / "02_create_reader_role.sql"
        )
        for required in (
            "name: Python ${{ matrix.python-version }}",
            "name: PostgreSQL 16 / Python 3.13",
            "runs-on: ubuntu-24.04",
            "sudo systemctl start postgresql",
            'marker="$RUNNER_TEMP/qualityops_powerbi_reader_created"',
            "trap on_exit EXIT",
            "02_create_reader_role.sql",
            "04_revoke_reader_access.sql",
            "05_drop_reader_role.sql",
            "QUALITYOPS_POWERBI_READER_DATABASE_URL",
            "QUALITYOPS_RUN_POSTGRES_INTEGRATION=1",
        ):
            self.assertIn(required, workflow)
        self.assertEqual(workflow.count("if: always()"), 2)
        self.assertNotRegex(workflow, r"(?i)docker|compose|service container")
        self.assertNotRegex(
            workflow,
            r"(?m)^\s*echo\s+.*QUALITYOPS_POWERBI_READER_PASSWORD=.*GITHUB_ENV",
        )
        self.assertNotIn("--set=reader_password", workflow)
        self.assertIn(
            r"\getenv reader_password QUALITYOPS_POWERBI_READER_PASSWORD",
            create_reader,
        )

        summary = VALIDATION_ROOT / "validation-summary.json"
        screenshot = REPOSITORY_ROOT / "docs" / "assets" / "powerbi-process-health.png"
        self.assertTrue(summary.is_file())
        self.assertTrue(screenshot.is_file())

        summary_payload = _json(summary)
        self.assertEqual(
            set(summary_payload),
            {
                "schema_version", "source_main_commit", "validated_at_utc",
                "power_bi_desktop_version", "python_version",
                "postgresql_server_version_num", "core_autocrlf",
                "project_format", "report_format", "semantic_model_format",
                "connectivity_mode", "model_culture", "desktop_locale",
                "power_query_culture", "results_grid_locale", "dataset_code",
                "version_label", "content_fingerprint", "reader_role",
                "refresh_succeeded", "reopen_succeeded",
                "query_folding_verified", "page_count",
                "generated_static_resource_paths", "table_row_counts",
                "query_results",
            },
        )
        self.assertEqual(summary_payload["schema_version"], 1)
        self.assertEqual(summary_payload["source_main_commit"], SOURCE_MAIN_COMMIT)
        self.assertRegex(summary_payload["validated_at_utc"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
        self.assertTrue(summary_payload["power_bi_desktop_version"].startswith("2.156.951.0 64-bit"))
        self.assertRegex(summary_payload["python_version"], r"^3\.\d+\.\d+")
        self.assertTrue(160000 <= summary_payload["postgresql_server_version_num"] < 170000)
        self.assertIs(summary_payload["core_autocrlf"], True)
        for key, value in {
            "project_format": "PBIP", "report_format": "PBIR",
            "semantic_model_format": "TMDL", "connectivity_mode": "Import",
            "model_culture": "en-US", "desktop_locale": "en-US",
            "power_query_culture": "en-US", "results_grid_locale": "en-US",
            "dataset_code": DATASET_CODE, "version_label": VERSION_LABEL,
            "content_fingerprint": FINGERPRINT, "reader_role": READER_ROLE,
        }.items():
            self.assertEqual(summary_payload[key], value)
        for key in ("refresh_succeeded", "reopen_succeeded", "query_folding_verified"):
            self.assertIs(summary_payload[key], True)
        self.assertEqual(summary_payload["page_count"], 1)
        self.assertEqual(
            summary_payload["generated_static_resource_paths"],
            [
                "powerbi/QualityOpsProcessHealth.Report/StaticResources/RegisteredResources/QualityOps_Process_Health3526366761134794.json",
                "powerbi/QualityOpsProcessHealth.Report/StaticResources/SharedResources/BaseThemes/CY26SU07.json",
            ],
        )
        self.assertEqual(
            summary_payload["table_row_counts"],
            {"DatasetVersion": 1, "Observation": 1567, "Sensor": 590, "Measurement": 924530, "Process Health Measures": 1},
        )
        self.assertEqual(set(summary_payload["query_results"]), {f"{name}.dax" for name in QUERY_NAMES})
        for name in QUERY_NAMES:
            item = summary_payload["query_results"][f"{name}.dax"]
            self.assertEqual(set(item), {"row_count", "mismatch_count", "max_absolute_error", "sha256"})
            self.assertEqual(item["row_count"], EXPECTED_ROWS[name])
            self.assertEqual(item["mismatch_count"], 0)
            self.assertIsInstance(item["max_absolute_error"], (int, float))
            self.assertTrue(math.isfinite(item["max_absolute_error"]))
            self.assertGreaterEqual(item["max_absolute_error"], 0)
            expected_hash = hashlib.sha256((RESULT_ROOT / f"{name}.tsv").read_bytes()).hexdigest().upper()
            self.assertEqual(item["sha256"], expected_hash)
        summary_text = _read(summary)
        self.assertNotIn("dataset_version_id", summary_text)
        self.assertNotIn("loaded_at", summary_text)

        png = screenshot.read_bytes()
        self.assertTrue(png.startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertEqual(png[12:16], b"IHDR")
        width, height = struct.unpack(">II", png[16:24])
        self.assertGreaterEqual(width, 1280)
        self.assertGreaterEqual(height, 720)
        self.assertEqual(width * 9, height * 16)

        sensitive_patterns = (
            re.compile(r"C:\\Users\\", re.IGNORECASE),
            re.compile(r"postgres(?:ql)?://[^\s\"']+", re.IGNORECASE),
            re.compile(r"(?i)(?:password|pwd)\s*[:=]\s*[^\s,}\]]+"),
            re.compile(r"(?i)(?:tenant|workspace)[_-]?id\s*[:=]"),
        )
        candidates = [
            path for path in POWERBI_ROOT.rglob("*")
            if path.is_file()
            and path.suffix.lower() in {".json", ".tmdl", ".dax", ".pbip", ".pbir", ".py", ".sql", ".md", ".tsv"}
            and "raw" not in path.parts
            and not any(part == ".pbi" for part in path.parts)
        ]
        candidates.extend(
            [
                REPOSITORY_ROOT / "README.md",
                REPOSITORY_ROOT / "ROADMAP.md",
                REPOSITORY_ROOT / "CHANGELOG.md",
                REPOSITORY_ROOT / "docs" / "portfolio-claims.md",
                REPOSITORY_ROOT / "docs" / "powerbi-process-health.md",
            ]
        )
        for path in candidates:
            text_value = _read(path)
            if path.name == "02_create_reader_role.sql":
                text_value = text_value.replace(
                    "PASSWORD :'reader_password'", "PASSWORD PARAMETER"
                )
            for pattern in sensitive_patterns:
                self.assertIsNone(pattern.search(text_value), (path, pattern.pattern))

    def _assert_independent_source_oracles(self) -> None:
        report = json.loads(_read(DATA_ROOT / "quality-report.json"))
        label_pattern = re.compile(r'^(-1|1) "(\d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2})"$')
        outcomes: list[int] = []
        observed: list[datetime] = []
        for line in _read(DATA_ROOT / "raw" / "secom_labels.data").splitlines():
            match = label_pattern.fullmatch(line)
            self.assertIsNotNone(match)
            outcomes.append(int(match.group(1)))
            observed.append(datetime.strptime(match.group(2), "%d/%m/%Y %H:%M:%S"))
        self.assertEqual(len(outcomes), 1567)

        pass_stats = [_Welford() for _ in range(590)]
        fail_stats = [_Welford() for _ in range(590)]
        missing = [0] * 590
        measurement_path = DATA_ROOT / "raw" / "secom.data"
        with measurement_path.open("r", encoding="utf-8") as handle:
            row_count = 0
            for row_count, (line, outcome) in enumerate(zip(handle, outcomes, strict=True), start=1):
                values = line.split()
                self.assertEqual(len(values), 590)
                target = pass_stats if outcome == -1 else fail_stats
                for index, token in enumerate(values):
                    if token == "NaN":
                        missing[index] += 1
                    else:
                        value = float(token)
                        self.assertTrue(math.isfinite(value))
                        target[index].add(value)
        self.assertEqual(row_count, 1567)

        provenance = _tsv_rows("01_dataset_provenance")[0]
        dataset = report["dataset"]
        self.assertEqual(
            provenance,
            {
                "dataset_version_id": "NON_NULL_BIGINT",
                "dataset_code": DATASET_CODE,
                "name": dataset["name"],
                "publisher": dataset["publisher"],
                "doi": dataset["doi"],
                "source_url": dataset["source_url"],
                "license_spdx": "CC-BY-4.0",
                "version_label": VERSION_LABEL,
                "acquired_on": dataset["retrieved_on"],
                "loaded_at": "NON_NULL_TIMESTAMPTZ",
                "audit_schema_version": "1",
                "content_fingerprint": FINGERPRINT,
            },
        )

        reconciliation = _tsv_rows("03_load_reconciliation")[0]
        expected_reconciliation = {
            "dataset_version_id": "NON_NULL_BIGINT",
            "expected_observation_count": "1567",
            "actual_observation_count": "1567",
            "observations_match": "true",
            "expected_sensor_count": "590",
            "actual_sensor_count": "590",
            "sensors_match": "true",
            "expected_measurement_count": "924530",
            "actual_measurement_count": "924530",
            "measurements_match": "true",
            "expected_missing_measurement_count": "41951",
            "actual_missing_measurement_count": "41951",
            "missing_measurements_match": "true",
            "measurements_per_observation_match": "true",
        }
        self.assertEqual(reconciliation, expected_reconciliation)

        counts = Counter(outcomes)
        outcome_rows = _tsv_rows("04_outcome_distribution")
        for row, outcome in zip(outcome_rows, (-1, 1), strict=True):
            self.assertEqual(int(row["outcome"]), outcome)
            self.assertEqual(row["outcome_name"], "pass" if outcome == -1 else "fail")
            self.assertEqual(int(row["observation_count"]), counts[outcome])
            self.assertTrue(_is_close(float(row["observation_percentage"]), 100 * counts[outcome] / 1567))

        daily: dict[date, Counter[int]] = {}
        for timestamp, outcome in zip(observed, outcomes, strict=True):
            daily.setdefault(timestamp.date(), Counter())[outcome] += 1
        daily_rows = _tsv_rows("05_daily_yield")
        self.assertEqual([row["observed_date"] for row in daily_rows], [item.isoformat() for item in sorted(daily)])
        for row, day in zip(daily_rows, sorted(daily), strict=True):
            count = daily[day]
            total = count[-1] + count[1]
            self.assertEqual(int(row["observation_count"]), total)
            self.assertEqual(int(row["pass_count"]), count[-1])
            self.assertEqual(int(row["fail_count"]), count[1])
            self.assertTrue(_is_close(float(row["fail_rate"]), count[1] / total))

        missing_rows = _tsv_rows("07_sensor_missingness")
        for index, row in enumerate(missing_rows):
            self.assertEqual(int(row["sensor_index"]), index)
            self.assertEqual(row["sensor_key"], f"sensor_{index:03d}")
            self.assertEqual(int(row["measurement_count"]), 1567)
            self.assertEqual(int(row["missing_count"]), missing[index])
            self.assertEqual(int(row["nonmissing_count"]), 1567 - missing[index])
            self.assertTrue(_is_close(float(row["missing_rate"]), missing[index] / 1567))
        self.assertEqual(sum(missing), report["quality"]["missing_cell_count"])

        expected_smd: list[dict[str, object]] = []
        for index, (passed, failed) in enumerate(zip(pass_stats, fail_stats, strict=True)):
            pass_variance = passed.variance
            fail_variance = failed.variance
            pooled = None
            difference = None
            degrees = passed.count + failed.count - 2
            if pass_variance is not None and fail_variance is not None and degrees > 0:
                pooled = (
                    (failed.count - 1) * fail_variance
                    + (passed.count - 1) * pass_variance
                ) / degrees
                if pooled > 0:
                    difference = (failed.mean - passed.mean) / math.sqrt(pooled)
            expected_smd.append(
                {
                    "sensor_index": index,
                    "sensor_key": f"sensor_{index:03d}",
                    "pass_count": passed.count,
                    "pass_mean": passed.mean,
                    "pass_sample_variance": pass_variance,
                    "fail_count": failed.count,
                    "fail_mean": failed.mean,
                    "fail_sample_variance": fail_variance,
                    "pooled_variance": pooled,
                    "standardized_mean_difference": difference,
                }
            )
        expected_smd.sort(
            key=lambda row: (
                row["standardized_mean_difference"] is None,
                -abs(row["standardized_mean_difference"])
                if row["standardized_mean_difference"] is not None
                else 0.0,
                row["sensor_index"],
            )
        )
        smd_rows = _tsv_rows("13_standardized_mean_difference")
        expected_smd_by_index = {
            row["sensor_index"]: row for row in expected_smd
        }
        float_columns = (
            "pass_mean", "pass_sample_variance", "fail_mean",
            "fail_sample_variance", "pooled_variance", "standardized_mean_difference",
        )
        nonnull = 0
        for position, actual in enumerate(smd_rows):
            expected = expected_smd_by_index[int(actual["sensor_index"])]
            self.assertEqual(int(actual["sensor_index"]), expected["sensor_index"])
            self.assertEqual(actual["sensor_key"], expected["sensor_key"])
            self.assertEqual(int(actual["pass_count"]), expected["pass_count"])
            self.assertEqual(int(actual["fail_count"]), expected["fail_count"])
            for column in float_columns:
                actual_value = None if actual[column] == "NULL" else float(actual[column])
                expected_value = expected[column]
                if expected_value is None:
                    self.assertIsNone(actual_value)
                else:
                    self.assertIsNotNone(actual_value)
                    self.assertTrue(_is_close(actual_value, expected_value), (column, expected["sensor_index"]))
            nonnull += actual["standardized_mean_difference"] != "NULL"
            if position:
                previous = smd_rows[position - 1]
                previous_value = previous["standardized_mean_difference"]
                current_value = actual["standardized_mean_difference"]
                if previous_value == "NULL":
                    self.assertEqual(current_value, "NULL")
                elif current_value != "NULL":
                    previous_absolute = abs(float(previous_value))
                    current_absolute = abs(float(current_value))
                    self.assertGreaterEqual(previous_absolute, current_absolute)
                    if previous_absolute == current_absolute:
                        self.assertLess(
                            int(previous["sensor_index"]), int(actual["sensor_index"])
                        )
        self.assertEqual(nonnull, 474)
        self.assertEqual(len(smd_rows) - nonnull, 116)
        self.assertEqual(
            [int(row["sensor_index"]) for row in smd_rows[:10]],
            [59, 103, 510, 348, 158, 111, 431, 293, 85, 434],
        )


if __name__ == "__main__":
    unittest.main()
