import json

import pytest

from labproof.bifrost import GatewayClient, ScriptedTransport, SearchClient
from labproof.cli import main
from labproof.contracts import ValidationError
from labproof.freshness import check_freshness, render_html

ANSWER = "The sample API is supported until October 2027."
DOMAIN = "docs.example.org"


def chat(body):
    return 200, {"choices": [{"message": {"content": json.dumps(body)}, "finish_reason": "stop"}]}


def clients(ids, observed_date, source):
    search = ScriptedTransport([(200, {"results": [
        {"url": "https://docs.example.org.evil.test", "content": "Exclude this domain"},
        {"url": "https://docs.example.org/releases", "title": "<Release schedule>", "content": "The API ends in October 2029."},
    ]})])
    gateway = ScriptedTransport([chat({"ids": ids}), chat({"date": observed_date, "source": source})])
    return (SearchClient(api_key="test-search", transport=search),
            GatewayClient("http://127.0.0.1:8080", "test/model", token="test-gateway", transport=gateway))


def test_explicit_date_checked_even_if_model_omits_it():
    search, gateway = clients([], "2029-10", "s1")
    report = check_freshness(ANSWER, [DOMAIN], search, gateway)
    row, = report["claims"]
    assert row["claim"] == ANSWER and row["freshness_score"] == 0
    assert row["sources"][0]["url"] == "https://docs.example.org/releases"
    assert "2027" not in search.transport.calls[0]["body"]["query"]
    assert "Exclude this domain" not in gateway.transport.calls[1]["body"]["messages"][1]["content"]
    assert "&lt;Release schedule&gt;" in render_html(report)


def test_invented_source_leaves_claim_unscored():
    search, gateway = clients([1], "2029-10", "invented")
    report = check_freshness(ANSWER, [DOMAIN], search, gateway)
    assert report["status"] == "partial" and report["claims"][0]["freshness_score"] is None


def test_invented_claim_id_is_not_sent_to_search():
    search, gateway = clients([2], "2029-10", "s1")
    with pytest.raises(ValidationError, match="unknown sentence ID"):
        check_freshness(ANSWER, [DOMAIN], search, gateway)
    assert not search.transport.calls


def test_freshness_requires_outbound_opt_in(tmp_path, capsys):
    assert main(["freshness", str(tmp_path / "answer.txt"), "--domain", DOMAIN,
                 "--output", str(tmp_path / "report")]) == 1
    assert "confirm-outbound" in capsys.readouterr().err
    assert not (tmp_path / "report").exists()


def test_date_must_be_present_in_the_selected_excerpt():
    search, gateway = clients([1], "2027-10", "s1")
    report = check_freshness(ANSWER, [DOMAIN], search, gateway)
    row, = report["claims"]
    assert row["verdict"] == "insufficient" and row["freshness_score"] is None
    assert "absent" in row["error"]
