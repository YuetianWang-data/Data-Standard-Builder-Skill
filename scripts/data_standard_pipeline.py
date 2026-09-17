#!/usr/bin/env python3
# Provides the stable executable entry point and backward-compatible public imports.

import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from data_standard.cli import build_parser, main
from data_standard.common import PipelineError, TableRows, read_jsonl
from data_standard.decisions import validate_and_build_rows
from data_standard.exporters import write_workbook
from data_standard.matching import build_candidates
from data_standard.schema_extractors import extract_ddl_fields
from data_standard.standard_extractors import extract_rules, finalize_standards

__all__ = [
    "PipelineError",
    "TableRows",
    "build_candidates",
    "build_parser",
    "extract_ddl_fields",
    "extract_rules",
    "finalize_standards",
    "main",
    "read_jsonl",
    "validate_and_build_rows",
    "write_workbook",
]

if __name__ == "__main__":
    raise SystemExit(main())
