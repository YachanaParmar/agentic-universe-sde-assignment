
import csv
import json
from collections import defaultdict

from solution.database import connect


DISPOSITIONS_FILE = (
    "assignment-a-data/schemas/dispositions.csv"
)


def calculate_event_quality(conn):
    """Calculate orphan and unknown disposition event counts."""

    known_codes = set()

    with open(
        DISPOSITIONS_FILE,
        encoding="utf-8-sig",
        newline="",
    ) as file:
        for row in csv.DictReader(file):
            known_codes.add(
                (row["workflow_id"], row["code"])
            )

    valid_leads = {
        (row["workflow_id"], row["phone_hash"])
        for row in conn.execute(
            "SELECT workflow_id, phone_hash FROM leads"
        )
    }

    events = [
        dict(row)
        for row in conn.execute(
            "SELECT * FROM events"
        )
    ]

    # Identify valid initiated calls and their lead identities.
    initiated_calls = {}

    for event in events:
        if event["event_type"] != "call.initiated":
            continue

        identity = (
            event["workflow_id"],
            event["phone_hash"],
        )

        if identity in valid_leads:
            key = (
                event["workflow_id"],
                event["call_id"],
            )
            initiated_calls[key] = identity

    orphan_events = 0
    unknown_disposition_events = 0

    for event in events:
        workflow = event["workflow_id"]
        call_id = event["call_id"]
        key = (workflow, call_id)

        if event["event_type"] == "call.initiated":
            linked = (
                workflow,
                event["phone_hash"],
            ) in valid_leads

        else:
            linked = key in initiated_calls

            if linked and event["phone_hash"]:
                linked = (
                    workflow,
                    event["phone_hash"],
                ) == initiated_calls[key]

        if not linked:
            orphan_events += 1
            continue

        if event["event_type"] in (
            "disposition.set",
            "disposition.override",
        ):
            try:
                payload = json.loads(
                    event["payload_json"]
                )
                code = payload.get(
                    "disposition_code"
                )
            except (ValueError, TypeError):
                code = None

            if (workflow, code) not in known_codes:
                unknown_disposition_events += 1

    return {
        "orphan_events": orphan_events,
        "unknown_disposition_events":
            unknown_disposition_events,
    }


if __name__ == "__main__":
    conn = connect()
    result = calculate_event_quality(conn)
    conn.close()

    print(json.dumps(result, indent=2))
