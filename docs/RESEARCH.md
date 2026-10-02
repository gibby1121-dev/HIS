# Trade-In Check: research basis

Research done 2026-10-02 for the Trade-In Check. This sandbox's network policy
blocked direct fetches of equipment, publisher and IRS sites, so **every figure
below was read through search-engine excerpts of the cited page, not the page
itself.** "Primary" means the URL is the original source (an OEM, Sandhills,
the IRS, a statute, a state revenue department, or MIA itself). Open the
primary links before quoting any of these externally.

## 1. How the trade-in squeeze works

| Finding | Source | Confidence |
|---|---|---|
| Dealers over-value trades. The new unit's margin goes up and the used unit's margin goes down. "The longer the expected time in inventory… the smaller the required trade-in allowance." | [Farm Equipment: causes of low gross margins](https://www.farm-equipment.com/articles/10245-sales-metrics-to-monitor-causes-of-low-gross-margins) | Secondary (dealer trade press) |
| A dealer books a trade at actual cash value (ACV). Any allowance above ACV is taken out of the new unit's gross. | [Dealer glossary](https://www.dealerint.com/glossary/trade-in-allowance) | Secondary (auto-dealer source, same mechanics) |
| Dealer value tiers, from IronGuides: Trade Premium/Rough → Wholesale ("orderly… dealer-to-dealer") → Forecast Wholesale ("forced liquidation… auction") → Resale Cash ("dealer expected selling price") → Retail Advertised. | [IronGuides features guide](https://ironsolutions.com/wp-content/uploads/2026/03/IronGuides-FeaturesGuide.pdf) | Primary |
| Used-equipment gross margin target is about 8% × 2 turns. Actual industry used gross margin was 1.6–5.1% in 2012–2016. | [Farm Equipment benchmarks](https://www.farm-equipment.com/articles/13638-how-dealers-are-measuring-up) | Secondary; the data is dated |
| OEM programs offer a cash discount **or** a low rate, not both (e.g. Case IH: "Up to $X Cash or 0% for 60 Months"). | [Case IH offers](https://www.caseih.com/en-us/unitedstates/tools-resources/special-offers) | Primary |
| AgDirect lets an operator take the OEM cash discount and still finance. | [AgDirect](https://www.fcsamerica.com/financing/agdirect-equipment-financing) | Primary |
| Activations on an integrated John Deere StarFire receiver can't be moved to another receiver. G5 licenses can be transferred through Operations Center: deactivate on one machine, reactivate on the new one. Precision Upgrades are subscription-based from model year 2024. | [AHW](https://www.ahwllc.com/blog/important-information-about-starfire-receivers--33476), [Koenig](https://support.koenigequipment.com/transferring-your-g5-advanced-license-what-you-need-to-know), [AgWeb](https://www.agweb.com/news/machinery/new-machinery/john-deere-details-precision-upgrades-2024) | Secondary |

**Not found:** published cash-in-lieu amounts for large-ag OEM programs, reconditioning reserve dollar figures, and any published dealer policy on quoting a no-trade price.

## 2. Market, 2026

| Claim in the product brief | Verified? | Detail |
|---|---|---|
| Used high-HP tractor inventory −16.75% Y/Y (July 2026) | **Yes** | Sandhills defines "high-HP" as **100 HP and up**. Inventory has fallen for 14 straight months. Auction values +2.97% Y/Y; asking prices sit 33% above auction. [PR Newswire](https://www.prnewswire.com/news-releases/sandhills-market-reports-show-continued-inventory-declines-across-used-equipment-and-truck-markets-302818473.html) |
| Planter auction values +15.3% Y/Y (Aug 2026) | **Yes** | +5.1% M/M. Asking prices are up only 6.4% Y/Y. [TractorHouse/Sandhills](https://www.tractorhouse.com/blog/sandhills-news/2026/09/used-farm-equipment-inventory-levels-continue-to-decline-as-auction-values-see-modest-increases) |
| 33% of listed sprayers are aged | **Stale and narrower than stated** | The figure is Tractor Zoom's **December 2025** snapshot of self-propelled sprayers, where "aged" means **listed 360+ days**. By June 2026, aged sprayer inventory was **−27% Y/Y**. Don't present 33% as current. [Tractor Zoom](https://www.tractorzoompro.com/blog/june-2026-equipment-market-update-falling-supply-uneven-strength) |
| 4WD is price-elastic | **Qualitative only** | Tractor Zoom calls 4WD "the category most exposed to price sensitive buyers pulling back". There is no measured elasticity, and Sandhills publishes no separate 4WD series. |

**Asking vs. auction ("EVI spread").** Sandhills asking prices ran **31–40% above auction values** for 100+ HP tractors and combines through 2026. This is why the engine never values a trade from listings.

## 3. Seller economics

| Finding | Source | Confidence |
|---|---|---|
| Mid-Iowa: "When your items sell you are charged 3% to 6%. The higher the value, the lower the rate… All advertising is paid for by Mid-Iowa… no fees if the asset doesn't sell." Seller controls the price (reserves). | [MIA: our company](https://www.midiowaauctioncompany.com/our-company.htm) | Primary; **bracket breakpoints not published** |
| Buyer's premiums vary widely. Ritchie Bros: flat $4,125 above $75k. BigIron: 10%, with caps of $500–$2,500 on some sales and reportedly uncapped on others. Steffes: 10%, max $1,000. | rbauction.com buyer fees; bigiron.com sale pages; Steffes terms | Primary, via search excerpts |
| Purple Wave's "contract price" = winning bid + buyer's premium. | [Purple Wave terms](https://www.purplewave.com/auction/legal/terms) | Primary |
| Whether aggregators (Machinery Pete, Tractor Zoom, AuctionValues) include the buyer's premium is undocumented. The engine therefore requires every comp to declare its price basis. | none found | Not verified |
| Settlement: Purple Wave ≤15 business days; Ritchie Bros ≤21 days. | Seller terms pages | Primary, via search excerpts |
| Farm loans >$100k averaged just under 7% in Q2 2026. This is the default operator borrowing rate. | [KC Fed](https://www.kansascityfed.org/center-for-agriculture-and-the-economy/agricultural-finance/new-farm-loan-originations-ease-slightly/) | Primary |

**Location discrepancy to resolve.** Listings place Mid-Iowa Auction in State Center / Marshalltown, IA. The `fsbo` skill's default radius center is Adel, IA.

## 4. Tax (facts for a CPA, not advice)

| Finding | Source | Confidence |
|---|---|---|
| Since TCJA, §1031 covers real property only. A machinery trade is a sale plus a purchase: §1245 recapture on Form 4797, and the new unit's basis is the full price. | [IRS Pub 225](https://www.irs.gov/publications/p225), [CALT](https://www.calt.iastate.edu/post/how-does-new-tax-law-act-impact-equipment-trades) | Primary/secondary |
| §1245 gain on business machinery isn't self-employment income (IRC §1402(a)(3)(C)). So an over-allowance that inflates both recapture and new-unit basis lowers SE tax. That's an issue for the CPA, not the product. | [26 USC 1402](https://codes.findlaw.com/us/title-26-internal-revenue-code/26-usc-sect-1402/) | Primary (rule); the over-allowance analysis is ours |
| OBBBA: 100% bonus depreciation for property acquired and placed in service after 2025-01-19. §179 limit for 2026 reported at $2.56M. | [IRS Notice 2026-11](https://www.irs.gov/pub/irs-drop/n-26-11.pdf) | Primary (bonus); secondary (§179) |
| §453(i): recapture is recognized in the year of sale, even on an installment sale. | 26 USC 453(i) | Primary |
| Ag machinery is sales-tax exempt in IA, IL, NE, MN, MO, WI, KS and IN. **South Dakota** charges a farm-machinery excise on the **cash difference after trade-in** (SDCL 10-46E-1, 4.5% statutory; whether the 2023 rate cut applies wasn't verified). So in SD, trading saves about 4.5% of the trade's value. | State revenue pages | Primary; SD rate not verified |
