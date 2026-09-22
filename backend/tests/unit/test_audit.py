import pytest

from app.modules.audit.allowlist import sanitize_changes
from app.shared.csv_safety import csv_safe


def test_audit_changes_are_allowlisted_and_truncated() -> None:
    sanitized = sanitize_changes(
        "membership",
        {"role": "admin", "email": "should-not-appear", "note": "x" * 300},
    )

    assert sanitized == {"role": "admin"}


def test_csv_safe_neutralizes_spreadsheet_formulas() -> None:
    assert (
        csv_safe('=HYPERLINK("https://attacker.test")') == '\'=HYPERLINK("https://attacker.test")'
    )
    assert csv_safe({"role": "member"}) == '{"role":"member"}'


@pytest.mark.parametrize("prefix", ["=", "+", "-", "@", "\t", "\r"])
def test_csv_safe_handles_every_dangerous_prefix(prefix: str) -> None:
    assert csv_safe(prefix + "payload") == "'" + prefix + "payload"
