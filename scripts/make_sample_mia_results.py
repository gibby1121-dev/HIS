#!/usr/bin/env python3
"""Write a SYNTHETIC Auction Summary Report in MIA's export layout.

Same layout as the TractorHouse/HiBid post-sale export the
post-sale-auction-recap skill reads: a "Details" sheet, data from row 6,
columns 0 ListingID, 1 Lot, 3 Year, 4 Manufacturer, 5 Model, 9 Auction Value,
10 Market Value, 12 Final price with buyer's premium, 14 Hammer.

The numbers are invented. They exist so the calibration path can be demoed
and tested; replace the folder's contents with real MIA exports.

    python3 scripts/make_sample_mia_results.py [OUT_DIR]
"""

import random
import sys
from pathlib import Path

import openpyxl

LOTS = [
    # make, model, year, sandhills auction estimate
    ("John Deere", "9RX 640", 2020, 352000), ("John Deere", "9RX 590", 2019, 298000),
    ("John Deere", "9R 540", 2018, 236000), ("Case IH", "Steiger 620 Quadtrac", 2019, 305000),
    ("John Deere", "9570R", 2014, 168000), ("Case IH", "Steiger 580", 2018, 252000),
    ("John Deere", "9RX 640", 2022, 455000), ("Case IH", "Quadtrac 540", 2017, 214000),
    ("John Deere", "8R 410", 2021, 318000), ("John Deere", "8370R", 2017, 176000),
    ("Case IH", "Magnum 380", 2020, 236000), ("John Deere", "8R 370", 2022, 312000),
    ("John Deere", "S780", 2020, 296000), ("John Deere", "S790", 2021, 372000),
    ("Case IH", "8250", 2020, 318000), ("John Deere", "S680", 2015, 128000),
    ("John Deere", "DB60", 2019, 158000), ("Kinze", "4905", 2020, 176000),
    ("John Deere", "1775NT", 2017, 86000), ("John Deere", "R4045", 2020, 268000),
    ("Hagie", "STS16", 2019, 214000), ("Case IH", "Patriot 4440", 2018, 156000),
    ("Kinze", "1300", 2019, 58000), ("Brent", "1596", 2018, 64000),
    ("John Deere", "9620RX", 2017, 228000), ("Case IH", "Steiger 500", 2016, 168000),
    ("John Deere", "8R 340", 2020, 248000), ("John Deere", "S770", 2021, 286000),
]
# Synthetic "truth": MIA hammer lands a bit above Sandhills on planters and
# 4WD, a bit below on sprayers.
BIAS = {"DB60": 1.08, "4905": 1.10, "1775NT": 1.06, "R4045": 0.94, "STS16": 0.93,
        "Patriot 4440": 0.95}


def main(out_dir: str = "sample/mia_results") -> Path:
    random.seed(20260930)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Details"
    for _ in range(5):
        ws.append(["SYNTHETIC SAMPLE: not real sale data"])
    for i, (mk, md, yr, est) in enumerate(LOTS, start=1):
        bias = BIAS.get(md, 1.03)
        hammer = round(est * bias * random.uniform(0.92, 1.08), -2)
        final = hammer + min(hammer * 0.10, 2500)  # 10% buyer's premium capped at $2,500
        row = [f"L{i:04d}", i, None, yr, mk, md, None, None, None, est,
               round(est * 1.3, -3), None, final, None, hammer]
        ws.append(row)
    wb.create_sheet("Summary")
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / "Auction Summary Report - SYNTHETIC SAMPLE.xlsx"
    wb.save(path)
    return path


if __name__ == "__main__":
    print(main(*sys.argv[1:]))
