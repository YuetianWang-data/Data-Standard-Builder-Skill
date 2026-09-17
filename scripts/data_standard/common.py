# Provides shared errors, text normalization, identifiers, and JSON file utilities.

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path


class PipelineError(RuntimeError):
    """A user-correctable pipeline failure."""


class TableRows:
    def __init__(self, rows, location):
        self.rows = rows
        self.location = location


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def clean_text(value):
    if value is None:
        return ""
    text = str(value).replace("\u3000", " ").replace("\xa0", " ")
    return re.sub(r"\s+", " ", text).strip()


def compact(value):
    text = clean_text(value).casefold()
    return re.sub(r"[\s_\-—–·•,，.。:：;；/\\|()（）\[\]【】<>《》]+", "", text)


def normalize_identifier(value):
    return value.strip().strip('`"[]')


def stable_id(prefix, *parts):
    clean_parts = []
    for part in parts:
        clean_parts.append(clean_text(part))
    payload = "\x1f".join(clean_parts)
    digest = hashlib.sha1(payload.encode("utf-8")).hexdigest()
    return f"{prefix}-{digest[:12]}"


def read_jsonl(path, required=True):
    if not path.exists():
        if required:
            raise PipelineError(f"Missing file: {path}")
        return []
    records = []
    with path.open("r", encoding="utf-8-sig") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise PipelineError(f"{path}:{line_number} is not valid JSON: {exc}") from exc
            if not isinstance(value, dict):
                raise PipelineError(f"{path}:{line_number} must contain a JSON object")
            records.append(value)
    return records


def write_jsonl(path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(dict(record), ensure_ascii=False, sort_keys=False) + "\n")


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def read_text_with_fallback(path):
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    raise PipelineError(f"Unable to detect text encoding: {path}")


def expand_inputs(values, allowed_suffixes, label):
    paths = []
    for raw in values:
        path = Path(raw).expanduser().resolve()
        if not path.exists():
            raise PipelineError(f"{label} does not exist: {path}")
        candidates = [path]
        if path.is_dir():
            candidates = []
            for item in path.rglob("*"):
                if item.is_file():
                    candidates.append(item)
            candidates.sort()
        for candidate in candidates:
            if candidate.suffix.casefold() in allowed_suffixes:
                paths.append(candidate)
    unique = []
    for path in paths:
        if path not in unique:
            unique.append(path)
    if values and not unique:
        supported = ", ".join(sorted(allowed_suffixes))
        raise PipelineError(f"No supported files found in {label} ({supported})")
    return unique
