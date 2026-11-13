
import pytest

from solution.normalization import (
    normalize_phone,
    normalize_date,
    normalize_decimal,
    normalize_header,
)


@pytest.mark.parametrize("raw", [
    "9876543210",
    "+91 98765 43210",
    "91-98765-43210",
    "09876543210",
])
def test_valid_phone(raw):
    assert normalize_phone(raw) == "+919876543210"


@pytest.mark.parametrize("raw", [
    "12345",
    "5123456789",
    "9999999999999",
])
def test_invalid_phone(raw):
    with pytest.raises(ValueError):
        normalize_phone(raw)


def test_header_alias_normalization():
    assert normalize_header(" Customer_Name ") == "customer name"


def test_date_normalization():
    assert normalize_date("01-Dec-2026") == "2026-12-01"
    assert normalize_date("01/12/2026") == "2026-12-01"


def test_invalid_date():
    with pytest.raises(ValueError):
        normalize_date("31/02/2026")


def test_decimal_normalization():
    assert normalize_decimal("Rs. 1,250.50") == "1250.50"
    assert normalize_decimal("₹999") == "999.00"
