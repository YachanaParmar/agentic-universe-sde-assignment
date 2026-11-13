# Assignment A — Interaction Ledger & Reporting Pipeline

## Overview

A Python and SQLite pipeline that ingests lead CSVs and call-event JSONL files, normalizes input data, maintains a persistent interaction ledger, and generates reporting outputs for two workflows: `motor_renewal` and `policy_feedback`.

## Architecture

- `normalization.py` — Header, phone, date, decimal, and enum normalization.
- `database.py` — SQLite schema and database connection.
- `ingestion.py` — Lead ingestion, validation, merging, and event ingestion.
- `event_quality.py` — Orphan-event and unknown-disposition analysis.
- `reporting.py` — Batch, daily, lead-level, rejection, and data-quality reports.

SQLite stores leads, ingested source rows, rejected rows, events, event-line processing records, field warnings, and duplicate-lead records.

Phone numbers are identified using HMAC-SHA256. The database stores the phone hash and last four digits rather than the complete phone number.

## Setup and execution

Run from the repository root.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Set a local HMAC key:

```powershell
$env:LEDGER_HMAC_KEY = .\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_hex(32))"
```

Generate sample data:

```powershell
.\.venv\Scripts\python.exe assignment-a-data\tools\generate_data.py --seed 42 --scale small --out data
```

Ingest both drops:

```powershell
.\.venv\Scripts\python.exe -c "from solution.database import connect; from solution.ingestion import ingest_leads,ingest_events; c=connect(); [(ingest_leads(c,d),ingest_events(c,d)) for d in ['data/drop_1','data/drop_2']]; c.close()"
```

Generate reports:

```powershell
.\.venv\Scripts\python.exe -m solution.reporting
```

Run tests:

```powershell
.\.venv\Scripts\python.exe -m pytest tests -v
```

## Generated reports

The `output/` directory contains:

- `batch_summary.csv`
- `daily_overview.csv`
- `lead_report.csv`
- `rejections.csv`
- `data_quality.json`

## Processing behavior

- Lead rows are validated using workflow-specific JSON schemas.
- Invalid required fields cause rejection.
- Invalid optional fields produce warnings.
- Leads are deduplicated by workflow and normalized phone identity.
- Re-ingestion skips previously processed source rows and event lines.
- Events are stored independently of lead arrival order.
- Reports reconstruct call state and effective dispositions from the stored events.
- Reporting dates are interpreted in Indian Standard Time.

## Limitations

The implementation has been validated with generated data and normalization tests. Additional automated integration tests for late-arriving events, disposition overrides, crash recovery, and report correctness would improve confidence.