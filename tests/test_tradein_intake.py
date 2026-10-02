"""Quote-intake tests with a mocked Claude client (no network, no credentials)."""

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tradein import intake  # noqa: E402


def num(value, evidence, source="document"):
    return {"value": value, "evidence": evidence, "source": source}


def txt(value, source="document"):
    return {"value": value, "source": source}


ABSENT_N = {"value": None, "evidence": None, "source": "absent"}
ABSENT_S = {"value": None, "source": "absent"}


def extraction(**over):
    ex = {
        "dealer_name": txt("Sample Implement Co"),
        "quote_date": txt("2026-09-28"),
        "new_unit": txt("2026 John Deere 9RX 640"),
        "list_price": num(905000, "List Price $905,000.00"),
        "quoted_price_with_trade": num(812000, "Selling Price $812,000"),
        "trade_allowance": num(455000, "Trade Allowance (455,000)"),
        "stated_difference": num(361800, "Balance Due $361,800"),
        "cash_price_no_trade": ABSENT_N,
        "trade_payoff": ABSENT_N,
        "other_charges": [{"label": "Freight/PDI", "amount": 4800, "evidence": "Freight & PDI 4,800"}],
        "financing_apr": num(0, "0.0% APR"),
        "financing_term_months": num(60, "60 months"),
        "financing_payments_per_year": num(1, "annual payments"),
        "financing_waiver_months": ABSENT_N,
        "cash_in_lieu": ABSENT_N,
        "trade_make": txt("John Deere"),
        "trade_model": txt("9RX 640"),
        "trade_year": num(2021, "2021 JD 9RX640"),
        "trade_hours": num(2050, "2,050 hrs", "note"),
        "trade_serial": ABSENT_S,
        "trade_config": txt("36in tracks, PTO", "note"),
        "unreadable": [],
    }
    ex.update(over)
    return ex


class FakeClient:
    def __init__(self, payload, stop_reason="end_turn"):
        self.payload, self.stop_reason, self.calls = payload, stop_reason, []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **kw):
        self.calls.append(kw)
        block = SimpleNamespace(type="text", text=json.dumps(self.payload))
        return SimpleNamespace(stop_reason=self.stop_reason, content=[block])


NOTE = "Trading my 2021 9RX 640, 2,050 hrs, 36in tracks with PTO"


@pytest.fixture
def quote_png(tmp_path):
    p = tmp_path / "quote.png"
    p.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 64)
    return p


def test_happy_path_builds_deal(quote_png):
    client = FakeClient(extraction())
    r = intake.extract_deal([quote_png], notes=NOTE, client=client)
    assert r.ready and not r.dropped
    q = r.deal["dealer_quote"]
    assert q["quoted_price_with_trade"] == 812000 and q["trade_allowance"] == 455000
    assert q["financing"]["payments_per_year"] == 1
    assert r.deal["trade_unit"]["hours"] == 2050
    assert any("cash price" in x for x in r.questions)


def test_request_shape(quote_png):
    client = FakeClient(extraction())
    intake.extract_deal([quote_png], notes=NOTE, client=client)
    kw = client.calls[0]
    assert kw["model"] == "claude-opus-5-5"
    assert kw["output_config"]["format"]["type"] == "json_schema"
    assert kw["extra_body"] == {"fallbacks": "default"}
    assert kw["messages"][0]["content"][0]["type"] == "image"


def test_number_not_in_its_evidence_is_dropped(quote_png):
    ex = extraction(trade_allowance=num(475000, "Trade Allowance (455,000)"))
    r = intake.extract_deal([quote_png], notes=NOTE, client=FakeClient(ex))
    assert r.deal["dealer_quote"]["trade_allowance"] is None
    assert not r.ready
    assert any("trade_allowance" in d for d in r.dropped)


def test_note_evidence_must_be_in_the_note(quote_png):
    ex = extraction(trade_hours=num(1800, "1,800 hrs", "note"))
    r = intake.extract_deal([quote_png], notes=NOTE, client=FakeClient(ex))
    assert r.deal["trade_unit"]["hours"] is None
    assert any("engine hours" in x for x in r.questions)


def test_math_mismatch_becomes_question(quote_png):
    ex = extraction(stated_difference=num(300000, "Balance Due $300,000"))
    r = intake.extract_deal([quote_png], notes=NOTE, client=FakeClient(ex))
    assert not r.ready
    assert any("doesn't tie out" in x for x in r.questions)


def test_charges_included_in_math_check(quote_png):
    # 812,000 - 455,000 + 4,800 = 361,800 -> consistent
    r = intake.extract_deal([quote_png], notes=NOTE, client=FakeClient(extraction()))
    assert not any("tie out" in x for x in r.questions)


def test_unsupported_charge_dropped(quote_png):
    ex = extraction(other_charges=[{"label": "Doc fee", "amount": 950, "evidence": "Doc fee 590"}])
    r = intake.extract_deal([quote_png], notes=NOTE, client=FakeClient(ex))
    assert r.deal["dealer_quote"]["other_charges"] == []


def test_refusal_raises(quote_png):
    with pytest.raises(intake.IntakeError, match="declined"):
        intake.extract_deal([quote_png], client=FakeClient(extraction(), "refusal"))


def test_unsupported_file_type(tmp_path):
    p = tmp_path / "quote.docx"
    p.write_bytes(b"x")
    with pytest.raises(intake.IntakeError, match="photo"):
        intake.extract_deal([p], client=FakeClient(extraction()))


@pytest.mark.parametrize("value,text,ok", [
    (455000, "Trade (455,000.00)", True), (455000, "$455k", True), (2050, "2,050 hrs", True),
    (0, "0% APR", True), (455000, "$45,500", False), (812000, "Total 821,000", False),
])
def test_number_matching(value, text, ok):
    assert intake._number_in_text(value, text) is ok


def test_payment_frequency_words():
    assert intake._word_supports("financing_payments_per_year", 12, "monthly payments")
    assert not intake._word_supports("financing_payments_per_year", 1, "semi-annual")
    assert not intake._word_supports("trade_hours", 1, "annual")
