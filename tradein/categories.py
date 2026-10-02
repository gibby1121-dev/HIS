"""Map make + model to a row-crop equipment category.

Used to group MIA auction results (the Auction Summary Report carries no
category column) so Sandhills-estimate calibration is computed per category,
and to sanity-check a trade unit's stated category.

Patterns are deliberately conservative: an unrecognized model returns
``OTHER`` rather than a guess.
"""

from __future__ import annotations

import re

FOUR_WD = "4WD Tractor"
ROW_CROP = "Row-Crop Tractor"
COMBINE = "Combine"
PLANTER = "Planter"
SPRAYER = "Self-Propelled Sprayer"
GRAIN_CART = "Grain Cart"
HEADER = "Combine Header"
OTHER = "Other"

CATEGORIES = (FOUR_WD, ROW_CROP, COMBINE, PLANTER, SPRAYER, GRAIN_CART, HEADER)

# (make regex, model regex, category). First match wins, so more specific
# rows come first.
_RULES: list[tuple[str, str, str]] = [
    # --- John Deere ------------------------------------------------------
    (r"deere", r"^9r[tx]?\s*\d{3}$|^9\d{2}0r[tx]?$|^9[2-6]\d0t?$|^9\d{3}r[tx]?$", FOUR_WD),
    (r"deere", r"^[78]r[tx]?\s*\d{3}$|^[78]\d{2}0r[t]?$|^8\d{3}r?t?$|^7\d{3}r$", ROW_CROP),
    (r"deere", r"^s[67]\d{2}$|^x9\s*\d{3,4}$|^9[5-8]\d0\s*sts$|^96[5-9]0\s*sts$|^t670$", COMBINE),
    (r"deere", r"^db\d{2}$|^17\d{2}(nt|ccs)?$|^1775nt$|^1795$", PLANTER),
    (r"deere", r"^r?40[2-4]\d$|^4[7-9][3-4]0$|^4630$|^4[0-9]{2}r$|^6[0-9]{2}r$", SPRAYER),
    (r"deere", r"^(7\d{2}|8\d{2}|9\d{2})(fd|d|f|r|x|c)$|^(hd|rd|fd)\d{2}[rf]?$", HEADER),
    # --- Case IH ---------------------------------------------------------
    (r"case", r"steiger|quadtrac|rowtrac|^stx\s*\d{3}", FOUR_WD),
    (r"case", r"magnum|optum|^mx\s*\d{3}", ROW_CROP),
    (r"case", r"^(af\s*)?([5-9]1[2-5]0|[5-9]2[2-6]0|[5-9]0[1-8]0|[1-9]?[0-9]{3}\s*axial)|axial|^af\d{1,2}$", COMBINE),
    (r"case", r"early\s*riser|^1[2-5][0-9]0$|^2[01][0-9]0$", PLANTER),
    (r"case", r"patriot|trident", SPRAYER),
    # --- New Holland -----------------------------------------------------
    (r"new\s*holland", r"^t9[\.\s]?\d{3}", FOUR_WD),
    (r"new\s*holland", r"^t8[\.\s]?\d{3}", ROW_CROP),
    (r"new\s*holland", r"^cr\s*\d|^cr[x]?\d{1,2}", COMBINE),
    (r"new\s*holland", r"guardian|^sp\.?\d{3}", SPRAYER),
    # --- AGCO family -----------------------------------------------------
    (r"challenger", r"^mt[89]\d{2}", FOUR_WD),
    (r"challenger|agco", r"rogator|^rg\d{3}", SPRAYER),
    (r"fendt", r"rogator|^rg\d{3}", SPRAYER),
    (r"fendt", r"^1[01]\d{2}\s*(vario\s*)?mt|^9\d{2}|^1[01]\d{2}|^7\d{2}", ROW_CROP),
    (r"fendt", r"ideal", COMBINE),
    (r"gleaner", r".*", COMBINE),
    (r"massey", r"^8[67]\d{2}", ROW_CROP),
    (r"versatile", r"deltatrack|^[4-6]\d{2}$", FOUR_WD),
    (r"claas", r"lexion|trion", COMBINE),
    # --- Specialists -----------------------------------------------------
    (r"hagie", r".*", SPRAYER),
    (r"apache", r".*", SPRAYER),
    (r"kinze", r"^(3[0-9]{3}|4[0-9]{3}|5[0-9]{3}|true\s*speed)", PLANTER),
    (r"kinze", r"^1[0-9]{3}$|^[89]50$|^1[0-9]{3}\s*grain", GRAIN_CART),
    (r"great\s*plains|horsch|precision\s*planting", r".*", PLANTER),
    (r"brent|j\s*&\s*m|unverferth|elmer|parker", r".*", GRAIN_CART),
    (r"geringhoff|macdon|drago|capello|oxbo", r".*", HEADER),
]

_COMPILED = [(re.compile(mk, re.I), re.compile(md, re.I), cat) for mk, md, cat in _RULES]


def _clean_model(model: str) -> str:
    return " ".join(str(model).replace("-", " ").split()).strip()


def classify(make: str, model: str) -> str:
    """Return a category from ``CATEGORIES`` or ``OTHER``."""
    mk, md = str(make or "").strip(), _clean_model(model or "")
    if not mk or not md:
        return OTHER
    for make_re, model_re, cat in _COMPILED:
        if make_re.search(mk) and model_re.search(md):
            return cat
    return OTHER


def normalize_category(text: str) -> str:
    """Map free-text category labels ("4wd", "Tractors - 300+ HP") to ours."""
    t = str(text or "").lower()
    if not t:
        return OTHER
    if any(k in t for k in ("4wd", "4 wd", "four wheel", "articulated", "quad track", "quadtrac")):
        return FOUR_WD
    if "combine" in t and ("head" in t or "platform" in t or "draper" in t or "corn head" in t):
        return HEADER
    if "header" in t or "corn head" in t or "draper" in t:
        return HEADER
    if "combine" in t:
        return COMBINE
    if "planter" in t:
        return PLANTER
    if "sprayer" in t:
        return SPRAYER
    if "grain cart" in t or "cart" in t:
        return GRAIN_CART
    if "tractor" in t:
        return ROW_CROP
    for c in CATEGORIES:
        if c.lower() == t:
            return c
    return OTHER
