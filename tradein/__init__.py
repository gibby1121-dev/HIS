"""Trade Desk — trade-in decision engine for owner-sellers of large row-crop iron.

Modules:
    categories  model-family -> equipment category for row-crop machines
    comps       comparable-sale loading and price-basis normalization
    mia         Mid-Iowa Auction Summary Report + Sandhills ExportFleet loaders,
                and calibration of Sandhills auction estimates to MIA hammer prices
    valuation   open-market value of the trade unit (hammer basis)
    deal        dealer-quote decomposition: trade over-allowance, financing bundle
    routes      net-to-operator for trade vs. consign vs. sell, dealer-side economics
    tax         CPA-ready facts (never advice)
    intake      Claude extraction of a photographed / PDF dealer quote
    report      operator report and internal MIA desk sheet
"""

__version__ = "2.0.0"
