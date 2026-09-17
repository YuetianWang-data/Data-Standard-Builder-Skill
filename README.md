# Data Standard Builder

Data Standard Builder is a GitHub Copilot agent skill and Python pipeline for creating traceable business data standards from database metadata, normative documents, data-quality rule catalogs, and AI-assisted semantic decisions. It was completed in May 2026 and was recently uploaded to GitHub.

It separates deterministic processing from semantic judgment:

- **Python** extracts metadata, parses source files, retrieves candidates, validates references, and exports
  deliverables.
- **AI** reviews normative evidence, resolves ambiguous matches, decides whether user rules apply, and
  recommends standards for uncovered fields.

The pipeline does **not** present AI-generated recommendations as normative source text.

## Features

- Extract fields from SQL DDL, SQLite databases, live databases, CSV, Excel, and JSON.
- Extract data elements from PDF, CSV, Excel, and JSON standards.
- Preserve PDF page and worksheet evidence for traceability.
- Retrieve candidate normative standards using names, descriptions, types, formats, and context.
- Import generic user-rule files and detailed data-quality monitoring catalogs.
- Preserve monitoring context such as system, table, model, expected rule, problem description, and status.
- Support three output classes:
  - `Normative Standard`
  - `General Standard`
  - `Recommended Standard`
- Export Excel, CSV, JSONL, summaries, and validation reports.
- Reject unknown references, duplicate decisions, invalid confidence values, missing reasons, and uncovered
  fields in strict mode.

## Important distinction

Importing a data-quality rule does not execute that rule against production data.

This project builds and validates a **standard catalog**. The AI decides which imported rules apply to which
database fields, while the Python pipeline validates the resulting decision files. To execute checks against
actual records, integrate the exported rules with a data-quality engine, SQL job, or validation framework.

## Installation

### As a personal Copilot skill

Place the project at:

```text
%USERPROFILE%\.copilot\skills\data-standard-builder
```

On macOS or Linux:

```text
~/.copilot/skills/data-standard-builder
```

Install Python dependencies:

```powershell
$SKILL_DIR = Join-Path $HOME ".copilot\skills\data-standard-builder"
python -m pip install -r (Join-Path $SKILL_DIR "requirements.txt")
```

Python 3.10 or later is required.

### As a repository skill

Copy the directory to:

```text
.github/skills/data-standard-builder
```

## Quick start with Copilot

Attach a schema, one or more standard documents, and optionally a rule catalog. Then ask:

```text
Use data-standard-builder with:
- schema.sql as the database schema
- general-standard.pdf and legal-entity-standard.pdf as normative standards
- monitoring-rules.xlsx as the user-rule catalog

Build business-data-standards.xlsx. Apply only enabled monitoring rules and mark ambiguous
jurisdiction-specific or business-specific constraints for manual review.
```

Copilot runs the extraction pipeline, reviews candidates, writes decision files, and builds the deliverables.

## Command-line workflow

Set the pipeline path:

```powershell
$SKILL_DIR = Join-Path $HOME ".copilot\skills\data-standard-builder"
$PIPELINE = Join-Path $SKILL_DIR "scripts\data_standard_pipeline.py"
```

### 1. Prepare a workspace

```powershell
python $PIPELINE prepare `
  --schema "schema.sql" `
  --standard "general-standard.pdf" `
  --standard "legal-entity-standard.pdf" `
  --rules "monitoring-rules.xlsx" `
  --out-dir ".data-standard-work"
```

Use the bundled general-purpose rule catalog when no custom rule file is available:

```powershell
python $PIPELINE prepare `
  --schema "schema.sql" `
  --standard "standard.pdf" `
  --rules (Join-Path $SKILL_DIR "templates\user-rules.csv") `
  --out-dir ".data-standard-work"
```

### 2. Review extraction results

The workspace contains:

| File | Purpose |
|---|---|
| `fields.jsonl` | Extracted database fields |
| `standards_extracted.jsonl` | Deterministically extracted normative items |
| `standards.jsonl` | Combined extracted and AI-reviewed normative items |
| `match_candidates.jsonl` | Candidate normative matches for each field |
| `rules.jsonl` | Imported user and monitoring rules |
| `pdf_pages.jsonl` | PDF text with page provenance |
| `pdf_review_queue.jsonl` | Pages requiring AI, OCR, or manual review |
| `summary.json` | Extraction counts and workspace status |

If PDF review is necessary, add source-supported items to `ai_standard_items.jsonl` and refresh:

```powershell
python $PIPELINE refresh --workspace ".data-standard-work"
```

### 3. Create AI decision files

Write UTF-8 JSONL files under `.data-standard-work\decisions`.

`normative_mappings.jsonl`:

```json
{"field_id":"company.credit_code","standard_id":"STD-a1b2c3d4e5f6","confidence":0.97,"reason":"The names, definition, type, and format agree"}
```

`general_rules.jsonl`:

```json
{"rule_id":"G001","field_ids":["contract.start_date"],"business_rule":"Use YYYY-MM-DD format","confidence":0.99,"reason":"The field is a date and falls within the rule scope"}
```

`recommendations.jsonl`:

```json
{"field_ids":["person.mobile_phone"],"standard_name":"Mobile phone format validation","business_rule":"When present, the value must match the confirmed mobile-phone format","confidence":0.86,"reason":"No supplied standard or enabled user rule covers this quality dimension"}
```

### 4. Build deliverables

```powershell
python $PIPELINE build `
  --workspace ".data-standard-work" `
  --output "business-data-standards.xlsx"
```

The command creates:

- `business-data-standards.xlsx`
- `business-data-standards.csv`
- `business-data-standards.jsonl`
- `build_report.json`

## Supported inputs

### Database schemas

- SQL DDL
- SQLite `.db`, `.sqlite`, and `.sqlite3`
- CSV, Excel, or JSON field inventories
- SQLAlchemy-compatible live databases through an environment variable

Recommended field-inventory columns include `table_name`, `table_description`, `field_name`,
`field_description`, `data_type`, `length`, `nullable`, `primary_key`, `default`, and `description`.

### Normative standards

- PDF
- CSV
- Excel
- JSON

Recommended structured fields include `chinese_name` or another source-language name, `english_name`,
`standard_code`, `definition`, `data_type`, `data_format`, `value_domain`, and `unit`.

### User rules

Generic rule files support:

| Column | Purpose |
|---|---|
| `rule_id` | Stable rule identifier |
| `rule_name` | Short rule name |
| `rule_content` | Testable constraint |
| `scope` | Semantic population to which the rule may apply |
| `target` | Field metadata or naming signals |
| `severity` | `Required`, `Recommended`, or `Manual review` |
| `source` | Rule provenance |

Monitoring catalogs may also contain:

| Column | Purpose |
|---|---|
| `system_name` | Source system |
| `table_name` | Target table |
| `model_name` | Quality-assessment model |
| `problem_description` | Description of a failed check |
| `rule_status` | Enabled or disabled status |

Chinese equivalents such as `系统名称`, `表名称`, `模型名称`, `规则名称`, `规则描述`, `问题描述`,
and `规则状态` are recognized.

Disabled rules remain available for traceability but should not be mapped unless explicitly requested.

## Built-in rule catalog

`templates/user-rules.csv` contains 32 reusable candidate rules covering:

- completeness and mandatory fields
- uniqueness and business keys
- text normalization and declared lengths
- numeric precision, rates, percentages, and monetary values
- Boolean, email, phone, URL, IP, and JSON validity
- timestamp ordering and effective periods
- referential integrity and code-name consistency
- geographic coordinates and hierarchies
- sensitive-data protection and minimization

These are candidates, not unconditional rules. The AI evaluates their applicability using field names,
descriptions, data types, schema constraints, table context, and related fields.

## Architecture

```text
data-standard-builder/
|-- SKILL.md
|-- README.md
|-- requirements.txt
|-- templates/
|   `-- user-rules.csv
|-- scripts/
|   |-- data_standard_pipeline.py
|   `-- data_standard/
|       |-- cli.py
|       |-- common.py
|       |-- constants.py
|       |-- decisions.py
|       |-- exporters.py
|       |-- matching.py
|       |-- schema_extractors.py
|       |-- standard_extractors.py
|       |-- tabular.py
|       `-- workflow.py
```

`data_standard_pipeline.py` is a compatibility facade. The implementation is divided into focused modules.

## AI and Python responsibilities

| Responsibility | AI | Python |
|---|:---:|:---:|
| Interpret field semantics | Yes | No |
| Resolve ambiguous normative matches | Yes | No |
| Decide whether a user rule applies | Yes | No |
| Recommend uncovered standards | Yes | No |
| Extract deterministic metadata | No | Yes |
| Generate candidate matches | No | Yes |
| Validate IDs, confidence, and duplicates | No | Yes |
| Export Excel, CSV, and JSONL | No | Yes |
| Execute checks against business records | No | No |

## Security

- Put database credentials in environment variables only.
- The live-database importer reads metadata and does not query business records.
- Do not copy credentials into prompts, workspaces, logs, or generated catalogs.
- Review sensitive-data recommendations before adoption.

## Limitations

- Scanned PDFs require OCR before reliable extraction.
- Candidate similarity is retrieval support, not proof of a normative match.
- Business-specific code sets, update frequencies, composite uniqueness rules, legal identifiers, and
  jurisdiction-specific formats require source evidence or manual confirmation.
- Imported monitoring rules are cataloged and mapped; they are not executed against production data.
- A successful build validates catalog integrity, not the correctness of every AI semantic decision.
