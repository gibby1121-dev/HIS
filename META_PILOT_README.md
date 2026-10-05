# HIS Meta pilot (Phase 1)

`meta_pilot.py` runs the first phase of the HIS seller platform on Meta. Each
pilot unit gets:

- **A unit landing page** on an HIS-owned domain, carrying the Meta Pixel.
- **A Meta catalog row**, so catalog ads can retarget people who looked at it.
- **A Gavel Report**: a private one-page report for the seller covering
  - who saw the unit and how long they watched
  - who saved it and who asked about it
  - where the asking price sits against market
  - a suggested next move

  The seller makes the call, and the report records it.

**Phase 1 goal:** prove the loop on 3–5 units. Phase 1 is done when one seller
makes a pricing decision from their Gavel Report *and* one owner inquiry comes
in through HIS's Meta surfaces.

## House rules (enforced by the tool)

- **Crew photos only.** Photos come from the intake folder, never from
  TractorHouse or Sandhills. A unit with no crew photos gets no page and no
  catalog row.
- **Truth standard.** Every number comes from the export, the pilot sheet, or
  Meta. Missing values show as "not set" or "not tracked". Nothing is filled
  in.
- **Epiphany Standard.** HIS-written copy never uses *auction, auctioneer,
  consignor, consignment,* or *salesman*. If a seller's description uses them,
  the run prints a `WARNING` with the words. Rewrite the description in
  Sandhills before the page goes live. The tool does not edit it.

## One-time Meta setup (Kent, about 30 minutes)

1. **Secure first.** In Meta Business Suite, create a separate **Heartland Iron
   Solutions business portfolio**. Do not reuse MIA's assets or the ad account
   in Kent's name. This matters because the Meta account was compromised in
   May. Then:
   - Turn on two-factor authentication for every admin, and keep at least two
     admins.
   - Add a dedicated payment method with an account spending limit.
2. **Page and Instagram.**
   - Create the **Heartland Iron Solutions** page and link an Instagram
     account.
   - Set the page button to **Send Message**.
   - Copy the page's `m.me/...` link for `--messenger-url`.
3. **Pixel (dataset).** In Events Manager, create a dataset (Pixel) and note
   its id for `--pixel-id`.
4. **Domain.** Host the pages on a domain HIS controls, over https.
   - Verify the domain in Business Settings (Brand safety → Domains).
   - Any static host works: GitHub Pages, Netlify, or Cloudflare Pages.
5. **Catalog.** In Commerce Manager, create a catalog with the type set to
   products. Add a **data feed** that points at the uploaded
   `meta_catalog.csv`, and connect the catalog to the Pixel dataset.
6. **Ad sets: one per unit.** Name every ad set with the unit's stock number,
   for example `HIS | SN2001 | owners 150mi`. The report finds each unit's
   numbers by that stock number.
   - Start each unit at about $5–10 a day.
   - Use Click-to-Message or Instant Forms for the response action.

## Pilot sheet (`pilot_units.csv`)

| Column | Required | Meaning |
|---|---|---|
| `StockNumber` | yes | Must match the Sandhills export |
| `seller_name` | yes | Name shown on the Gavel Report |
| `start_date` | yes | Day the unit went live on Meta (YYYY-MM-DD) |
| `market_value` | no | HIS's valuation of the unit. Without it, price position shows as "unknown" |
| `ladder` | no | The seller's pre-committed price steps, highest first, separated by `;` (e.g. `289000;279000;269000`) |
| `decision`, `decision_date` | no | The seller's call after each report. Shown on the next report |

## Weekly run

```bash
# 1. Pages, then upload site/ to the HIS domain
python3 meta_pilot.py pages --inventory ExportInventory.csv --pilot pilot_units.csv \
    --photos Photos/ --pixel-id <DATASET_ID> --base-url https://<his-domain>/units \
    --phone "<number>" --messenger-url https://m.me/<page> --out site

# 2. Catalog feed (upload, or let the scheduled data feed pick it up)
python3 meta_pilot.py catalog --inventory ExportInventory.csv --pilot pilot_units.csv \
    --photos Photos/ --base-url https://<his-domain>/units --out meta_catalog.csv

# 3. Gavel Reports from an Ads Manager export
python3 meta_pilot.py report --inventory ExportInventory.csv --pilot pilot_units.csv \
    --ads ads_export.csv --out gavel_reports
```

Photo naming follows `marketplace_pack.py`: `<StockNumber>_<NN>.jpg`, where
`01` is the cover shot. Case, a `LOT` prefix, and leading zeros are ignored
when matching.

### Ads Manager export for the report

In Ads Manager, open the **Ad sets** tab and set the date range from launch to
today.

1. Choose **Customize columns** and add these columns:
   - Reach, Impressions, Amount spent, Link clicks
   - ThruPlays, Video average play time
   - Leads, Messaging conversations started
   - Website content views, Website adds to wishlist, Website contacts
2. Optionally, under **Breakdown → By Delivery → Region**, add the region
   breakdown. This fills in the "where the attention is coming from" section.
3. **Export** the table as a `.csv`.

Only *Ad set name*, *Reach* and *Impressions* are required. Any column you
leave out shows as "not tracked" on the report. If Meta renames a header, the
run stops and lists the columns it found. Add the new spelling to
`ADS_ALIASES` in `meta_pilot.py`.

### How the suggested move is picked

These checks run in order, and the first match decides the move.

| Situation | Suggested move |
|---|---|
| Any lead, message, or call/message click | Hold and work the conversations |
| Live under 7 days, or reached under 1,000 people | Hold: too early to call |
| Average watch time under 3 s | Reposition the creative (a video problem, not a price problem) |
| Asking price more than 10% over market value | Step down the ladder, naming the seller's committed next step |
| People saved the unit | Hold: buyers are watching |
| Otherwise | Widen the audience |

The thresholds are pilot starting points, not doctrine. They are constants
at the top of `meta_pilot.py`; tune them once the pilot has real numbers.

## Limits to know

- Meta does not say *who* viewed a unit. Names only come from people who
  message or submit a form.
- Marketplace has no listing API. Marketplace posting stays manual (see
  `marketplace_pack.py` on its own branch).
- Phase 1 pulls numbers from a manual export. Phase 2 replaces that export
  with a nightly Marketing API pull.

## Sample data

`sample/meta_pilot/` holds **synthetic** inputs used by the tests. They are
not real units, sellers, or Meta results.
