# Extracts field metadata from DDL, SQLite, tabular inventories, and live databases.

import os
import re
import sqlite3

from .common import PipelineError, clean_text, compact, normalize_identifier, read_text_with_fallback
from .constants import CONSTRAINT_WORDS, FIELD_ALIASES, NO, YES
from .tabular import canonicalize_dict, load_csv_rows, load_excel_rows, load_json_records, records_from_rows


def split_sql_columns(body):
    parts = []
    current = []
    depth = 0
    quote = None
    index = 0
    while index < len(body):
        char = body[index]
        if quote:
            current.append(char)
            if char == quote:
                if index + 1 < len(body) and body[index + 1] == quote and quote in {"'", '"'}:
                    current.append(body[index + 1])
                    index += 1
                else:
                    quote = None
        elif char in {"'", '"', "`"}:
            quote = char
            current.append(char)
        elif char == "[":
            quote = "]"
            current.append(char)
        elif char == "(":
            depth += 1
            current.append(char)
        elif char == ")":
            depth = max(0, depth - 1)
            current.append(char)
        elif char == "," and depth == 0:
            part = "".join(current).strip()
            if part:
                parts.append(part)
            current = []
        else:
            current.append(char)
        index += 1
    part = "".join(current).strip()
    if part:
        parts.append(part)
    return parts


def find_create_table_blocks(sql):
    pattern = re.compile(
        r"\bCREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?"
        r"(?P<name>(?:[`\"\[]?[\w\u4e00-\u9fff]+[`\"\]]?\.)?"
        r"[`\"\[]?[\w\u4e00-\u9fff]+[`\"\]]?)\s*\(",
        re.IGNORECASE,
    )
    for match in pattern.finditer(sql):
        depth = 1
        quote = None
        index = match.end()
        start = index
        while index < len(sql) and depth:
            char = sql[index]
            if quote:
                if char == quote:
                    if index + 1 < len(sql) and sql[index + 1] == quote and quote in {"'", '"'}:
                        index += 1
                    else:
                        quote = None
            elif char in {"'", '"', "`"}:
                quote = char
            elif char == "[":
                quote = "]"
            elif char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
            index += 1
        if depth == 0:
            yield normalize_identifier(match.group("name")), sql[start : index - 1]


def extract_inline_comment(rest):
    match = re.search(r"\bCOMMENT\s+(?:IS\s+)?(['\"])(.*?)\1", rest, re.IGNORECASE | re.DOTALL)
    if match:
        return clean_text(match.group(2))
    return ""


def parse_type_and_constraints(rest):
    upper = rest.upper()
    cut = len(rest)
    for word in CONSTRAINT_WORDS:
        match = re.search(rf"\b{re.escape(word)}\b", upper)
        if match:
            cut = min(cut, match.start())
    type_decl = clean_text(rest[:cut])
    if not type_decl:
        return "", "", rest
    length_match = re.search(r"\(([^)]*)\)", type_decl)
    length = ""
    if length_match:
        length = clean_text(length_match.group(1))
    data_type = clean_text(re.sub(r"\([^)]*\)", "", type_decl))
    return data_type, length, rest[cut:]


def extract_ddl_fields(path):
    sql = read_text_with_fallback(path)
    table_comments = {}
    table_comment_matches = re.findall(
        r"\bCOMMENT\s+ON\s+TABLE\s+([`\"\[\]\w.\u4e00-\u9fff]+)\s+IS\s+(['\"])(.*?)\2",
        sql,
        re.IGNORECASE | re.DOTALL,
    )
    for name, quote, comment in table_comment_matches:
        table_comments[normalize_identifier(name)] = clean_text(comment)

    column_comments = {}
    column_comment_matches = re.findall(
        r"\bCOMMENT\s+ON\s+COLUMN\s+([`\"\[\]\w.\u4e00-\u9fff]+)\."
        r"([`\"\[\]\w\u4e00-\u9fff]+)\s+IS\s+(['\"])(.*?)\3",
        sql,
        re.IGNORECASE | re.DOTALL,
    )
    for table, column, quote, comment in column_comment_matches:
        key = (normalize_identifier(table), normalize_identifier(column))
        column_comments[key] = clean_text(comment)

    fields = []
    for table_name, body in find_create_table_blocks(sql):
        table_pk = set()
        column_defs = []
        for definition in split_sql_columns(body):
            if re.match(r"^\s*(?:CONSTRAINT\b.*?\b)?PRIMARY\s+KEY\b", definition, re.IGNORECASE):
                pk_match = re.search(r"\((.*?)\)", definition, re.DOTALL)
                if pk_match:
                    primary_key_columns = split_sql_columns(pk_match.group(1))
                    for item in primary_key_columns:
                        table_pk.add(normalize_identifier(item.strip()))
                continue
            if re.match(
                r"^\s*(?:CONSTRAINT|FOREIGN\s+KEY|UNIQUE|CHECK|KEY|INDEX)\b",
                definition,
                re.IGNORECASE,
            ):
                continue
            column_defs.append(definition)
        for ordinal, definition in enumerate(column_defs, start=1):
            match = re.match(
                r"^\s*(?P<name>`[^`]+`|\"[^\"]+\"|\[[^\]]+\]|[\w\u4e00-\u9fff]+)\s+"
                r"(?P<rest>.+)$",
                definition,
                re.DOTALL,
            )
            if not match:
                continue
            field_name = normalize_identifier(match.group("name"))
            rest = clean_text(match.group("rest"))
            data_type, length, constraints = parse_type_and_constraints(rest)
            if not data_type:
                continue
            default_match = re.search(
                r"\bDEFAULT\s+(.+?)(?=\s+(?:NOT\s+NULL|NULL|PRIMARY\s+KEY|UNIQUE|"
                r"REFERENCES|CHECK|COMMENT|COLLATE|GENERATED|CONSTRAINT)\b|$)",
                constraints,
                re.IGNORECASE,
            )
            comment = extract_inline_comment(constraints)
            comment = column_comments.get((table_name, field_name), comment)
            nullable = YES
            if re.search(r"\bNOT\s+NULL\b", constraints, re.IGNORECASE):
                nullable = NO
            primary_key = NO
            if field_name in table_pk or re.search(
                r"\bPRIMARY\s+KEY\b", constraints, re.IGNORECASE
            ):
                primary_key = YES
            default = ""
            if default_match:
                default = clean_text(default_match.group(1))
            fields.append(
                {
                    "table_name": table_name,
                    "table_comment": table_comments.get(table_name, ""),
                    "field_name": field_name,
                    "field_comment": comment,
                    "data_type": data_type,
                    "length": length,
                    "nullable": nullable,
                    "primary_key": primary_key,
                    "default": default,
                    "ordinal": ordinal,
                    "source_file": path.name,
                    "source_location": f"{path.name}:table:{table_name}",
                }
            )
    if not fields:
        raise PipelineError(f"No fields were detected in DDL file: {path}")
    return fields


def bool_text(value, truthy=None):
    normalized = compact(value)
    truthy = truthy or {"yes", "y", "true", "1", "是", "主键", "pk"}
    if not normalized:
        return ""
    return YES if normalized in truthy else NO


def extract_tabular_fields(path):
    raw_records = []
    if path.suffix.casefold() == ".csv":
        for table in load_csv_rows(path):
            raw_records.extend(records_from_rows(table, FIELD_ALIASES, {"field_name"}))
    elif path.suffix.casefold() in {".xlsx", ".xlsm"}:
        for table in load_excel_rows(path):
            raw_records.extend(records_from_rows(table, FIELD_ALIASES, {"field_name"}))
    else:
        for record in load_json_records(path):
            canonical = canonicalize_dict(record, FIELD_ALIASES)
            canonical["_location"] = f"{path.name}:json"
            raw_records.append(canonical)
    fields = []
    for ordinal, record in enumerate(raw_records, start=1):
        field_name = clean_text(record.get("field_name"))
        if not field_name:
            continue
        location = clean_text(record.get("_location"))
        sheet_match = re.search(r":sheet:([^:]+)", location)
        fallback_table = path.stem
        if sheet_match:
            fallback_table = sheet_match.group(1)
        fields.append(
            {
                "table_name": clean_text(record.get("table_name")) or fallback_table,
                "table_comment": clean_text(record.get("table_comment")),
                "field_name": field_name,
                "field_comment": clean_text(record.get("field_comment")),
                "data_type": clean_text(record.get("data_type")),
                "length": clean_text(record.get("length")),
                "nullable": bool_text(
                    record.get("nullable"),
                    {"yes", "y", "true", "1", "是", "允许", "可空", "null"},
                ),
                "primary_key": bool_text(record.get("primary_key")),
                "default": clean_text(record.get("default")),
                "ordinal": ordinal,
                "source_file": path.name,
                "source_location": location or path.name,
            }
        )
    if not fields:
        raise PipelineError(f"No recognized field-name column was found in: {path}")
    return fields


def extract_sqlite_fields(path):
    fields = []
    uri = f"file:{path.as_posix()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as connection:
        tables = connection.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
        for (table_name,) in tables:
            escaped = table_name.replace('"', '""')
            for column in connection.execute(f'PRAGMA table_info("{escaped}")').fetchall():
                ordinal, field_name, data_type, not_null, default, primary_key = column
                length_match = re.search(r"\(([^)]*)\)", data_type or "")
                length = ""
                if length_match:
                    length = clean_text(length_match.group(1))
                nullable = YES
                if not_null or primary_key:
                    nullable = NO
                primary_key_text = NO
                if primary_key:
                    primary_key_text = YES
                fields.append(
                    {
                        "table_name": table_name,
                        "table_comment": "",
                        "field_name": field_name,
                        "field_comment": "",
                        "data_type": clean_text(re.sub(r"\([^)]*\)", "", data_type or "")),
                        "length": length,
                        "nullable": nullable,
                        "primary_key": primary_key_text,
                        "default": clean_text(default),
                        "ordinal": ordinal + 1,
                        "source_file": path.name,
                        "source_location": f"{path.name}:table:{table_name}",
                    }
                )
    if not fields:
        raise PipelineError(f"The SQLite database has no visible business tables: {path}")
    return fields


def extract_database_fields(environment_name):
    url = os.environ.get(environment_name)
    if not url:
        raise PipelineError(f"Environment variable {environment_name} is not set")
    try:
        from sqlalchemy import create_engine, inspect
    except ImportError as exc:
        raise PipelineError(
            "Live database metadata extraction requires SQLAlchemy; install requirements.txt"
        ) from exc
    engine = create_engine(url)
    fields = []
    try:
        inspector = inspect(engine)
        schemas = [None]
        for schema in schemas:
            for table_name in inspector.get_table_names(schema=schema):
                primary_key_info = inspector.get_pk_constraint(table_name, schema=schema) or {}
                primary_key_columns = primary_key_info.get("constrained_columns") or []
                primary_keys = set(primary_key_columns)
                table_comment = clean_text(
                    (inspector.get_table_comment(table_name, schema=schema) or {}).get("text")
                )
                for ordinal, column in enumerate(
                    inspector.get_columns(table_name, schema=schema), start=1
                ):
                    type_text = clean_text(column.get("type"))
                    length_match = re.search(r"\(([^)]*)\)", type_text)
                    length = ""
                    if length_match:
                        length = clean_text(length_match.group(1))
                    full_table_name = table_name
                    if schema:
                        full_table_name = f"{schema}.{table_name}"
                    nullable = NO
                    if column.get("nullable"):
                        nullable = YES
                    primary_key = NO
                    if column.get("name") in primary_keys:
                        primary_key = YES
                    fields.append(
                        {
                            "table_name": full_table_name,
                            "table_comment": table_comment,
                            "field_name": clean_text(column.get("name")),
                            "field_comment": clean_text(column.get("comment")),
                            "data_type": clean_text(re.sub(r"\([^)]*\)", "", type_text)),
                            "length": length,
                            "nullable": nullable,
                            "primary_key": primary_key,
                            "default": clean_text(column.get("default")),
                            "ordinal": ordinal,
                            "source_file": f"env:{environment_name}",
                            "source_location": f"database:table:{table_name}",
                        }
                    )
    finally:
        engine.dispose()
    if not fields:
        raise PipelineError("No visible business tables were detected in the live database")
    return fields


def finalize_fields(records):
    result = []
    seen = {}
    for raw in records:
        record = dict(raw)
        base = f"{clean_text(record.get('table_name'))}.{clean_text(record.get('field_name'))}"
        base_key = base.casefold()
        seen[base_key] = seen.get(base_key, 0) + 1
        field_id = base
        if seen[base_key] > 1:
            field_id = f"{base}#{seen[base_key]}"
        record["field_id"] = field_id
        result.append(record)
    return result
