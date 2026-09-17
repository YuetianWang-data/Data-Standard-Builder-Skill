# Validates AI decisions and converts them into normalized business-standard rows.

from .common import PipelineError, clean_text, compact
from .constants import (
    GENERATED_STATUS,
    GENERAL_STANDARD,
    MANUAL_REVIEW_STATUS,
    NORMATIVE_STANDARD,
    RECOMMENDED_STANDARD,
)


def parse_confidence(value, location):
    try:
        confidence = float(value)
    except (TypeError, ValueError) as exc:
        raise PipelineError(f"{location} confidence must be a number from 0 to 1") from exc
    if not 0 <= confidence <= 1:
        raise PipelineError(f"{location} confidence is outside the 0-to-1 range")
    return confidence


def require_ids(values, valid_ids, location):
    if not isinstance(values, list) or not values:
        raise PipelineError(f"{location} field_ids must be a non-empty array")
    result = []
    missing = []
    for value in values:
        field_id = clean_text(value)
        result.append(field_id)
        if field_id not in valid_ids:
            missing.append(field_id)
    if missing:
        raise PipelineError(f"{location} references unknown fields: {', '.join(missing)}")
    if len(result) != len(set(result)):
        raise PipelineError(f"{location} field_ids contains duplicates")
    return result


def normative_rule_text(standard):
    clauses = []
    definition = clean_text(standard.get("definition"))
    data_type = clean_text(standard.get("data_type"))
    data_format = clean_text(standard.get("data_format"))
    value_domain = clean_text(standard.get("value_domain"))
    if definition:
        clauses.append(f"Definition: {definition}")
    if data_type:
        clauses.append(f"Data type: {data_type}")
    if data_format:
        clauses.append(f"Data format: {data_format}")
    if value_domain:
        clauses.append(f"Value domain: {value_domain}")
    if clauses:
        return "; ".join(clauses)
    name = clean_text(standard.get("chinese_name"))
    return f"Follow the definition of data element '{name}'"


def index_by_id(records, key):
    result = {}
    for record in records:
        record_id = clean_text(record.get(key))
        result[record_id] = record
    return result


def validate_and_build_rows(fields, standards, rules, normative, general, recommendations):
    fields_by_id = index_by_id(fields, "field_id")
    standards_by_id = index_by_id(standards, "standard_id")
    rules_by_id = index_by_id(rules, "rule_id")
    field_ids = set(fields_by_id)
    covered = set()
    rows = []
    issues = []
    decision_keys = set()

    for index, decision in enumerate(normative, start=1):
        location = f"normative_mappings.jsonl item {index}"
        field_id = clean_text(decision.get("field_id"))
        standard_id = clean_text(decision.get("standard_id"))
        if field_id not in fields_by_id:
            raise PipelineError(f"{location} references an unknown field: {field_id}")
        if standard_id not in standards_by_id:
            raise PipelineError(f"{location} references an unknown standard: {standard_id}")
        reason = clean_text(decision.get("reason"))
        if not reason:
            raise PipelineError(f"{location} is missing reason")
        key = ("normative", field_id, standard_id)
        if key in decision_keys:
            raise PipelineError(f"{location} duplicates an earlier decision")
        decision_keys.add(key)
        confidence = parse_confidence(decision.get("confidence"), location)
        field = fields_by_id[field_id]
        standard = standards_by_id[standard_id]
        covered.add(field_id)
        rows.append(
            make_business_row(
                field_ids=[field_id],
                fields_by_id=fields_by_id,
                standard_type=NORMATIVE_STANDARD,
                source=clean_text(standard.get("source_file")),
                source_location=clean_text(standard.get("source_location")),
                standard_code=clean_text(standard.get("standard_code")),
                standard_name=clean_text(standard.get("chinese_name"))
                or clean_text(standard.get("english_name")),
                business_rule=clean_text(decision.get("business_rule"))
                or normative_rule_text(standard),
                data_type=clean_text(standard.get("data_type")) or clean_text(field.get("data_type")),
                data_format=clean_text(standard.get("data_format")),
                value_domain=clean_text(standard.get("value_domain")),
                confidence=confidence,
                reason=reason,
                manual_confirmation=clean_text(decision.get("manual_confirmation")),
            )
        )

    for index, decision in enumerate(general, start=1):
        location = f"general_rules.jsonl item {index}"
        rule_id = clean_text(decision.get("rule_id"))
        if rule_id not in rules_by_id:
            raise PipelineError(f"{location} references an unknown rule: {rule_id}")
        selected_ids = require_ids(decision.get("field_ids"), field_ids, location)
        reason = clean_text(decision.get("reason"))
        business_rule = clean_text(decision.get("business_rule"))
        if not reason or not business_rule:
            raise PipelineError(f"{location} is missing reason or business_rule")
        key = ("general", rule_id, tuple(selected_ids), compact(business_rule))
        if key in decision_keys:
            raise PipelineError(f"{location} duplicates an earlier decision")
        decision_keys.add(key)
        confidence = parse_confidence(decision.get("confidence"), location)
        rule = rules_by_id[rule_id]
        covered.update(selected_ids)
        rows.append(
            make_business_row(
                field_ids=selected_ids,
                fields_by_id=fields_by_id,
                standard_type=GENERAL_STANDARD,
                source=clean_text(rule.get("source")),
                source_location=clean_text(rule.get("source_location")),
                standard_code=rule_id,
                standard_name=clean_text(rule.get("rule_name")),
                business_rule=business_rule,
                data_type="",
                data_format="",
                value_domain="",
                confidence=confidence,
                reason=reason,
                manual_confirmation=clean_text(decision.get("manual_confirmation")),
            )
        )

    for index, decision in enumerate(recommendations, start=1):
        location = f"recommendations.jsonl item {index}"
        selected_ids = require_ids(decision.get("field_ids"), field_ids, location)
        standard_name = clean_text(decision.get("standard_name"))
        business_rule = clean_text(decision.get("business_rule"))
        reason = clean_text(decision.get("reason"))
        if not standard_name or not business_rule or not reason:
            raise PipelineError(
                f"{location} is missing standard_name, business_rule, or reason"
            )
        key = ("recommended", tuple(selected_ids), compact(standard_name), compact(business_rule))
        if key in decision_keys:
            raise PipelineError(f"{location} duplicates an earlier decision")
        decision_keys.add(key)
        confidence = parse_confidence(decision.get("confidence"), location)
        already_covered = []
        for field_id in selected_ids:
            if field_id in covered:
                already_covered.append(field_id)
        if already_covered:
            issues.append(
                f"{location} includes fields already covered by normative or general standards: "
                f"{', '.join(already_covered)}. Confirm that this adds a quality dimension "
                "rather than duplicating an existing rule"
            )
        covered.update(selected_ids)
        rows.append(
            make_business_row(
                field_ids=selected_ids,
                fields_by_id=fields_by_id,
                standard_type=RECOMMENDED_STANDARD,
                source="AI recommendation (not normative source text)",
                source_location="",
                standard_code="",
                standard_name=standard_name,
                business_rule=business_rule,
                data_type=clean_text(decision.get("data_type")),
                data_format=clean_text(decision.get("data_format")),
                value_domain=clean_text(decision.get("value_domain")),
                confidence=confidence,
                reason=reason,
                manual_confirmation=clean_text(decision.get("manual_confirmation")),
            )
        )

    for index, row in enumerate(rows, start=1):
        row["business_standard_id"] = f"BS-{index:06d}"
    uncovered = sorted(field_ids - covered)
    return rows, uncovered, issues


def make_business_row(
    field_ids,
    fields_by_id,
    standard_type,
    source,
    source_location,
    standard_code,
    standard_name,
    business_rule,
    data_type,
    data_format,
    value_domain,
    confidence,
    reason,
    manual_confirmation,
):
    selected = []
    for field_id in field_ids:
        selected.append(fields_by_id[field_id])
    if manual_confirmation:
        status = manual_confirmation
    elif confidence < 0.8:
        status = MANUAL_REVIEW_STATUS
    else:
        status = GENERATED_STATUS
    return {
        "business_standard_id": "",
        "field_ids": " | ".join(field_ids),
        "table_names": join_field_values(selected, "table_name"),
        "field_names": join_field_values(selected, "field_name"),
        "field_chinese_names": join_field_values(selected, "field_comment", skip_empty=True),
        "standard_type": standard_type,
        "standard_code": standard_code,
        "standard_name": standard_name,
        "business_rule": business_rule,
        "data_type": data_type,
        "data_format": data_format,
        "value_domain": value_domain,
        "source": source,
        "source_location": source_location,
        "confidence": confidence,
        "reason": reason,
        "status": status,
    }


def join_field_values(fields, key, skip_empty=False):
    values = []
    for field in fields:
        value = clean_text(field.get(key))
        if skip_empty and not value:
            continue
        if value not in values:
            values.append(value)
    return " | ".join(values)
