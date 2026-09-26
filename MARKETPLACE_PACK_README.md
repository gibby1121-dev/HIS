# Marketplace post packs (List.it)

`marketplace_pack.py` turns a TractorHouse inventory export plus the crew's
own lot photos into ready-to-post Facebook Marketplace packs.

## Rules

- **Photos come from the crew's intake folder, never from TractorHouse.**
  TractorHouse images carry Sandhills watermarks. Do not download, crop, or
  remove the watermarks on them.
- **A person clicks Publish.** Meta has no Marketplace listing API, and
  scripted posting breaks its terms. The packs stop at "ready to publish".
- **Take listings down when a unit sells.** A re-run flags these as `TAKE_DOWN`.

## Photo intake convention

One folder per sale, with files named `<StockNumber>_<NN>.jpg`, for example
`SN1001_01.jpg` or `LOT042_03.jpg`. `01` is the cover shot. Matching ignores
case, a `LOT` prefix, and leading zeros, so `LOT042_01.jpg` and `lot42_01.jpg`
both match stock `LOT042`. Files that don't follow the pattern are ignored.

## Run

```bash
python3 marketplace_pack.py --inventory ExportInventory.csv --photos Photos/ \
    --out marketplace_queue --phone "515-555-0100" --location "Ames, IA" \
    --sale-note "Sells at Mid-Iowa online auction closing Oct 14"
```

Required fields in the export: stock number, year, make, model. Price, hours,
category, serial, description, and listing URL are used when present. Common
Sandhills header spellings are accepted (`Stock #`, `Stock Number`,
`StockNumber` ...). If a new spelling shows up, the run stops, lists the
columns it found, and you add the spelling to `COLUMN_ALIASES`.

## Output (`marketplace_queue/`, generated and git-ignored)

- `<StockNumber>/listing.txt`: title, price, category, condition, and a
  description ready to paste.
- `<StockNumber>/01.jpg ...`: up to 10 photos, in order.
- `queue.csv`: the posting tracker. Fill in `MarketplaceURL`, `PostedDate`,
  and `TakenDownDate` as you go. Re-runs keep those columns.

| Status | Meaning |
|---|---|
| `READY` | Pack built; ready to post |
| `NEEDS_PRICE` | Pack built, but no asking price. Kent sets one before posting |
| `NEEDS_PHOTOS` | No intake photos found; no pack built |
| `POSTED` | Marketplace URL logged |
| `TAKE_DOWN` | Posted, but no longer in inventory. Delete the Marketplace listing |
| `TAKEN_DOWN` | Take-down logged |
