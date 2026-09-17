---
name: data-standard-builder
description: >-
  Extract field inventories from database schemas, data catalogs, or field lists; analyze user-provided
  PDF/XLSX data-element standards; match normative standards; apply user-defined rules as general
  standards; and recommend justified standards for uncovered fields. Use for data-standard construction,
  field-to-standard matching, data-element extraction, data-quality rules, or business-standard catalogs.
user-invocable: true
---

# Data Standard Builder

Use the bundled Python pipeline to build traceable data standards. Python handles deterministic extraction,
candidate retrieval, validation, and Excel delivery. You analyze source materials, resolve ambiguity,
interpret rules, and create recommendations. Never present model inference as source-standard text.

## Skill directory

```powershell
$SKILL_DIR = Join-Path $HOME ".copilot\skills\data-standard-builder"
$PIPELINE = Join-Path $SKILL_DIR "scripts\data_standard_pipeline.py"
```

Install dependencies on first use or after a missing-package error:

```powershell
python -m pip install -r (Join-Path $SKILL_DIR "requirements.txt")
```

## Supported inputs

- Database structure: `.sql` DDL, SQLite `.db/.sqlite/.sqlite3`, or `.csv/.xlsx/.json` field lists
- Live database: use `--database-url-env` to name an environment variable containing a SQLAlchemy URL
- Standard documents: `.pdf/.csv/.xlsx/.json`
- Custom rules: `.txt/.md/.csv/.xlsx/.json`

Keep live-database credentials only in environment variables. Never write passwords to commands, logs,
workspace files, or deliverables. Read metadata only by default; do not read business records or sample values.

### Tabular field inventory

A CSV, Excel, or JSON field inventory must contain a recognized field-name column such as `field_name` or
`column_name`. Recommended columns are `table_name`, `table_description`, `field_name`, `field_description`,
`data_type`, `length`, `nullable`, `primary_key`, `default`, and `description`.

### Structured normative-standard inventory

In addition to PDFs, the pipeline accepts structured standards containing `chinese_name` or another
source-language name, `english_name`, `standard_code`, `definition`, `data_type`, `data_format`,
`value_domain`, and `unit`.

### User-rule format

Copy and edit `templates\user-rules.csv`. Each rule must express a testable constraint. For paired fields,
describe both semantic roles or naming patterns in `target`.

| Column | Purpose |
|---|---|
| `rule_id` | Stable identifier referenced by `general_rules.jsonl` |
| `rule_name` | Short rule name |
| `rule_content` | Testable constraint to adopt when applicable |
| `scope` | Semantic population to which the rule may apply |
| `target` | Field metadata or naming signals used by the AI as evidence |
| `severity` | `Required`, `Recommended`, or `Manual review` |
| `source` | Rule provenance |

The AI evaluates candidate rules against field metadata and business context; the pipeline does not apply
them mechanically. `Required` means mandatory when applicable, `Recommended` means normally appropriate when
applicable, and `Manual review` means the business scope, representation, jurisdiction, or security
classification must be confirmed before adoption.

The pipeline also recognizes monitoring catalogs with the columns `System Name`, `Table Name`, `Model Name`,
`Rule Name`, `Rule Description`, `Problem Description`, and `Rule Status`, including their Chinese header
equivalents. It preserves this context in `rules.jsonl`. Apply only enabled rules; retain disabled rules for
traceability but do not create `general_rules.jsonl` decisions from them unless the user explicitly requests it.

### Live-database metadata

Pass the name of an environment variable containing a SQLAlchemy URL. Non-SQLite databases also require their
database driver, such as `psycopg` for PostgreSQL or `pymysql` for MySQL. The pipeline uses SQLAlchemy Inspector
only to read table, column, primary-key, and comment metadata.

## Workflow

### 1. Confirm inputs

Locate the exact database structure, standard documents, rules, and output directory supplied by the user.
If an attachment is missing, say so explicitly. Do not substitute a similarly named online document or
invent content. If custom rules are absent, you may start with `templates\user-rules.csv`, but identify them
as template rules and require user confirmation.

### 2. Generate field, standard, and candidate inventories

Each input option is repeatable:

```powershell
python $PIPELINE prepare `
  --schema "schema.sql" `
  --schema "data-catalog.xlsx" `
  --standard "general-data-element-standard.pdf" `
  --standard "legal-entity-data-element-standard.pdf" `
  --rules "custom-rules.xlsx" `
  --out-dir ".data-standard-work"
```

Live-database example:

```powershell
$env:DATA_STANDARD_DB_URL = "postgresql+psycopg://user:password@host/db"
python $PIPELINE prepare `
  --database-url-env DATA_STANDARD_DB_URL `
  --standard "standard.pdf" `
  --rules "rules.csv" `
  --out-dir ".data-standard-work"
```

Read `summary.json` first. Inspect:

- `fields.jsonl`: database field inventory
- `standards.jsonl`: machine-extracted normative-standard inventory
- `match_candidates.jsonl`: normative candidates for each field
- `rules.jsonl`: user-rule inventory
- `pdf_review_queue.jsonl`: PDF pages that require review because extraction was unreliable
- `pdf_pages.jsonl`: PDF source text with page numbers

Never accept the highest string-similarity score as a normative match by itself. Evaluate local-language and
English names, definitions, types, formats, value domains, and context. Avoid matching homonyms with different
business meanings.

### 3. Complete PDF extraction

If `pdf_review_queue.jsonl` is not empty, review the corresponding entries in `pdf_pages.jsonl`. Write only
data elements explicitly supported by the source to `ai_standard_items.jsonl`, one JSON object per line:

```json
{"source_file":"standard.pdf","page":12,"evidence":"Short quotation from the source","chinese_name":"...","english_name":"unifiedSocialCreditCode","standard_code":"DE001","definition":"...","data_type":"character","data_format":"an18","value_domain":"..."}
```

Requirements:

- `source_file`, `page`, and `evidence` are required. Evidence must be quoted from that page.
- Populate only attributes explicitly stated in the source. Leave unknown values blank.
- For multi-page tables, inspect adjacent headers before merging rows.
- Do not duplicate an item already present in `standards_extracted.jsonl`.
- If a page has no extractable text, do not infer text from the image. Run OCR or leave it unresolved.

Refresh the standard inventory and candidates afterward:

```powershell
python $PIPELINE refresh --workspace ".data-standard-work"
```

### 4. Create three decision types

Write the following UTF-8 JSONL files under the workspace `decisions` directory. Do not modify extracted files.

`normative_mappings.jsonl` (Normative Standard):

```json
{"field_id":"person.credit_code","standard_id":"STD-a1b2c3d4e5f6","confidence":0.96,"reason":"The field name, definition, and an18 format agree"}
```

Rules:

- `field_id` must exist in `fields.jsonl`; `standard_id` must exist in `standards.jsonl`.
- Create a mapping only when the supplied standard document provides explicit support.
- `reason` must explain semantic and structural evidence, not merely say "high similarity."
- A field may map to multiple complementary standards, but mappings must not duplicate one another.

`general_rules.jsonl` (General Standard):

```json
{"rule_id":"G001","field_ids":["contract.start_date"],"business_rule":"Use YYYY-MM-DD format","confidence":0.99,"reason":"The date field is within the scope of user rule G001"}
{"rule_id":"G002","field_ids":["contract.start_date","contract.end_date"],"business_rule":"The start date must be before or equal to the end date","confidence":0.98,"reason":"A start/end date pair exists on the same business object"}
```

Rules:

- `rule_id` must exist in `rules.jsonl`; every ID in `field_ids` must exist in `fields.jsonl`.
- Understand scope, conditions, field pairs, and exceptions before applying a rule. Do not apply date rules
  mechanically to character-code fields.
- `business_rule` must be actionable and testable while preserving the user's intent.
- The AI is responsible for deciding whether a template rule applies. It must evaluate field names,
  descriptions, data types, constraints, table context, and related fields against the rule's `scope` and
  `target`; the Python pipeline does not apply template rules automatically.
- Treat `severity` as the strength of an applicable rule, not as permission to apply it to every field.
- For ambiguous ranges, jurisdiction-specific formats, sensitive-data classifications, or inferred business
  keys, set `manual_confirmation` and explain what must be confirmed.
- Python validates references, confidence values, duplicates, and coverage. It does not certify that the AI's
  semantic applicability decision is correct.

`recommendations.jsonl` (Recommended Standard):

```json
{"field_ids":["person.mobile_phone"],"standard_name":"Mobile phone format validation","business_rule":"When present, the value must match the confirmed mobile-phone format","confidence":0.86,"reason":"No supplied standard or user rule covers this field; format validation reduces unusable contact data"}
```

Rules:

- Recommend only after identifying fields or quality dimensions not covered by normative or general standards.
- `reason` must explain both the coverage gap and the business or quality benefit.
- Never claim that a recommendation came from a user-supplied standard.
- Prefer testable completeness, uniqueness, consistency, timeliness, validity, and referential-integrity rules.
- For identity, privacy, industry-code, or legal constraints without source support, mark the recommendation
  for manual review instead of inventing a value domain.

### 5. Build deliverables in strict mode

```powershell
python $PIPELINE build `
  --workspace ".data-standard-work" `
  --output "business-data-standards.xlsx"
```

Strict mode rejects missing field/standard/rule references, invalid confidence values, missing recommendation
reasons, duplicate decisions, empty outputs, and completely uncovered fields. Fix decisions and rebuild.
Use `--allow-incomplete` only when the user explicitly requests a draft.

Deliverables:

- The requested Excel workbook
- A same-name `.csv` file
- A same-name `.jsonl` file

The three standard-type labels are `Normative Standard`, `General Standard`, and `Recommended Standard`.

### 6. Final review

Inspect `build_report.json` and confirm:

- Field, normative-element, and decision-type counts are reasonable.
- `uncovered_field_count` is zero, or draft output explicitly lists uncovered fields.
- Every normative standard has a source and page/worksheet location.
- Every general standard traces to a user rule.
- Every recommended standard has a reason and no fabricated normative source.

Report the output path, counts by standard type, manual-review items, and unresolved source material. Do not
claim sample-specific compatibility unless the actual sample files were read and processed successfully.
