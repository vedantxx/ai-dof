"""Every tunable constant for the treasury tearsheet.

Kept in one module so the data generator and the analytics layer cannot drift
apart: the generator bakes these parameters into the CSVs, and the tests assert
the regressions recover them.

All figures here are MODELLED. Meridian Holdings Group is fictional.
"""
from __future__ import annotations

from pathlib import Path

# --------------------------------------------------------------------------- #
#  Paths
# --------------------------------------------------------------------------- #
REPO_ROOT = Path(__file__).resolve().parent.parent
# NOTE: data/ is .gitignored (superseded full-detail dataset). Treasury data
# lives beside the canonical compact ledger so it is actually committed.
DATA_DIR = REPO_ROOT / "data_compact" / "treasury"
LEDGER_DIR = REPO_ROOT / "data_compact" / "csv"

FACTORS_CSV = DATA_DIR / "ff_factors_daily.csv"
RETURNS_CSV = DATA_DIR / "treasury_portfolio_returns.csv"
OPERATING_CSV = DATA_DIR / "operating_factors_monthly.csv"
ARTIFACT_HTML = REPO_ROOT / "treasury-tearsheet-jul2026.html"

# --------------------------------------------------------------------------- #
#  Calendar and conventions
# --------------------------------------------------------------------------- #
SEED = 20260729
TRADING_DAYS_PER_YEAR = 252
START = "2024-07-01"          # aligned to the ledger's 24 months
END = "2026-06-30"
REGIME_SPLIT = "2026-01-01"   # the drift begins here

DEFAULT_WINDOW = 63           # ~one quarter, the reference's default
ALLOWED_WINDOWS = (21, 63, 126)

# --------------------------------------------------------------------------- #
#  Market model
# --------------------------------------------------------------------------- #
RF_ANNUAL = 0.043             # risk-free rate, constant over the sample
FEE_ANNUAL = 0.0045           # 45bp management fee, netted out of the series
PORTFOLIO_NOTIONAL = 9_000_000.0   # MODELLED: group cash under management

# Daily standard deviations. Mkt-RF ~16%/yr; style factors are long/short and
# therefore much less volatile.
FACTOR_VOL = {
    "Mkt-RF": 0.0101,
    "SMB": 0.0050,
    "HML": 0.0050,
    "RMW": 0.0040,
    "CMA": 0.0040,
}

# Annualized risk premia earned by each factor over the sample. These are what
# CAPM cannot see, and therefore what it misattributes to alpha.
FACTOR_PREMIUM = {
    "Mkt-RF": 0.080,
    "SMB": 0.030,
    "HML": 0.045,
    "RMW": 0.030,
    "CMA": 0.010,
}

# Two regimes. FY2025 is defensive and value-tilted; FY2026 rotates into
# high-beta small-cap growth. `alpha` is TRUE annualized alpha, deliberately
# tiny -- the ~+2% that CAPM will report is factor premia, not skill.
REGIMES = {
    "FY2025": dict(mkt=0.85, smb=-0.15, hml=0.45, rmw=0.35, cma=0.05,
                   idio=0.060, alpha=0.0025),
    "FY2026": dict(mkt=1.31, smb=0.55, hml=-0.30, rmw=-0.20, cma=-0.10,
                   idio=0.110, alpha=-0.0050),
}

# A six-week market selloff. Applied to the MARKET factor, not to the portfolio
# directly: the drawdown must be something the portfolio amplified through its
# drifted beta, not an unexplained idiosyncratic drag. Putting it in the
# portfolio's residual instead would land the whole episode in the regression
# intercept and destroy the alpha finding.
SHOCK_START = "2026-02-02"
SHOCK_END = "2026-03-13"
SHOCK_DAILY = -0.0038         # daily excess-return drag on Mkt-RF

# --------------------------------------------------------------------------- #
#  Investment policy — what the Director of Finance is accountable for
# --------------------------------------------------------------------------- #
POLICY = {
    "max_beta": 1.00,         # rolling market beta ceiling
    "max_drawdown": 0.10,     # as a positive magnitude
    "min_net_alpha": 0.0,     # FF5 alpha, net of fees
    "market_stress": 0.20,    # market decline used to size the beta breach
}

# --------------------------------------------------------------------------- #
#  Factor metadata
# --------------------------------------------------------------------------- #
FF5_FACTORS = ["Mkt-RF", "SMB", "HML", "RMW", "CMA"]
FF3_FACTORS = ["Mkt-RF", "SMB", "HML"]

FACTOR_DESCRIPTIONS = {
    "Mkt-RF": "Market excess return (the equity risk premium).",
    "SMB": "Small Minus Big: small-cap minus large-cap returns (size).",
    "HML": "High Minus Low: value minus growth returns (value).",
    "RMW": "Robust Minus Weak: high minus low profitability (profitability).",
    "CMA": "Conservative Minus Aggressive: low minus high investment (investment).",
    "RF": "Daily risk-free rate.",
}

# --------------------------------------------------------------------------- #
#  Operating factor model (section 2)
# --------------------------------------------------------------------------- #
OPERATING_START = "2021-07"   # 36 months of MODELLED pre-history
LEDGER_START = "2024-07"      # from here the revenue is ACTUAL
LEDGER_END = "2026-06"
# MHG is the holding company and books no invoice revenue.
OPERATING_ENTITIES = ["MLG", "CFS", "NWC", "APX"]
OPERATING_FACTORS = ["freight_rate_index", "diesel_price", "industrial_production"]
OPERATING_FACTOR_DESCRIPTIONS = {
    "freight_rate_index": "Spot truckload rate index, month-on-month change.",
    "diesel_price": "Diesel price, month-on-month change (a cost input).",
    "industrial_production": "Industrial production index, month-on-month change.",
}
