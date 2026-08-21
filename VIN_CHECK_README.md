# VIN Checker (`vin_check.py`)

Ghost-listing triage for sourcing runs.

## The problem it solves

A sourcing sweep (Want.it, FSBO, any buyer want) comes back with a pile of
leads pulled from dealer sites, aggregator feeds, and search-engine summaries.
A large share of those are **ghost listings**.

The mechanism is usually not a person deciding to lie. Dealer website platforms
auto-generate an SEO landing page for every year × model × trim permutation the
dealer *could* stock — whether or not one unit is on the ground. When the page
has nothing, it says "0 results, here are some other vehicles you may be
interested in," and search engines scrape that fallback block as if those units
matched the search. You call, a bot or a BDC rep answers, and the truck was
never there.

This tool tells you which leads are real machines and which are noise, before
anybody spends a day on the phone.

## What it checks

1. **Check digit** — position 9 of a VIN is an arithmetic checksum over the
   other sixteen characters (ISO 3779). A number someone invented fails this
   roughly nine times out of ten. A pass means the VIN is genuinely
   well-formed; a failure is near-proof of fabrication or a transcription
   error.
2. **Structure** — world manufacturer identifier, model year, assembly plant,
   and the sequential build number. Real inventory spreads naturally across a
   model-year run; pattern-generated VINs tend to cluster.
3. **Verification URLs** — the manufacturer window sticker (Monroney label) and
   the NHTSA vPIC decoder.

**The window sticker is the one that ends the argument.** It is served by the
manufacturer, not the dealer, and it only exists if the factory actually built
that unit. It also lists the real option codes — which is how you confirm a
package like Ford's Platinum Plus (773A) instead of taking a listing's word for
it. No dealer, bot, or AI-generated photo can fake it.

## What it does not do

- **No network calls.** The tool is offline and deterministic — it hands you
  URLs to open rather than fetching them. That keeps it testable, keeps it
  working behind restrictive network policies, and keeps a sourcing run from
  hammering third-party services.
- **It cannot tell you the unit is on that lot today.** A valid VIN plus a
  window sticker proves the machine was *built*. Confirming it is *present*
  still takes a VIN from the seller up front and a timestamped photo or
  walkaround video.

Anyone who will not hand over a VIN for a unit they claim is on the ground does
not have the unit. That is the whole rule.

## Usage

```bash
# VINs as arguments
python3 vin_check.py 1FT8W4DM6TED77655 1FT8W4DM1TED70984

# one VIN per line; blank lines and '#' comments ignored
python3 vin_check.py --file candidates.txt

# straight out of a candidate-list CSV
python3 vin_check.py --csv candidates.csv --column VIN

# machine-readable, for piping into a report
python3 vin_check.py --csv candidates.csv --json > verified.json

# just the verification links, one per line
python3 vin_check.py --file candidates.txt --urls-only
```

No dependencies beyond the standard library.

### Exit codes

| Code | Meaning |
|------|---------|
| `0`  | every VIN checked out |
| `1`  | at least one VIN is invalid — something needs eyes |
| `2`  | bad input (no VINs given, missing file, missing CSV column) |

The nonzero-on-invalid contract is deliberate, so a sweep script can gate on it.

### Example

```
$ python3 vin_check.py 1FT8W4DM6TED77655 1FT8W4DM6TED77656

  [VALID]   1FT8W4DM6TED77655
            2026 · Kentucky Truck Plant, Louisville KY · build #D77655

  [INVALID] 1FT8W4DM6TED77656
            check digit mismatch: position 9 is '6', should be '8'
```

## Coverage notes

- The check-digit math is **make-agnostic** — it works on any VIN, including
  Class 8 trucks and titled ag equipment. The check digit is the load-bearing
  part of this tool and it is reliable everywhere.
- **Model year on heavy trucks is a hint, not an answer.** The year code
  repeats every 30 years, and the convention that breaks the tie (a letter at
  position 7 means 2010-or-later) is defined for *light* vehicles. Class 8
  tractors often carry a digit there regardless of year, so a late-model heavy
  truck can resolve 30 years early — a 2014 Peterbilt reading as 1984, for
  instance. Confirm the year of any Class 8 VIN against the NHTSA link before
  it goes in a report. Ford pickups, including the Super Duty line, follow the
  light-vehicle convention and decode correctly.
- The **plant table and window-sticker lookup are Ford/Lincoln-specific.**
  Non-Ford VINs still validate and decode, and still get an NHTSA link; they
  just do not get a sticker URL, because other manufacturers serve their labels
  differently. Unrecognized plant codes report as unknown rather than guessing
  — a wrong plant name in a sourcing report is worse than an honest blank.
- Serial-numbered equipment that predates VIN standardization (older ag and
  construction iron) will not validate. That is expected: those need a
  manufacturer serial lookup, not a VIN check.

## Tests

```bash
pytest tests/test_vin_check.py
```

The known-good fixtures are real 2026 Ford F-450 Super Duty VINs collected
during a Platinum Plus sourcing sweep, so the arithmetic has a live regression
net rather than only synthetic cases.
