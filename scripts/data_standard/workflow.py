# Orchestrates workspace preparation, candidate refresh, validation, and delivery.

import json
from pathlib import Path

from .common import PipelineError, clean_text, expand_inputs, read_jsonl, utc_now, write_json, write_jsonl
from .constants import SUPPORTED_RULE_SUFFIXES, SUPPORTED_SCHEMA_SUFFIXES, SUPPORTED_STANDARD_SUFFIXES
from .decisions import validate_and_build_rows
from .exporters import BUSINESS_HEADERS, write_csv, write_workbook
from .matching import build_candidates
from .schema_extractors import (
    extract_database_fields,
    extract_ddl_fields,
    extract_sqlite_fields,
    extract_tabular_fields,
    finalize_fields,
)
from .standard_extractors import (
    extract_pdf_standards,
    extract_rules,
    extract_tabular_standards,
    finalize_standards,
    validate_ai_standard,
)


def prepare(args):
    workspace = Path(args.out_dir).expanduser().resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    schema_paths = expand_inputs(args.schema or [], SUPPORTED_SCHEMA_SUFFIXES, "schema input")
    standard_paths = expand_inputs(args.standard or [], SUPPORTED_STANDARD_SUFFIXES, "standard input")
    rule_paths = expand_inputs(args.rules or [], SUPPORTED_RULE_SUFFIXES, "custom-rule input")
    if not schema_paths and not args.database_url_env:
        raise PipelineError("Provide at least one --schema or --database-url-env")
    if not standard_paths:
        raise PipelineError("Provide at least one --standard")

    field_records = []
    for path in schema_paths:
        suffix = path.suffix.casefold()
        if suffix == ".sql":
            field_records.extend(extract_ddl_fields(path))
        elif suffix in {".db", ".sqlite", ".sqlite3"}:
            field_records.extend(extract_sqlite_fields(path))
        else:
            field_records.extend(extract_tabular_fields(path))
    if args.database_url_env:
        field_records.extend(extract_database_fields(args.database_url_env))
    fields = finalize_fields(field_records)

    extracted_standards = []
    pdf_pages = []
    review_queue = []
    for path in standard_paths:
        if path.suffix.casefold() == ".pdf":
            standards, pages, queue = extract_pdf_standards(path)
            extracted_standards.extend(standards)
            pdf_pages.extend(pages)
            review_queue.extend(queue)
        else:
            extracted_standards.extend(extract_tabular_standards(path))
    extracted_standards = finalize_standards(extracted_standards)

    rules = []
    for path in rule_paths:
        rules.extend(extract_rules(path))

    write_jsonl(workspace / "fields.jsonl", fields)
    write_jsonl(workspace / "standards_extracted.jsonl", extracted_standards)
    write_jsonl(workspace / "pdf_pages.jsonl", pdf_pages)
    write_jsonl(workspace / "pdf_review_queue.jsonl", review_queue)
    write_jsonl(workspace / "rules.jsonl", rules)
    ai_items = workspace / "ai_standard_items.jsonl"
    if not ai_items.exists():
        write_jsonl(ai_items, [])
    decisions = workspace / "decisions"
    decisions.mkdir(exist_ok=True)
    for filename in (
        "normative_mappings.jsonl",
        "general_rules.jsonl",
        "recommendations.jsonl",
    ):
        path = decisions / filename
        if not path.exists():
            write_jsonl(path, [])
    write_json(
        workspace / "manifest.json",
        {
            "created_at": utc_now(),
            "schema_inputs": path_strings(schema_paths),
            "standard_inputs": path_strings(standard_paths),
            "rule_inputs": path_strings(rule_paths),
            "database_url_environment": args.database_url_env or "",
            "top_k": args.top_k,
        },
    )
    refresh_workspace(workspace)


def path_strings(paths):
    result = []
    for path in paths:
        result.append(str(path))
    return result


def refresh_workspace(workspace):
    fields = read_jsonl(workspace / "fields.jsonl")
    extracted = read_jsonl(workspace / "standards_extracted.jsonl")
    ai_raw = read_jsonl(workspace / "ai_standard_items.jsonl", required=False)
    ai_items = []
    for index, record in enumerate(ai_raw, start=1):
        ai_items.append(validate_ai_standard(record, index))
    all_standards = list(extracted)
    all_standards.extend(ai_items)
    standards = finalize_standards(all_standards)
    manifest_path = workspace / "manifest.json"
    if not manifest_path.exists():
        raise PipelineError(f"Missing workspace manifest: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    top_k = int(manifest.get("top_k", 5))
    candidates = build_candidates(fields, standards, top_k)
    write_jsonl(workspace / "standards.jsonl", standards)
    write_jsonl(workspace / "match_candidates.jsonl", candidates)
    rules = read_jsonl(workspace / "rules.jsonl", required=False)
    review_queue = read_jsonl(workspace / "pdf_review_queue.jsonl", required=False)
    summary = {
        "updated_at": utc_now(),
        "field_count": len(fields),
        "extracted_standard_count": len(extracted),
        "ai_reviewed_standard_count": len(ai_items),
        "standard_count": len(standards),
        "rule_count": len(rules),
        "pdf_review_page_count": len(review_queue),
        "field_candidate_count": count_fields_with_candidates(candidates),
        "files": {
            "fields": "fields.jsonl",
            "standards": "standards.jsonl",
            "candidates": "match_candidates.jsonl",
            "rules": "rules.jsonl",
            "pdf_pages": "pdf_pages.jsonl",
            "pdf_review_queue": "pdf_review_queue.jsonl",
            "ai_standard_items": "ai_standard_items.jsonl",
            "decisions": "decisions",
        },
    }
    write_json(workspace / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def count_fields_with_candidates(candidates):
    count = 0
    for item in candidates:
        if item.get("candidates"):
            count += 1
    return count


def build(args):
    workspace = Path(args.workspace).expanduser().resolve()
    output = Path(args.output).expanduser().resolve()
    if output.suffix.casefold() != ".xlsx":
        raise PipelineError("--output must end with .xlsx")
    fields = read_jsonl(workspace / "fields.jsonl")
    standards = read_jsonl(workspace / "standards.jsonl")
    rules = read_jsonl(workspace / "rules.jsonl", required=False)
    decisions = workspace / "decisions"
    normative = read_jsonl(decisions / "normative_mappings.jsonl")
    general = read_jsonl(decisions / "general_rules.jsonl")
    recommendations = read_jsonl(decisions / "recommendations.jsonl")
    business_rows, uncovered, issues = validate_and_build_rows(
        fields, standards, rules, normative, general, recommendations
    )
    failures = []
    if not business_rows:
        failures.append("No business standards were generated")
    if uncovered:
        failures.append(f"{len(uncovered)} fields are completely uncovered")
    if failures and not args.allow_incomplete:
        raise PipelineError(
            "; ".join(failures)
            + ". Add decisions, or use --allow-incomplete only when producing a draft"
        )
    write_workbook(output, business_rows, fields, standards, rules, uncovered, issues)
    csv_path = output.with_suffix(".csv")
    jsonl_path = output.with_suffix(".jsonl")
    write_csv(csv_path, business_rows, BUSINESS_HEADERS)
    write_jsonl(jsonl_path, business_rows)
    type_counts = {}
    for row in business_rows:
        standard_type = clean_text(row.get("standard_type"))
        current_count = type_counts.get(standard_type, 0)
        type_counts[standard_type] = current_count + 1
    report = {
        "built_at": utc_now(),
        "output": str(output),
        "csv_output": str(csv_path),
        "jsonl_output": str(jsonl_path),
        "field_count": len(fields),
        "standard_count": len(standards),
        "rule_count": len(rules),
        "business_standard_count": len(business_rows),
        "business_standard_type_counts": type_counts,
        "uncovered_field_count": len(uncovered),
        "uncovered_fields": uncovered,
        "review_issue_count": len(issues),
        "review_issues": issues,
        "draft": bool(args.allow_incomplete and failures),
    }
    write_json(output.parent / "build_report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
