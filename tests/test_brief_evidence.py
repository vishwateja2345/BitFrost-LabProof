"""The retained live brief records still verify against the run they were made from and were made by real providers."""
from pathlib import Path

import pytest

from labproof.brief import verify_brief
from labproof.contracts import parse_json

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "evidence" / "local-python-01"
RECORDS = sorted(path.parent for path in (ROOT / "evidence" / "live-brief-01").rglob("brief.json"))
EXPECTED = {"direct": "sourced", "relay": "sourced", "attempt-1/direct": "model_failed", "attempt-1/relay": "no_verified_advice"}


def test_the_expected_live_records_are_retained():
    assert {path.relative_to(ROOT / "evidence" / "live-brief-01").as_posix() for path in RECORDS} == set(EXPECTED)


@pytest.mark.parametrize("record", RECORDS, ids=lambda path: path.relative_to(ROOT / "evidence" / "live-brief-01").as_posix())
def test_a_retained_live_brief_verifies_and_is_not_a_demo(record):
    result = verify_brief(RUN, record)
    assert result["valid"] is True and result["mode"] == "live"
    brief = parse_json((record / "brief.json").read_bytes())
    assert brief["search"]["via"] in ("tavily", "bifrost_relay") and brief["model"]["via"] == "bifrost"
    assert [entry["status"] for entry in brief["classes"]] == [EXPECTED[record.relative_to(ROOT / "evidence" / "live-brief-01").as_posix()]]
    assert all(source["url"].startswith(("https://owasp.org/", "https://cheatsheetseries.owasp.org/")) for entry in brief["classes"] for source in entry["sources"])


@pytest.mark.parametrize("record", RECORDS, ids=lambda path: path.relative_to(ROOT / "evidence" / "live-brief-01").as_posix())
def test_a_retained_live_brief_holds_no_credential(record):
    text = (record / "brief.json").read_text(encoding="utf-8") + (record / "brief.html").read_text(encoding="utf-8")
    assert "tvly-" not in text and "sk-bf-" not in text and "x-bf-vk" not in text and "Bearer" not in text
