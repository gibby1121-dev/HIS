"""Read a dealer quote (photo or PDF) with Claude and turn it into a deal file.

Operators don't fill in JSON. They have a photo of the dealer's worksheet,
a PDF proposal, and a sentence about their machine. This module sends those to
Claude and gets back structured fields.

Every extracted number is checked before it is used:

* Claude must return the **verbatim text** it read each number from
  (``evidence``). A number that doesn't appear in its own evidence is dropped.
* When an operator note is the source, the evidence must appear in the note
  word for word.
* Arithmetic is checked: quoted price − allowance should match the stated
  difference/balance on the worksheet. A mismatch becomes a question, not a
  silent correction.

Anything missing comes back as a plain-language question for the operator.
"""

from __future__ import annotations

import base64
import json
import mimetypes
import re
from dataclasses import dataclass, field
from pathlib import Path

MODEL = "claude-opus-5-5"
_IMAGE_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}


class IntakeError(RuntimeError):
    pass


def _numfield(desc: str) -> dict:
    return {
        "type": "object",
        "description": desc,
        "properties": {
            "value": {"type": ["number", "null"]},
            "evidence": {"type": ["string", "null"],
                         "description": "Exact text copied from the document or note that shows this number."},
            "source": {"type": "string", "enum": ["document", "note", "absent"]},
        },
        "required": ["value", "evidence", "source"],
        "additionalProperties": False,
    }


def _strfield(desc: str) -> dict:
    return {
        "type": "object",
        "description": desc,
        "properties": {
            "value": {"type": ["string", "null"]},
            "source": {"type": "string", "enum": ["document", "note", "absent"]},
        },
        "required": ["value", "source"],
        "additionalProperties": False,
    }


SCHEMA = {
    "type": "object",
    "properties": {
        "dealer_name": _strfield("Dealership name"),
        "quote_date": _strfield("Date on the quote, YYYY-MM-DD"),
        "new_unit": _strfield("New unit being purchased, e.g. '2026 John Deere 9RX 640'"),
        "list_price": _numfield("MSRP / list price of the new unit"),
        "quoted_price_with_trade": _numfield("Selling price of the new unit on this trade deal, before the trade allowance is subtracted"),
        "trade_allowance": _numfield("Trade-in allowance credited for the operator's machine"),
        "stated_difference": _numfield("Difference / balance / amount due printed on the quote after the trade"),
        "cash_price_no_trade": _numfield("A price for the new unit with NO trade, only if the document states one"),
        "trade_payoff": _numfield("Lien payoff on the trade unit the dealer will pay"),
        "other_charges": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "label": {"type": "string"},
                    "amount": {"type": "number"},
                    "evidence": {"type": "string"},
                },
                "required": ["label", "amount", "evidence"],
                "additionalProperties": False,
            },
        },
        "financing_apr": _numfield("Financing rate in percent"),
        "financing_term_months": _numfield("Financing term in months"),
        "financing_payments_per_year": _numfield("1 for annual, 2 semi-annual, 4 quarterly, 12 monthly"),
        "financing_waiver_months": _numfield("Interest waiver period in months"),
        "cash_in_lieu": _numfield("Cash discount offered instead of the financing rate"),
        "trade_make": _strfield("Trade unit make"),
        "trade_model": _strfield("Trade unit model"),
        "trade_year": _numfield("Trade unit model year"),
        "trade_hours": _numfield("Trade unit engine hours"),
        "trade_serial": _strfield("Trade unit serial number"),
        "trade_config": _strfield("Trade unit configuration: tracks/wheels, PTO, hitch, precision tech"),
        "unreadable": {"type": "array", "items": {"type": "string"},
                       "description": "Parts of the document that were present but couldn't be read"},
    },
    "required": [
        "dealer_name", "quote_date", "new_unit", "list_price", "quoted_price_with_trade",
        "trade_allowance", "stated_difference", "cash_price_no_trade", "trade_payoff",
        "other_charges", "financing_apr", "financing_term_months",
        "financing_payments_per_year", "financing_waiver_months", "cash_in_lieu",
        "trade_make", "trade_model", "trade_year", "trade_hours", "trade_serial",
        "trade_config", "unreadable",
    ],
    "additionalProperties": False,
}

SYSTEM = """You read farm-equipment dealer quotes and trade-in worksheets for an \
auction company that helps row-crop operators check whether a trade-in offer is fair.

Extract only what the document or the operator's note actually says. For every \
number, copy the exact text you read it from into `evidence` and say whether it \
came from the document or the note. If a value isn't there, return null with \
source "absent". Never compute or infer a value that isn't printed: in particular, \
a no-trade cash price exists only if the quote states one. If a figure is present \
but illegible, leave it null and describe it in `unreadable`."""


@dataclass
class IntakeResult:
    deal: dict
    questions: list[str]
    dropped: list[str] = field(default_factory=list)
    ready: bool = False


def _content_block(path: Path) -> dict:
    if not path.exists():
        raise IntakeError(f"'{path}' does not exist.")
    mime = mimetypes.guess_type(path.name)[0] or ""
    data = base64.standard_b64encode(path.read_bytes()).decode("ascii")
    if mime == "application/pdf":
        return {"type": "document",
                "source": {"type": "base64", "media_type": mime, "data": data}}
    if mime in _IMAGE_TYPES:
        return {"type": "image",
                "source": {"type": "base64", "media_type": mime, "data": data}}
    raise IntakeError(f"'{path.name}': send a photo (jpg/png/webp) or a PDF, not {mime or 'this file type'}.")


def _digits(s: str) -> str:
    return re.sub(r"[^\d.]", "", s or "")


def _number_in_text(value: float, text: str) -> bool:
    """Does ``value`` appear in ``text`` (allowing $, commas, k, %, decimals)?"""
    if text is None:
        return False
    t = text.lower().replace(",", "")
    candidates = set()
    for tok in re.findall(r"\d+(?:\.\d+)?\s*k?", t):
        k = tok.endswith("k")
        try:
            n = float(tok.rstrip("k").strip())
        except ValueError:
            continue
        candidates.add(n * 1000 if k else n)
    return any(abs(c - value) < 0.006 * max(1.0, abs(value)) for c in candidates)


_PERIOD_WORDS = {1: ("annual", "yearly", "per year"), 2: ("semi-annual", "semiannual"),
                 4: ("quarterly",), 12: ("monthly", "per month", "/mo")}


def _word_supports(key: str, value: float, evidence: str) -> bool:
    """Payment frequency is usually printed as a word, not a number."""
    if key != "financing_payments_per_year" or not evidence:
        return False
    ev = evidence.lower()
    if value == 1 and any(w in ev for w in ("semi-annual", "semiannual")):
        return False
    return any(w in ev for w in _PERIOD_WORDS.get(int(value), ()))


def call_claude(blocks: list[dict], notes: str, client=None) -> dict:
    """One structured-output request. Returns the parsed JSON object."""
    try:
        import anthropic
    except ImportError as exc:  # pragma: no cover
        raise IntakeError("pip install anthropic to read quotes.") from exc
    client = client or anthropic.Anthropic()
    content = list(blocks) + [{
        "type": "text",
        "text": ("Operator's note about the trade unit: " + notes) if notes else
                "No operator note was provided.",
    }]
    try:
        resp = client.beta.messages.create(
            model=MODEL,
            max_tokens=16000,
            system=SYSTEM,
            messages=[{"role": "user", "content": content}],
            output_config={"effort": "medium",
                           "format": {"type": "json_schema", "schema": SCHEMA}},
            betas=["server-side-fallback-2026-07-01"],
            extra_body={"fallbacks": "default"},
        )
    except anthropic.AuthenticationError as exc:
        raise IntakeError("Anthropic API credentials are missing or invalid.") from exc
    except anthropic.BadRequestError as exc:
        raise IntakeError(f"The API rejected the request: {exc.message}") from exc
    except anthropic.RateLimitError as exc:
        raise IntakeError("Rate limited by the API; try again shortly.") from exc
    except anthropic.APIStatusError as exc:
        raise IntakeError(f"API error {exc.status_code}: {exc.message}") from exc
    except anthropic.APIConnectionError as exc:
        raise IntakeError("Could not reach the Anthropic API.") from exc

    if resp.stop_reason == "refusal":
        raise IntakeError("The model declined to read this document.")
    if resp.stop_reason == "max_tokens":
        raise IntakeError("The response was cut off; try fewer pages.")
    text = next((b.text for b in resp.content if b.type == "text"), None)
    if not text:
        raise IntakeError("No structured response came back.")
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise IntakeError(f"Unparseable response: {exc}") from exc


def verify(ex: dict, notes: str) -> tuple[dict, list[str]]:
    """Null out numbers whose evidence doesn't support them."""
    dropped = []
    norm_notes = " ".join((notes or "").split()).lower()
    for key, f in list(ex.items()):
        if not isinstance(f, dict) or "value" not in f or "evidence" not in f:
            continue
        v = f["value"]
        if v is None:
            continue
        ev = f.get("evidence") or ""
        ok = _number_in_text(float(v), ev) or _word_supports(key, float(v), ev)
        if ok and f.get("source") == "note":
            ok = " ".join(ev.split()).lower() in norm_notes
        if not ok:
            dropped.append(f"{key}={v!r} (evidence: {ev!r})")
            ex[key] = {"value": None, "evidence": None, "source": "absent"}
    kept = []
    for ch in ex.get("other_charges") or []:
        if _number_in_text(float(ch["amount"]), ch.get("evidence", "")):
            kept.append(ch)
        else:
            dropped.append(f"other_charges '{ch.get('label')}'={ch.get('amount')!r}")
    ex["other_charges"] = kept
    return ex, dropped


def to_deal(ex: dict) -> tuple[dict, list[str], bool]:
    """Map verified extraction to the deal-file shape, plus open questions."""
    v = lambda k: (ex.get(k) or {}).get("value")  # noqa: E731
    q: list[str] = []
    blocking = False

    for key, ask in (("trade_make", "What make is the machine you're trading?"),
                     ("trade_model", "What model is it?"),
                     ("trade_year", "What model year is it?"),
                     ("trade_hours", "How many engine hours are on it?")):
        if v(key) in (None, ""):
            q.append(ask)
            blocking = True
    if v("quoted_price_with_trade") is None:
        q.append("What price is the dealer showing for the new unit on this deal?")
        blocking = True
    if v("trade_allowance") is None:
        q.append("What trade allowance is the dealer showing for your machine?")
        blocking = True
    if v("cash_price_no_trade") is None:
        q.append("Ask the dealer: what's the cash price on the new unit if you don't trade? "
                 "(The check can run without it, but this is the number that settles it.)")
    qp, ta, sd = v("quoted_price_with_trade"), v("trade_allowance"), v("stated_difference")
    if None not in (qp, ta, sd):
        charges = sum(c["amount"] for c in ex.get("other_charges") or [])
        if abs((qp - ta) - sd) > 1 and abs((qp - ta + charges) - sd) > 1:
            q.append(f"The quote's math doesn't tie out: {qp:,.0f} − {ta:,.0f} ≠ {sd:,.0f}. "
                     "Which number is right?")
            blocking = True
    for u in ex.get("unreadable") or []:
        q.append(f"Couldn't read part of the quote: {u}. What does it say?")

    fin = None
    if v("financing_term_months"):
        fin = {"apr": v("financing_apr") or 0.0,
               "term_months": int(v("financing_term_months")),
               "payments_per_year": int(v("financing_payments_per_year") or 1),
               "waiver_months": int(v("financing_waiver_months") or 0),
               "cash_in_lieu": v("cash_in_lieu")}
        if v("financing_payments_per_year") is None:
            q.append("Are the financing payments annual or monthly?")

    deal = {
        "as_of": v("quote_date"),
        "operator": {"state": "IA"},
        "trade_unit": {
            "make": v("trade_make"), "model": v("trade_model"),
            "year": v("trade_year"), "hours": v("trade_hours"),
            "serial": v("trade_serial"), "config": v("trade_config"),
        },
        "dealer_quote": {
            "dealer": v("dealer_name"),
            "new_unit": v("new_unit") or "new unit",
            "list_price": v("list_price"),
            "quoted_price_with_trade": qp,
            "trade_allowance": ta,
            "cash_price_no_trade": v("cash_price_no_trade"),
            "trade_payoff": v("trade_payoff") or 0,
            "other_charges": [{"label": c["label"], "amount": c["amount"]}
                              for c in ex.get("other_charges") or []],
            "financing": fin,
        },
    }
    if not deal["as_of"] or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(deal["as_of"])):
        deal.pop("as_of")
    q.append("Which state is the farm in? (It changes how trades are taxed.)")
    return deal, q, not blocking


def extract_deal(paths: list[Path], notes: str = "", client=None) -> IntakeResult:
    if not paths:
        raise IntakeError("No quote files given.")
    blocks = [_content_block(Path(p)) for p in paths]
    raw = call_claude(blocks, notes, client)
    verified, dropped = verify(raw, notes)
    deal, questions, ready = to_deal(verified)
    return IntakeResult(deal=deal, questions=questions, dropped=dropped, ready=ready)
