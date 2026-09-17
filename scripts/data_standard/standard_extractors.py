# Extracts normative standards and user rules from structured files and PDFs.

import re

from .common import PipelineError, TableRows, clean_text, compact, read_text_with_fallback, stable_id
from .constants import RULE_ALIASES, STANDARD_ALIASES
from .tabular import canonicalize_dict, load_csv_rows, load_excel_rows, load_json_records, records_from_rows


STANDARD_FIELDS = (
    "chinese_name",
    "english_name",
    "standard_code",
    "definition",
    "data_type",
    "data_format",
    "value_domain",
    "unit",
    "synonyms",
    "remarks",
)


def clean_standard_fields(record):
    standard = {}
    for key in STANDARD_FIELDS:
        standard[key] = clean_text(record.get(key))
    return standard


def extract_tabular_standards(path):
    raw_records = []
    if path.suffix.casefold() == ".csv":
        for table in load_csv_rows(path):
            raw_records.extend(
                records_from_rows(table, STANDARD_ALIASES, {"chinese_name", "standard_code"})
            )
    elif path.suffix.casefold() in {".xlsx", ".xlsm"}:
        for table in load_excel_rows(path):
            raw_records.extend(
                records_from_rows(table, STANDARD_ALIASES, {"chinese_name", "standard_code"})
            )
    else:
        for record in load_json_records(path):
            canonical = canonicalize_dict(record, STANDARD_ALIASES)
            canonical["_location"] = f"{path.name}:json"
            raw_records.append(canonical)
    standards = []
    for record in raw_records:
        if not clean_text(record.get("chinese_name")) and not clean_text(record.get("standard_code")):
            continue
        location = clean_text(record.get("_location")) or path.name
        standard = clean_standard_fields(record)
        standard["source_file"] = path.name
        standard["source_location"] = location
        standard["page"] = ""
        standard["evidence"] = ""
        standard["extraction_method"] = "structured"
        standards.append(standard)
    return standards


def require_pdfplumber():
    try:
        import pdfplumber
    except ImportError as exc:
        raise PipelineError("PDF processing requires pdfplumber; install requirements.txt") from exc
    return pdfplumber


def extract_pdf_standards(path):
    pdfplumber = require_pdfplumber()
    standards = []
    pages = []
    review_queue = []
    with pdfplumber.open(path) as document:
        for page_number, page in enumerate(document.pages, start=1):
            text = clean_text(page.extract_text(x_tolerance=2, y_tolerance=3) or "")
            page_record = {
                "source_file": path.name,
                "page": page_number,
                "text": text,
            }
            pages.append(page_record)
            page_rows = 0
            tables = page.extract_tables() or []
            for table_index, raw_table in enumerate(tables, start=1):
                rows = []
                for row in raw_table:
                    if not row:
                        continue
                    clean_row = []
                    for cell in row:
                        clean_row.append(clean_text(cell))
                    rows.append(clean_row)
                location = f"{path.name}:page:{page_number}:table:{table_index}"
                for record in records_from_rows(
                    TableRows(rows=rows, location=location),
                    STANDARD_ALIASES,
                    {"chinese_name", "standard_code"},
                ):
                    if not clean_text(record.get("chinese_name")) and not clean_text(
                        record.get("standard_code")
                    ):
                        continue
                    standard = clean_standard_fields(record)
                    standard["source_file"] = path.name
                    standard["source_location"] = clean_text(record.get("_location"))
                    standard["page"] = page_number
                    standard["evidence"] = ""
                    standard["extraction_method"] = "pdf_table"
                    standards.append(standard)
                    page_rows += 1
            has_standard_signals = any(
                signal in text
                for signal in ("数据元", "中文名称", "英文名称", "数据格式", "值域", "定义")
            )
            if not text:
                review_queue.append(
                    {
                        "source_file": path.name,
                        "page": page_number,
                        "reason": "The page has no extractable text; it may require OCR or manual review",
                        "text_preview": "",
                    }
                )
            elif page_rows == 0 and (has_standard_signals or tables):
                review_queue.append(
                    {
                        "source_file": path.name,
                        "page": page_number,
                        "reason": "The page contains data-element signals, but no structured row was extracted reliably",
                        "text_preview": text[:300],
                    }
                )
    return standards, pages, review_queue


def finalize_standards(records):
    result = []
    seen_keys = set()
    for raw in records:
        record = {}
        for key, value in raw.items():
            record[key] = clean_text(value)
        key = (
            compact(record.get("source_file")),
            compact(record.get("standard_code")),
            compact(record.get("chinese_name")),
            compact(record.get("english_name")),
            compact(record.get("definition"))[:80],
        )
        if key in seen_keys:
            continue
        seen_keys.add(key)
        record["standard_id"] = stable_id(
            "STD",
            record.get("source_file"),
            record.get("source_location"),
            record.get("page"),
            record.get("standard_code"),
            record.get("chinese_name"),
            record.get("english_name"),
        )
        result.append(record)
    return result


def extract_rules(path):
    raw_records = []
    suffix = path.suffix.casefold()
    if suffix in {".txt", ".md"}:
        text = read_text_with_fallback(path)
        for line_number, raw_line in enumerate(text.splitlines(), start=1):
            line = re.sub(r"^\s*(?:[-*+]|\d+[.)、])\s*", "", raw_line).strip()
            if not line or line.startswith("#"):
                continue
            raw_records.append(
                {
                    "rule_name": line[:50],
                    "rule_content": line,
                    "source": path.name,
                    "_location": f"{path.name}:line:{line_number}",
                }
            )
    elif suffix == ".csv":
        for table in load_csv_rows(path):
            raw_records.extend(
                records_from_rows(table, RULE_ALIASES, {"rule_content", "rule_name"})
            )
    elif suffix in {".xlsx", ".xlsm"}:
        for table in load_excel_rows(path):
            raw_records.extend(
                records_from_rows(table, RULE_ALIASES, {"rule_content", "rule_name"})
            )
    else:
        for record in load_json_records(path):
            canonical = canonicalize_dict(record, RULE_ALIASES)
            canonical["_location"] = f"{path.name}:json"
            raw_records.append(canonical)
    rules = []
    for index, record in enumerate(raw_records, start=1):
        content = clean_text(record.get("rule_content")) or clean_text(record.get("rule_name"))
        if not content:
            continue
        rule_id = clean_text(record.get("rule_id")) or stable_id(
            "RULE", path.name, record.get("_location"), content
        )
        rules.append(
            {
                "rule_id": rule_id,
                "system_name": clean_text(record.get("system_name")),
                "table_name": clean_text(record.get("table_name")),
                "model_name": clean_text(record.get("model_name")),
                "rule_name": clean_text(record.get("rule_name")) or content[:50],
                "rule_content": content,
                "problem_description": clean_text(record.get("problem_description")),
                "rule_status": clean_text(record.get("rule_status")),
                "scope": clean_text(record.get("scope")),
                "target": clean_text(record.get("target")),
                "severity": clean_text(record.get("severity")),
                "source": clean_text(record.get("source")) or path.name,
                "source_location": clean_text(record.get("_location")) or f"{path.name}:item:{index}",
            }
        )
    return rules

def validate_ai_standard(record, index):
    source_file = clean_text(record.get("source_file"))
    page = clean_text(record.get("page"))
    evidence = clean_text(record.get("evidence"))
    name = clean_text(record.get("chinese_name"))
    code = clean_text(record.get("standard_code"))
    if not source_file or not page or not evidence:
        raise PipelineError(
            f"ai_standard_items.jsonl item {index} is missing source_file, page, or evidence"
        )
    if not name and not code:
        raise PipelineError(
            f"ai_standard_items.jsonl item {index} is missing a source-language name or standard code"
        )
    normalized = clean_standard_fields(record)
    normalized["source_file"] = source_file
    normalized["page"] = page
    normalized["evidence"] = evidence
    normalized["source_location"] = f"{source_file}:page:{page}:ai-reviewed"
    normalized["extraction_method"] = "ai_reviewed"
    return normalized
