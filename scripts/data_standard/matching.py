# Scores semantic and structural similarity between fields and normative standards.

from difflib import SequenceMatcher

from .common import compact


def type_family(value):
    normalized = compact(value)
    families = {
        "date": ("date", "time", "日期", "时间", "timestamp"),
        "number": ("int", "decimal", "numeric", "number", "float", "double", "金额", "数值", "数字"),
        "boolean": ("bool", "boolean", "布尔"),
        "binary": ("blob", "binary", "byte", "二进制"),
        "text": ("char", "text", "string", "varchar", "字符", "文本", "字符串"),
    }
    for family, markers in families.items():
        if any(compact(marker) in normalized for marker in markers):
            return family
    return ""


def similarity(left, right):
    clean_left = compact(left)
    clean_right = compact(right)
    if not clean_left or not clean_right:
        return 0.0
    if clean_left == clean_right:
        return 1.0
    ratio = SequenceMatcher(None, clean_left, clean_right).ratio()
    if clean_left in clean_right or clean_right in clean_left:
        shorter_length = min(len(clean_left), len(clean_right))
        longer_length = max(len(clean_left), len(clean_right))
        contained_ratio = shorter_length / longer_length * 0.92
        ratio = max(ratio, contained_ratio)
    return ratio


def score_value(item):
    return item[1]


def candidate_score(field, standard):
    comparisons = [
        ("English field name", field.get("field_name"), standard.get("english_name")),
        ("Field description", field.get("field_comment"), standard.get("chinese_name")),
        (
            "Table and field semantics",
            f"{field.get('table_comment', '')}{field.get('field_comment', '')}",
            standard.get("definition"),
        ),
        ("Field name and source-language standard name", field.get("field_name"), standard.get("chinese_name")),
    ]
    scored = []
    for label, left, right in comparisons:
        scored.append((label, similarity(left, right)))
    scored.sort(key=score_value, reverse=True)
    name_score = scored[0][1]
    semantic_score = scored[1][1] if len(scored) > 1 else 0.0
    score = name_score * 0.78 + semantic_score * 0.17
    reasons = []
    for label, value in scored[:2]:
        if value > 0:
            reasons.append(f"{label}:{value:.2f}")
    field_type = type_family(field.get("data_type"))
    standard_type = type_family(standard.get("data_type"))
    if field_type and standard_type:
        if field_type == standard_type:
            score += 0.05
            reasons.append("Compatible types")
        else:
            score -= 0.08
            reasons.append("Possible type conflict")
    return max(0.0, min(1.0, score)), reasons


def candidate_sort_value(item):
    return item["score"]


def build_candidates(fields, standards, top_k):
    candidates = []
    for field in fields:
        scored = []
        for standard in standards:
            score, signals = candidate_score(field, standard)
            if score < 0.18:
                continue
            scored.append(
                {
                    "standard_id": standard.get("standard_id"),
                    "score": round(score, 4),
                    "signals": signals,
                    "standard_code": standard.get("standard_code"),
                    "chinese_name": standard.get("chinese_name"),
                    "english_name": standard.get("english_name"),
                    "definition": standard.get("definition"),
                    "data_type": standard.get("data_type"),
                    "data_format": standard.get("data_format"),
                    "value_domain": standard.get("value_domain"),
                    "source_file": standard.get("source_file"),
                    "page": standard.get("page"),
                }
            )
        scored.sort(key=candidate_sort_value, reverse=True)
        candidates.append(
            {
                "field_id": field.get("field_id"),
                "table_name": field.get("table_name"),
                "field_name": field.get("field_name"),
                "field_comment": field.get("field_comment"),
                "data_type": field.get("data_type"),
                "candidates": scored[:top_k],
            }
        )
    return candidates
