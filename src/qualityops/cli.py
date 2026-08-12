"""Command-line interface for reproducible QualityOps analyses."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path
from typing import Any

from qualityops.analysis import analyze_process
from qualityops.data import load_excel, load_measurements
from qualityops.quality import summarize_dataframe
from qualityops.persistence import (
    SecomDataIntegrityError,
    SecomDatabaseError,
    SecomMigrationError,
    SecomPersistenceConflictError,
    persist_secom,
)
from qualityops.secom import audit_secom


_JSON_ARGUMENT_ERRORS = False


class _CliArgumentError(ValueError):
    pass


class _QualityOpsArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        if _JSON_ARGUMENT_ERRORS:
            raise _CliArgumentError(message)
        super().error(message)


def _sheet_name(raw_value: str) -> str | int:
    try:
        return int(raw_value)
    except ValueError:
        return raw_value


def build_parser() -> argparse.ArgumentParser:
    """Build the public CLI parser."""

    parser = _QualityOpsArgumentParser(
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

    persistence_parser = subparsers.add_parser(
        "load-secom-postgres",
        help="Persist the verified UCI SECOM dataset in PostgreSQL.",
    )
    persistence_parser.add_argument(
        "--data-dir",
        type=Path,
        required=True,
        help="Directory containing quality-report.json and the raw directory.",
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


_PERSISTENCE_ERRORS = {
    "argument_error": "Invalid command arguments.",
    "configuration_error": "QUALITYOPS_DATABASE_URL is required.",
    "data_integrity_error": "SECOM source verification failed.",
    "migration_error": "PostgreSQL schema revision is not supported.",
    "persistence_conflict": (
        "Persisted SECOM data conflicts with the verified source."
    ),
    "database_error": "PostgreSQL operation failed.",
    "internal_error": "SECOM persistence failed.",
}


def _write_compact_json(payload: dict[str, Any], stream: Any) -> None:
    stream.write(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    )


def _write_persistence_error(code: str) -> int:
    _write_compact_json(
        {"error": {"code": code, "message": _PERSISTENCE_ERRORS[code]}},
        sys.stderr,
    )
    return 2


def _run_persistence_command(args: argparse.Namespace) -> int:
    database_url = os.environ.get("QUALITYOPS_DATABASE_URL")
    if not database_url:
        return _write_persistence_error("configuration_error")
    try:
        result = persist_secom(args.data_dir, database_url)
    except SecomDataIntegrityError:
        return _write_persistence_error("data_integrity_error")
    except SecomMigrationError:
        return _write_persistence_error("migration_error")
    except SecomPersistenceConflictError:
        return _write_persistence_error("persistence_conflict")
    except SecomDatabaseError:
        return _write_persistence_error("database_error")
    except Exception:
        return _write_persistence_error("internal_error")
    _write_compact_json(result.to_dict(), sys.stdout)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Execute the CLI and return a process exit code."""

    global _JSON_ARGUMENT_ERRORS
    raw_arguments = list(argv) if argv is not None else sys.argv[1:]
    json_argument_errors = bool(
        raw_arguments and raw_arguments[0] == "load-secom-postgres"
    )
    parser = build_parser()
    previous_mode = _JSON_ARGUMENT_ERRORS
    _JSON_ARGUMENT_ERRORS = json_argument_errors
    try:
        args = parser.parse_args(raw_arguments)
    except _CliArgumentError:
        return _write_persistence_error("argument_error")
    finally:
        _JSON_ARGUMENT_ERRORS = previous_mode
    try:
        if args.command == "inspect":
            payload = _inspect_payload(args)
        elif args.command == "analyze":
            payload = _analysis_payload(args)
        elif args.command == "audit-secom":
            payload = _secom_audit_payload(args)
        elif args.command == "load-secom-postgres":
            return _run_persistence_command(args)
        else:  # pragma: no cover - argparse restricts this value.
            parser.error(f"Unsupported command: {args.command}")
    except (FileNotFoundError, KeyError, TypeError, ValueError) as error:
        parser.error(str(error))

    print(json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False))
    return 0
