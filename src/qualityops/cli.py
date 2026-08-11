"""Command-line interface for reproducible QualityOps analyses."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path
from typing import Any

from qualityops.analysis import analyze_process
from qualityops.data import load_excel, load_measurements
from qualityops.quality import summarize_dataframe
from qualityops.secom import audit_secom


def _sheet_name(raw_value: str) -> str | int:
    try:
        return int(raw_value)
    except ValueError:
        return raw_value


def build_parser() -> argparse.ArgumentParser:
    """Build the public CLI parser."""

    parser = argparse.ArgumentParser(
        prog="qualityops",
        description="Audit Excel data and calculate process-performance metrics.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect_parser = subparsers.add_parser(
        "inspect", help="Report basic quality checks for one Excel worksheet."
    )
    inspect_parser.add_argument("path", type=Path)
    inspect_parser.add_argument(
        "--sheet",
        default="0",
        help="Worksheet name or zero-based index (default: 0).",
    )

    analyze_parser = subparsers.add_parser(
        "analyze", help="Calculate overall Pp/Ppk and optional Cp/Cpk."
    )
    source = analyze_parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--values", nargs="+", type=float)
    source.add_argument("--file", type=Path)
    analyze_parser.add_argument(
        "--column", help="Measurement column; required with --file."
    )
    analyze_parser.add_argument("--sheet", default="0")
    analyze_parser.add_argument("--lsl", type=float, required=True)
    analyze_parser.add_argument("--usl", type=float, required=True)
    analyze_parser.add_argument(
        "--within-sigma",
        type=float,
        help=(
            "Documented within-subgroup standard deviation. If omitted, "
            "Cp/Cpk are not reported."
        ),
    )

    secom_parser = subparsers.add_parser(
        "audit-secom",
        help="Verify and audit the public UCI SECOM source files.",
    )
    secom_parser.add_argument(
        "--data-dir",
        type=Path,
        required=True,
        help="Directory containing secom.data, secom_labels.data, and secom.names.",
    )
    return parser


def _inspect_payload(args: argparse.Namespace) -> dict[str, Any]:
    dataframe = load_excel(args.path, sheet_name=_sheet_name(args.sheet))
    return {"source": str(args.path), "quality": summarize_dataframe(dataframe)}


def _analysis_payload(args: argparse.Namespace) -> dict[str, Any]:
    source_metadata: dict[str, Any]
    if args.file is not None:
        if not args.column:
            raise ValueError("--column is required when --file is used")
        extracted = load_measurements(
            args.file,
            column=args.column,
            sheet_name=_sheet_name(args.sheet),
        )
        values = extracted.values
        source_metadata = {
            "kind": "excel",
            "path": str(args.file),
            "column": args.column,
            "source_row_count": extracted.source_row_count,
            "missing_measurements_excluded": extracted.missing_count,
        }
    else:
        values = args.values
        source_metadata = {"kind": "command_line", "value_count": len(values)}

    result = analyze_process(
        values,
        lsl=args.lsl,
        usl=args.usl,
        within_sigma=args.within_sigma,
    )
    return {"source": source_metadata, "analysis": asdict(result)}


def _secom_audit_payload(args: argparse.Namespace) -> dict[str, Any]:
    return audit_secom(args.data_dir).to_dict()


def main(argv: Sequence[str] | None = None) -> int:
    """Execute the CLI and return a process exit code."""

    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "inspect":
            payload = _inspect_payload(args)
        elif args.command == "analyze":
            payload = _analysis_payload(args)
        elif args.command == "audit-secom":
            payload = _secom_audit_payload(args)
        else:  # pragma: no cover - argparse restricts this value.
            parser.error(f"Unsupported command: {args.command}")
    except (FileNotFoundError, KeyError, TypeError, ValueError) as error:
        parser.error(str(error))

    print(json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False))
    return 0
