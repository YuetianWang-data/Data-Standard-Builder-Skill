# Maps multilingual headers and loads normalized rows from CSV, Excel, and JSON.

import csv
import json

from .common import PipelineError, TableRows, clean_text, compact, read_text_with_fallback


def alias_lookup(aliases):
    result = {}
    for canonical_name, names in aliases.items():
        all_names = [canonical_name]
        all_names.extend(names)
        for name in all_names:
            result[compact(name)] = canonical_name
    return result


def map_header(value, aliases):
    normalized = compact(value)
    if not normalized:
        return None
    lookup = alias_lookup(aliases)
    if normalized in lookup:
        return lookup[normalized]
    matches = set()
    for alias, canonical in lookup.items():
        if len(alias) >= 3 and (alias in normalized or normalized in alias):
            matches.add(canonical)
    if len(matches) == 1:
        return matches.pop()
    return None


def detect_header(rows, aliases, required_any, scan_limit=20):
    best = None
    for row_index, row in enumerate(rows[:scan_limit]):
        mapping = {}
        for column_index, cell in enumerate(row):
            canonical = map_header(cell, aliases)
            if canonical and canonical not in mapping.values():
                mapping[column_index] = canonical
        found = set(mapping.values())
        if not found.intersection(required_any):
            continue
        score = len(found) * 10 - row_index
        if best is None or score > best[0]:
            best = (score, row_index, mapping)
    if best is None:
        return None
    return best[1], best[2]


def records_from_rows(table, aliases, required_any):
    detected = detect_header(table.rows, aliases, required_any)
    if detected is None:
        return []
    header_index, mapping = detected
    result = []
    for row_number, row in enumerate(table.rows[header_index + 1 :], start=header_index + 2):
        record = {}
        for column_index, canonical in mapping.items():
            value = ""
            if column_index < len(row):
                value = clean_text(row[column_index])
            record[canonical] = value
        if not any(record.values()):
            continue
        non_empty_cells = []
        for cell in row:
            if clean_text(cell):
                non_empty_cells.append(cell)
        header_cells = 0
        for cell in non_empty_cells:
            if map_header(cell, aliases):
                header_cells += 1
        if non_empty_cells and header_cells == len(non_empty_cells):
            continue
        record["_location"] = f"{table.location}:row:{row_number}"
        result.append(record)
    return result


def load_csv_rows(path):
    text = read_text_with_fallback(path)
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",\t;|")
    except csv.Error:
        dialect = csv.excel
    rows = []
    reader = csv.reader(text.splitlines(), dialect)
    for row in reader:
        clean_row = []
        for cell in row:
            clean_row.append(clean_text(cell))
        rows.append(clean_row)
    return [TableRows(rows=rows, location=f"{path.name}:sheet:CSV")]


def require_openpyxl():
    try:
        import openpyxl
    except ImportError as exc:
        raise PipelineError(
            "Reading or writing Excel files requires openpyxl; install requirements.txt"
        ) from exc
    return openpyxl


def load_excel_rows(path):
    openpyxl = require_openpyxl()
    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    tables = []
    try:
        for sheet in workbook.worksheets:
            rows = []
            for row in sheet.iter_rows(values_only=True):
                clean_row = []
                for cell in row:
                    clean_row.append(clean_text(cell))
                rows.append(clean_row)
            tables.append(TableRows(rows=rows, location=f"{path.name}:sheet:{sheet.title}"))
    finally:
        workbook.close()
    return tables


def only_dicts(values):
    records = []
    for value in values:
        if isinstance(value, dict):
            records.append(value)
    return records


def load_json_records(path):
    with path.open("r", encoding="utf-8-sig") as handle:
        value = json.load(handle)
    if isinstance(value, list):
        return only_dicts(value)
    if isinstance(value, dict):
        for key in ("items", "records", "fields", "standards", "rules", "data"):
            nested = value.get(key)
            if isinstance(nested, list):
                return only_dicts(nested)
        return [value]
    raise PipelineError(f"The JSON root must be an object or array: {path}")


def canonicalize_dict(record, aliases):
    result = {}
    for key, value in record.items():
        canonical = map_header(key, aliases)
        if canonical and canonical not in result:
            result[canonical] = clean_text(value)
    return result
