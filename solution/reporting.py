
import csv
import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from solution.database import connect
from solution.event_quality import calculate_event_quality


IST = timezone(timedelta(hours=5, minutes=30))

REPORT_COLUMNS = {
    "batch_summary.csv": [
        "workflow_id",
        "batch_id",
        "total_leads",
        "yet_to_reach_out",
        "in_progress_telephony_failed",
        "in_progress_dialed",
        "completed",
    ],
    "daily_overview.csv": [
        "workflow_id",
        "date",
        "total_calls",
        "connected_calls",
        "connectivity_rate",
        "success_leads",
    ],
    "lead_report.csv": [
        "workflow_id",
        "external_ref",
        "batch_id",
        "phone_masked",
        "bucket",
        "total_calls",
        "connected_calls",
        "last_call_at",
        "current_disposition",
        "ever_success",
    ],
    "rejections.csv": [
        "workflow_id",
        "batch_id",
        "row_number",
        "reason",
    ],
}


def parse_timestamp(value):
    if not value:
        return None

    try:
        dt = datetime.fromisoformat(
            str(value).replace("Z", "+00:00")
        )

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=IST)

        return dt.astimezone(IST)

    except (ValueError, TypeError):
        return None


def load_dispositions():
    result = {}

    path = Path(
        "assignment-a-data/schemas/dispositions.csv"
    )

    with path.open(
        encoding="utf-8-sig",
        newline="",
    ) as file:
        for row in csv.DictReader(file):
            result[
                (row["workflow_id"], row["code"])
            ] = {
                "terminal": (
                    row["is_terminal"].lower() == "true"
                ),
                "success": (
                    row["is_success"].lower() == "true"
                ),
            }

    return result


def write_csv(path, columns, rows):
    with Path(path).open(
        "w",
        encoding="utf-8",
        newline="",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=columns,
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(rows)


def generate_reports(
    db_path="solution/ledger.db",
    output_dir="output",
):
    output_dir = Path(output_dir)
    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    conn = connect(db_path)

    try:
        dispositions = load_dispositions()

        leads = [
            dict(row)
            for row in conn.execute(
                "SELECT * FROM leads"
            )
        ]

        events = [
            dict(row)
            for row in conn.execute(
                "SELECT * FROM events"
            )
        ]

        lead_lookup = {
            (
                lead["workflow_id"],
                lead["phone_hash"],
            ): lead
            for lead in leads
        }

        # Group events by workflow and call ID.
        calls = defaultdict(
            lambda: {
                "lead": None,
                "initiated": [],
                "connected": False,
                "failed": False,
                "dispositions": [],
                "effective_code": None,
            }
        )

        for event in events:
            workflow = event["workflow_id"]
            call_id = event["call_id"]

            if not workflow or not call_id:
                continue

            key = (workflow, call_id)
            call = calls[key]

            event_type = event["event_type"]
            timestamp = parse_timestamp(
                event["occurred_at"]
            )

            # Only an initiated event establishes
            # the lead identity for a call.
            if (
                event_type == "call.initiated"
                and event["phone_hash"]
            ):
                lead = lead_lookup.get(
                    (
                        workflow,
                        event["phone_hash"],
                    )
                )

                if lead is not None:
                    call["lead"] = lead

            if event_type == "call.initiated":
                if timestamp is not None:
                    call["initiated"].append(
                        timestamp
                    )

            elif event_type == "call.connected":
                call["connected"] = True

            elif event_type == "call.telephony_failed":
                call["failed"] = True

            elif event_type in (
                "disposition.set",
                "disposition.override",
            ):
                try:
                    payload = json.loads(
                        event["payload_json"]
                    )
                except (ValueError, TypeError):
                    payload = {}

                if not isinstance(payload, dict):
                    payload = {}

                code = payload.get(
                    "disposition_code"
                )

                # Unknown codes do not affect
                # the effective disposition.
                if (
                    workflow,
                    code,
                ) not in dispositions:
                    continue

                call["dispositions"].append(
                    (
                        timestamp,
                        event_type
                        == "disposition.override",
                        event["event_id"],
                        code,
                    )
                )

        # Resolve the effective disposition.
        # Latest override wins when present;
        # otherwise latest disposition.set wins.
        minimum_time = datetime.min.replace(
            tzinfo=IST
        )

        for call in calls.values():
            records = call["dispositions"]

            overrides = [
                record
                for record in records
                if record[1]
            ]

            candidates = (
                overrides if overrides else records
            )

            if candidates:
                latest = max(
                    candidates,
                    key=lambda record: (
                        record[0] or minimum_time,
                        record[2],
                    ),
                )
                call["effective_code"] = latest[3]

        # Only count calls linked to valid leads
        # and containing an initiated event.
        calls_by_lead = defaultdict(list)

        for call in calls.values():
            lead = call["lead"]

            if (
                lead is not None
                and call["initiated"]
            ):
                calls_by_lead[
                    lead["id"]
                ].append(call)

        batch_counts = defaultdict(
            lambda: defaultdict(int)
        )

        daily_counts = defaultdict(
            lambda: {
                "total_calls": 0,
                "connected_calls": 0,
                "success_leads": set(),
            }
        )

        lead_rows = []

        for lead in leads:
            workflow = lead["workflow_id"]

            lead_calls = calls_by_lead.get(
                lead["id"],
                [],
            )

            completed = False
            ever_success = False

            for call in lead_calls:
                code = call["effective_code"]

                info = dispositions.get(
                    (workflow, code),
                    {},
                )

                if info.get("terminal", False):
                    completed = True

                if info.get("success", False):
                    ever_success = True

                initiated_at = min(
                    call["initiated"]
                )

                day = initiated_at.date().isoformat()

                daily = daily_counts[
                    (workflow, day)
                ]

                daily["total_calls"] += 1

                if call["connected"]:
                    daily["connected_calls"] += 1

                if info.get("success", False):
                    daily[
                        "success_leads"
                    ].add(lead["id"])

            if not lead_calls:
                bucket = "yet_to_reach_out"

            elif completed:
                bucket = "completed"

            elif all(
                call["failed"]
                for call in lead_calls
            ):
                bucket = (
                    "in_progress_telephony_failed"
                )

            else:
                bucket = "in_progress_dialed"

            batch_counts[
                (
                    workflow,
                    lead["batch_id"],
                )
            ][bucket] += 1

            last_call_at = ""
            current_disposition = ""

            if lead_calls:
                latest_call = max(
                    lead_calls,
                    key=lambda call: max(
                        call["initiated"]
                    ),
                )

                latest_time = max(
                    latest_call["initiated"]
                )

                last_call_at = (
                    latest_time.isoformat()
                )

                current_disposition = (
                    latest_call["effective_code"]
                    or ""
                )

            lead_rows.append(
                {
                    "workflow_id": workflow,
                    "external_ref": (
                        lead["external_ref"]
                    ),
                    "batch_id": lead["batch_id"],
                    "phone_masked": (
                        "+91******"
                        + lead["phone_last4"]
                    ),
                    "bucket": bucket,
                    "total_calls": len(lead_calls),
                    "connected_calls": sum(
                        1
                        for call in lead_calls
                        if call["connected"]
                    ),
                    "last_call_at": last_call_at,
                    "current_disposition": (
                        current_disposition
                    ),
                    "ever_success": str(
                        ever_success
                    ).lower(),
                }
            )

        batch_summary = []

        for (
            workflow,
            batch_id,
        ), counts in sorted(
            batch_counts.items()
        ):
            batch_summary.append(
                {
                    "workflow_id": workflow,
                    "batch_id": batch_id,
                    "total_leads": sum(
                        counts.values()
                    ),
                    "yet_to_reach_out": counts[
                        "yet_to_reach_out"
                    ],
                    "in_progress_telephony_failed":
                        counts[
                            "in_progress_telephony_failed"
                        ],
                    "in_progress_dialed": counts[
                        "in_progress_dialed"
                    ],
                    "completed": counts[
                        "completed"
                    ],
                }
            )

        daily_overview = []

        for (
            workflow,
            day,
        ), counts in sorted(
            daily_counts.items()
        ):
            total = counts["total_calls"]
            connected = counts["connected_calls"]

            rate = (
                connected / total
                if total
                else 0
            )

            daily_overview.append(
                {
                    "workflow_id": workflow,
                    "date": day,
                    "total_calls": total,
                    "connected_calls": connected,
                    "connectivity_rate": (
                        f"{rate:.4f}"
                    ),
                    "success_leads": len(
                        counts["success_leads"]
                    ),
                }
            )

        rejections = [
            dict(row)
            for row in conn.execute(
                """
                SELECT
                    workflow_id,
                    batch_id,
                    row_number,
                    reason
                FROM rejections
                ORDER BY
                    workflow_id,
                    batch_id,
                    row_number
                """
            )
        ]

        # Write CSV reports.
        write_csv(
            output_dir / "batch_summary.csv",
            REPORT_COLUMNS["batch_summary.csv"],
            batch_summary,
        )

        write_csv(
            output_dir / "daily_overview.csv",
            REPORT_COLUMNS["daily_overview.csv"],
            daily_overview,
        )

        write_csv(
            output_dir / "lead_report.csv",
            REPORT_COLUMNS["lead_report.csv"],
            sorted(
                lead_rows,
                key=lambda row: (
                    row["workflow_id"],
                    row["external_ref"],
                ),
            ),
        )

        write_csv(
            output_dir / "rejections.csv",
            REPORT_COLUMNS["rejections.csv"],
            rejections,
        )

        # Calculate event quality once.
        event_quality = calculate_event_quality(
            conn
        )

        rejection_counts = {
            row[0]: row[1]
            for row in conn.execute(
                """
                SELECT reason, COUNT(*)
                FROM rejections
                GROUP BY reason
                """
            )
        }

        quality = {
            "lead_rows_total": conn.execute(
                """
                SELECT COUNT(*)
                FROM lead_rows
                """
            ).fetchone()[0],

            "lead_rows_rejected": len(
                rejections
            ),

            "rejections_by_reason": (
                rejection_counts
            ),

            "duplicate_lead_rows_merged": (
    conn.execute(
        "SELECT COUNT(*) FROM lead_rows"
    ).fetchone()[0]
    - conn.execute(
        "SELECT COUNT(*) FROM rejections"
    ).fetchone()[0]
    - conn.execute(
        "SELECT COUNT(*) FROM leads"
    ).fetchone()[0]
),

            "field_warnings": conn.execute(
                """
                SELECT COUNT(*)
                FROM field_warnings
                """
            ).fetchone()[0],

            "events_total": conn.execute(
                """
                SELECT COUNT(*)
                FROM event_lines
                """
            ).fetchone()[0],

            "malformed_events": conn.execute(
                """
                SELECT COUNT(*)
                FROM event_lines
                WHERE status = 'malformed'
                """
            ).fetchone()[0],

            "duplicate_events_dropped":
                conn.execute(
                    """
                    SELECT COUNT(*)
                    FROM event_lines
                    WHERE status = 'duplicate'
                    """
                ).fetchone()[0],

            "orphan_events": event_quality[
                "orphan_events"
            ],

            "unknown_disposition_events":
                event_quality[
                    "unknown_disposition_events"
                ],
        }

        with (
            output_dir / "data_quality.json"
        ).open(
            "w",
            encoding="utf-8",
        ) as file:
            json.dump(
                quality,
                file,
                indent=2,
            )

    finally:
        conn.close()

    print(
        "Reports generated in:",
        output_dir.resolve(),
    )

    for filename in [
        *REPORT_COLUMNS.keys(),
        "data_quality.json",
    ]:
        print(" -", filename)


if __name__ == "__main__":
    generate_reports()
