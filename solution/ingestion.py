
import csv
import hashlib
import hmac
import json
import os
from pathlib import Path

from solution.normalization import (
    normalize_field,
    normalize_header,
    normalize_phone,
)


SCHEMA_DIR = Path("assignment-a-data/schemas")


def phone_hash(phone):
    """Create a keyed hash for matching phone numbers."""
    key = os.environ.get("LEDGER_HMAC_KEY")

    if not key:
        raise RuntimeError(
            "Set LEDGER_HMAC_KEY before ingestion"
        )

    return hmac.new(
        key.encode("utf-8"),
        phone.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def load_schema(workflow_id):
    path = SCHEMA_DIR / f"{workflow_id}.json"

    with path.open(encoding="utf-8") as file:
        return json.load(file)


def map_headers(headers, fields):
    aliases = {}

    for field in fields:
        for name in [field["name"], *field.get("aliases", [])]:
            aliases[normalize_header(name)] = field["name"]

    mapping = {}

    for header in headers:
        normalized = normalize_header(header)

        if normalized in aliases:
            mapping[header] = aliases[normalized]

    return mapping


def validate_row(raw, fields):
    values = {}
    warnings = []

    for field in fields:
        name = field["name"]
        value = raw.get(name)

        if value is None or not str(value).strip():
            if field.get("required"):
                return None, [], f"missing_required:{name}"

            values[name] = None
            continue

        try:
            values[name] = normalize_field(value, field)

        except ValueError:
            if field.get("required"):
                reason = (
                    "invalid_phone"
                    if field["type"] == "phone"
                    else f"invalid_{field['type']}:{name}"
                )
                return None, [], reason

            values[name] = None
            warnings.append(name)

    return values, warnings, None


def ingest_leads(conn, drop_path):
    """Ingest and merge lead CSV records."""
    drop_path = Path(drop_path)
    lead_root = drop_path / "leads"

    if not lead_root.exists():
        raise FileNotFoundError(lead_root)

    for workflow_dir in sorted(lead_root.iterdir()):
        if not workflow_dir.is_dir():
            continue

        workflow_id = workflow_dir.name
        schema = load_schema(workflow_id)
        fields = schema["fields"]

        reference_field = next(
            field["name"]
            for field in fields
            if field.get("reference")
        )

        for csv_path in sorted(workflow_dir.glob("*.csv")):
            batch_id = csv_path.stem
            source_file = str(csv_path.resolve())

            with csv_path.open(
                encoding="utf-8-sig",
                newline="",
            ) as file:

                reader = csv.DictReader(file)
                mapping = map_headers(
                    reader.fieldnames or [],
                    fields,
                )

                row_number = 0

                for source_row in reader:
                    if all(
                        not str(value or "").strip()
                        for value in source_row.values()
                    ):
                        continue

                    row_number += 1

                    already_seen = conn.execute(
                        """
                        SELECT 1 FROM lead_rows
                        WHERE source_file = ?
                        AND row_number = ?
                        """,
                        (source_file, row_number),
                    ).fetchone()

                    if already_seen:
                        continue

                    raw = {
                        mapped: source_row.get(original)
                        for original, mapped in mapping.items()
                    }

                    values, warnings, reason = validate_row(
                        raw, fields
                    )

                    conn.execute(
                        """
                        INSERT INTO lead_rows
                        (source_file, row_number)
                        VALUES (?, ?)
                        """,
                        (source_file, row_number),
                    )

                    if reason:
                        conn.execute(
                            """
                            INSERT INTO rejections
                            (source_file, workflow_id,
                             batch_id, row_number, reason)
                            VALUES (?, ?, ?, ?, ?)
                            """,
                            (
                                source_file,
                                workflow_id,
                                batch_id,
                                row_number,
                                reason,
                            ),
                        )
                        continue

                    for warning in warnings:
                        conn.execute(
                            """
                            INSERT INTO field_warnings
                            (source_file, row_number, field_name)
                            VALUES (?, ?, ?)
                            """,
                            (
                                source_file,
                                row_number,
                                warning,
                            ),
                        )

                    phone = values.pop("phone")
                    identity = phone_hash(phone)

                    existing = conn.execute(
                        """
                        SELECT * FROM leads
                        WHERE workflow_id = ?
                        AND phone_hash = ?
                        """,
                        (workflow_id, identity),
                    ).fetchone()

                    # Never store plaintext customer names.
                    values.pop("customer_name", None)

                    if existing:
                        conn.execute(
                            """
                            INSERT OR IGNORE INTO duplicate_leads
                            (source_file, row_number, workflow_id)
                            VALUES (?, ?, ?)
                            """,
                            (
                                source_file,
                                row_number,
                                workflow_id,
                            ),
                        )

                        merged = json.loads(
                            existing["fields_json"]
                        )

                        for name, value in values.items():
                            if value is not None:
                                merged[name] = value

                        conn.execute(
                            """
                            UPDATE leads
                            SET fields_json = ?,
                                external_ref = ?
                            WHERE id = ?
                            """,
                            (
                                json.dumps(merged),
                                merged[reference_field],
                                existing["id"],
                            ),
                        )

                    else:
                        for field in fields:
                            name = field["name"]

                            if (
                                field.get("default") is not None
                                and values.get(name) is None
                            ):
                                values[name] = field["default"]

                        conn.execute(
                            """
                            INSERT INTO leads
                            (
                                workflow_id,
                                phone_hash,
                                phone_last4,
                                batch_id,
                                external_ref,
                                fields_json
                            )
                            VALUES (?, ?, ?, ?, ?, ?)
                            """,
                            (
                                workflow_id,
                                identity,
                                phone[-4:],
                                batch_id,
                                values[reference_field],
                                json.dumps(values),
                            ),
                        )

    conn.commit()


def ingest_events(conn, drop_path):
    """
    Ingest JSONL call events.

    Records malformed and duplicate lines.
    Keeps events available for late lead matching.
    """
    drop_path = Path(drop_path)
    events_dir = drop_path / "events"

    if not events_dir.exists():
        raise FileNotFoundError(events_dir)

    for event_file in sorted(events_dir.glob("*.jsonl")):
        source_file = str(event_file.resolve())

        with event_file.open(encoding="utf-8") as file:
            for line_number, line in enumerate(file, start=1):

                if not line.strip():
                    continue

                already_processed = conn.execute(
                    """
                    SELECT 1 FROM event_lines
                    WHERE source_file = ?
                    AND line_number = ?
                    """,
                    (source_file, line_number),
                ).fetchone()

                if already_processed:
                    continue

                event_id = None
                status = "malformed"

                try:
                    event = json.loads(line)

                    if not isinstance(event, dict):
                        raise ValueError(
                            "Event must be a JSON object"
                        )

                    event_id = event.get("event_id")

                    if not event_id:
                        raise ValueError("Missing event_id")

                except (
                    json.JSONDecodeError,
                    ValueError,
                    TypeError,
                ):
                    pass

                else:
                    duplicate = conn.execute(
                        """
                        SELECT 1 FROM events
                        WHERE event_id = ?
                        """,
                        (event_id,),
                    ).fetchone()

                    if duplicate:
                        status = "duplicate"

                    else:
                        workflow_id = event.get("workflow_id")
                        phone = event.get("phone")
                        identity = None

                        if phone:
                            try:
                                canonical = normalize_phone(phone)
                                identity = phone_hash(canonical)
                            except ValueError:
                                identity = None

                        conn.execute(
                            """
                            INSERT INTO events
                            (
                                event_id,
                                event_type,
                                workflow_id,
                                call_id,
                                occurred_at,
                                phone_hash,
                                payload_json
                            )
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                event_id,
                                event.get("event_type", ""),
                                workflow_id,
                                event.get("call_id"),
                                event.get("occurred_at"),
                                identity,
                                json.dumps(
                                    event.get("payload") or {}
                                ),
                            ),
                        )

                        status = "stored"

                conn.execute(
                    """
                    INSERT INTO event_lines
                    (
                        source_file,
                        line_number,
                        event_id,
                        status
                    )
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        source_file,
                        line_number,
                        event_id,
                        status,
                    ),
                )

    conn.commit()
