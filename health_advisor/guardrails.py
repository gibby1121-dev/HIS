"""Guardrails — personal reference, not medical advice.

Detects when an answer must carry a flag: methylene-blue safety, optimal-vs-
standard lab ranges, and open medical loops that belong with a physician.
Returned flags are meant to be appended to any answer they trigger on.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Optimal targets that run TIGHTER than the standard lab reference range.
# When any of these markers is discussed, say the optimal target and that it is
# tighter than what a standard panel flags.
OPTIMAL_TIGHTER_THAN_STANDARD = {
    "fasting insulin": "< 6 µIU/mL",
    "homa-ir": "< 1.0 (under 2.0 acceptable)",
    "fasting glucose": "< 90 mg/dL",
    "a1c": "< 5.4%",
    "triglycerides": "< 80 mg/dL",
    "trig/hdl": "< 1.5",
}

# The standing baseline guardrail on every answer.
BASE_DISCLAIMER = (
    "Personal reference, not medical advice. Open medical questions belong with "
    "a physician."
)

_MB_PATTERN = re.compile(r"\b(methylene\s*blue|\bMB\b)\b", re.IGNORECASE)
_MEDICAL_LOOP_PATTERN = re.compile(
    r"\b(statin|atorvastatin|colonoscopy|hgb|hct|hemoglobin|hematocrit|"
    r"prescription|dose daily|once daily)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class GuardrailFlag:
    kind: str          # mb-safety | optimal-vs-standard | medical-loop
    message: str

    def __str__(self) -> str:
        return f"[{self.kind}] {self.message}"


def _mb_flags(text: str) -> list[GuardrailFlag]:
    if not _MB_PATTERN.search(text):
        return []
    return [
        GuardrailFlag(
            "mb-safety",
            "Methylene blue is a potent MAOI — serotonin-syndrome risk; confirm "
            "NO SSRIs/SNRIs/MAOIs/bupropion/other serotonergics. Screen for G6PD "
            "deficiency (hemolysis risk).",
        ),
        GuardrailFlag(
            "mb-safety",
            "Dose is WEIGHED in grams of diluted solution on a scale — never "
            "count drops. Same scale number is NOT the same dose: 6 g of 1% = "
            "60 mg, 6 g of 5% = 300 mg (5x). Confirm the % on the bottle every "
            "time; at 5% use a scale reading to 0.1 g or finer.",
        ),
        GuardrailFlag(
            "medical-loop",
            "Section 1 calls MB 'situational only' while the newer entry moves "
            "toward once-daily — unresolved. Close with a physician before daily "
            "use.",
        ),
    ]


def _optimal_flags(text: str) -> list[GuardrailFlag]:
    low = text.lower()
    out: list[GuardrailFlag] = []
    for marker, target in OPTIMAL_TIGHTER_THAN_STANDARD.items():
        if marker in low:
            out.append(
                GuardrailFlag(
                    "optimal-vs-standard",
                    f"{marker}: optimal target {target} runs tighter than the "
                    f"standard lab reference range.",
                )
            )
    return out


def _medical_loop_flags(text: str, mb_present: bool) -> list[GuardrailFlag]:
    if not _MEDICAL_LOOP_PATTERN.search(text):
        return []
    return [
        GuardrailFlag(
            "medical-loop",
            "Touches an open medical loop (labs/meds/procedure). Flag it for a "
            "physician rather than resolving it here.",
        )
    ]


def guardrail_flags(text: str) -> list[GuardrailFlag]:
    """All guardrail flags triggered by ``text`` (a query and/or draft answer)."""
    flags = _mb_flags(text)
    mb_present = bool(flags)
    flags += _optimal_flags(text)
    flags += _medical_loop_flags(text, mb_present)
    # de-dup identical messages, preserve order
    seen: set[tuple[str, str]] = set()
    unique: list[GuardrailFlag] = []
    for f in flags:
        key = (f.kind, f.message)
        if key in seen:
            continue
        seen.add(key)
        unique.append(f)
    return unique
