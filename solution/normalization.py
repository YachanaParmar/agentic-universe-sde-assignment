
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


DATE_FORMATS = (
    "%Y-%m-%d",
    "%d/%m/%Y",
    "%d-%m-%Y",
    "%d-%b-%Y",
)


def normalize_header(value):
    return re.sub(r"[_\s]+", " ", value.strip().lower())


def normalize_phone(value):
    digits = re.sub(r"\D", "", str(value))

    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    elif len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]

    if len(digits) != 10 or digits[0] not in "6789":
        raise ValueError("invalid_phone")

    return "+91" + digits


def normalize_date(value):
    value = str(value).strip()

    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            continue

    raise ValueError("invalid_date")


def normalize_decimal(value):
    value = str(value).strip()

    value = re.sub(
        r"^(₹|Rs\.?|INR)\s*",
        "",
        value,
        flags=re.IGNORECASE,
    ).replace(",", "")

    try:
        number = Decimal(value)
    except InvalidOperation:
        raise ValueError("invalid_decimal")

    if not number.is_finite() or number < 0:
        raise ValueError("invalid_decimal")

    return str(
        number.quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )
    )


def normalize_enum(value, allowed):
    value = str(value).strip().lower()

    if value not in [v.lower() for v in allowed]:
        raise ValueError("invalid_enum")

    return value


def normalize_field(value, field):
    if value is None or not str(value).strip():
        return None

    kind = field["type"]

    if kind == "string":
        return str(value).strip()

    if kind == "phone":
        return normalize_phone(value)

    if kind == "date":
        return normalize_date(value)

    if kind == "decimal":
        return normalize_decimal(value)

    if kind == "enum":
        return normalize_enum(value, field["values"])

    raise ValueError(f"Unsupported field type: {kind}")
