# Submission

## Candidate

- Name: Yachana
- Assignment chosen: A — Interaction Ledger & Reporting Pipeline
- Time spent (honest estimate): Approximately 7 hours 

## How to run

Complete setup and execution instructions are available in `solution/README.md`.

From a clean clone, create a Python 3.11+ virtual environment, install dependencies, configure the HMAC key, generate the sample data, ingest both drops, generate reports, and run the tests.

The implementation uses Python and SQLite. No external database server is required.

## Design

The solution is organized into five components:

1. Normalization (`normalization.py`): Normalizes headers, Indian phone numbers, dates, decimals, and enum values.
2. Lead ingestion (`ingestion.py`): Validates CSV rows against workflow schemas, records rejections and warnings, and merges duplicate leads.
3. Event ingestion (`ingestion.py`): Ingests JSONL events, deduplicates using event IDs, and maintains event history.
4. Event quality (`event_quality.py`): Evaluates orphan events and unknown disposition codes.
5. Reporting (`reporting.py`): Reconstructs call and lead states to generate the five required output files.

### Database design

SQLite stores the following tables:

| Table | Purpose |
|---|---|
| `leads` | Unique lead records by workflow and phone identity |
| `lead_rows` | Tracks processed source rows |
| `rejections` | Stores rejected lead rows and reasons |
| `events` | Stores unique call and disposition events |
| `event_lines` | Tracks processed JSONL lines |
| `field_warnings` | Tracks invalid optional fields |
| `duplicate_leads` | Records duplicate lead merges |

Phone identities use HMAC-SHA256 rather than storing complete phone numbers.

## Decisions & assumptions

| Decision | Why | Alternative considered |
|---|---|---|
| SQLite | Lightweight, persistent, and easy to run locally | PostgreSQL |
| HMAC-SHA256 phone identity | Supports deterministic matching without retaining full phone numbers | Plaintext phone storage |
| Workflow and normalized phone as lead identity | Supports deduplication within each workflow | Reference-based matching |
| Append-only event history | Supports reconstructing interaction state | Latest-state-only storage |
| IST reporting dates | Follows the assignment's reporting timezone | UTC-only reporting |
| Source-row tracking | Supports safe re-ingestion | Reprocessing every row |
| Report-time event reconciliation | Allows events to be evaluated after leads have arrived | Rejecting unmatched events immediately |

## Failure modes considered

The implementation handles invalid required fields, invalid optional values, malformed JSON, duplicate event IDs, duplicate leads, and repeated ingestion of the same source files.

Known limitations include incomplete automated integration coverage for late-arriving events, supervisor overrides, crash recovery, and independent verification of all report calculations.

## Testing

- **11 normalization tests passed.**
- All five reports generated successfully.
- Batch totals matched the number of unique leads.
- All batch bucket totals reconciled.
- Connected-call counts did not exceed total-call counts.
- Duplicate-lead statistics reconciled with accepted and unique lead counts.
- Re-ingestion preserved the original lead and event counts.

Automated end-to-end tests for supervisor overrides, late-arriving events, crash recovery, and exact report correctness have not yet been completed.

## Results

Generated sample data using seed 42 at the small scale.

| Metric | Result |
|---|---:|
| Total lead rows | 2,057 |
| Rejected lead rows | 108 |
| Unique leads | 1,892 |
| Duplicate lead rows merged | 57 |
| Event lines processed | 8,745 |
| Unique events stored | 8,500 |
| Malformed events | 8 |
| Duplicate events dropped | 237 |
| Orphan events | 462 |
| Unknown disposition events | 18 |

**Execution time:** Not benchmarked separately. Pipeline execution and report generation completed successfully on the small dataset.

## If I had another day

I would prioritize end-to-end tests for out-of-order events, disposition overrides, and exact report correctness, followed by improved crash-recovery testing and more detailed data-quality diagnostics.