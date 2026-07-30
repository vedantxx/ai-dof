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

# Portfolio size is DERIVED from the ledger, not assumed -- see treasury.ledger.
# It was hardcoded at $9.0M, which exceeded the group's entire cash balance
# ($6.14M at 30 Jun 2026) and so could not have existed. Every breach on the page
# is sized off this figure, so getting it wrong inflated all three.
OPENING_CASH = 12_000_000.0   # mirrors streamlit_app.OPENING["cash"]; a test ties them
BUFFER_MONTHS = 2             # months of operating cash held back before investing

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
# Group revenue growth per unit of the freight index. The index is the MODELLED
# quantity and is derived from observed revenue over the ledger window, so this
# sets how strongly the two are tied. Raise it and the freight coefficient falls.
REVENUE_FREIGHT_BETA = 1.30
FREIGHT_NOISE = 0.008      # measurement noise on the derived index
OPERATING_IDIO = 0.018     # idiosyncratic monthly revenue noise, pre-history
OPERATING_FACTOR_DESCRIPTIONS = {
    "freight_rate_index": "Spot truckload rate index, month-on-month change.",
    "diesel_price": "Diesel price, month-on-month change (a cost input).",
    "industrial_production": "Industrial production index, month-on-month change.",
}
OPERATING_FACTOR_LABELS = {
    "freight_rate_index": "Freight rate index",
    "diesel_price": "Diesel price",
    "industrial_production": "Industrial production",
}

# --------------------------------------------------------------------------- #
#  Theming
# --------------------------------------------------------------------------- #
# The tearsheet's stylesheet declares the dark values in :root. Light mode is
# applied by overriding those same variables, so there is one stylesheet rather
# than two that can drift apart.
THEMES = ("dark", "light")
DEFAULT_THEME = "dark"

LIGHT_VARS = {
    "--bg": "#f6f8fb",
    "--bg-2": "#ffffff",
    "--panel": "rgba(255, 255, 255, 0.92)",
    "--panel-border": "rgba(31, 56, 100, 0.14)",
    "--text": "#14203a",
    "--muted": "#5b6b85",
    "--muted-2": "#7b8AA3",
    "--accent": "#0F6B4F",      # the app's existing teal reads on white
    "--accent-2": "#1F3864",    # and its navy
    "--danger": "#B3261E",
    "--warn": "#B45309",
}

# Chart colours per theme. The dark set is the reference project's; the light set
# is the palette the other four pages already use, so the app reads as one system.
CHART_COLORS = {
    "dark": dict(accent="#4ade80", accent_2="#60a5fa", danger="#f87171",
                 warn="#fbbf24", muted="#94a3b8", title="#e2e8f0",
                 grid="rgba(148,163,184,0.12)", template="plotly_dark",
                 factors={"Mkt-RF": "#60a5fa", "SMB": "#4ade80", "HML": "#fbbf24",
                          "RMW": "#c084fc", "CMA": "#f472b6"}),
    "light": dict(accent="#0F6B4F", accent_2="#1F3864", danger="#B3261E",
                  warn="#B45309", muted="#5b6b85", title="#14203a",
                  grid="rgba(31,56,100,0.10)", template="plotly_white",
                  factors={"Mkt-RF": "#1F3864", "SMB": "#0F6B4F", "HML": "#B45309",
                           "RMW": "#6D28D9", "CMA": "#BE185D"}),
}
