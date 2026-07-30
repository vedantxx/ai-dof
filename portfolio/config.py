"""Every tunable constant for the portfolio tearsheet.

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
# NOTE: data/ is .gitignored (superseded full-detail dataset). Portfolio data
# lives beside the canonical compact ledger so it is actually committed.
DATA_DIR = REPO_ROOT / "data_compact" / "portfolio"
LEDGER_DIR = REPO_ROOT / "data_compact" / "csv"

FACTORS_CSV = DATA_DIR / "ff_factors_daily.csv"
RETURNS_CSV = DATA_DIR / "portfolio_returns_daily.csv"
PRICES_CSV = DATA_DIR / "holdings_prices_daily.csv"
ARTIFACT_HTML = REPO_ROOT / "portfolio-tearsheet-jul2026.html"

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
FEE_ANNUAL = 0.0045           # 45bp holding-company management charge

# Cost basis of the four stakes, mirroring streamlit_app.OPENING["capital"] --
# what the members actually put in. A test ties the two together.
OPENING_CAPITAL = 24_300_000.0

# Daily standard deviations. Mkt-RF ~16%/yr; style factors are long/short and
# therefore much less volatile.
FACTOR_VOL = {
    "Mkt-RF": 0.0101,
    "SMB": 0.0050,
    "HML": 0.0050,
    "RMW": 0.0040,
    "CMA": 0.0040,
}

# Annualized risk premia earned by each factor over the sample.
FACTOR_PREMIUM = {
    "Mkt-RF": 0.080,
    "SMB": 0.030,
    "HML": 0.045,
    "RMW": 0.030,
    "CMA": 0.010,
}

# --------------------------------------------------------------------------- #
#  The portfolio: MHG's four operating stakes
# --------------------------------------------------------------------------- #
# Meridian Holdings Group is the investor; these are the positions. Ownership,
# share counts and prices are MODELLED -- the ledger records the companies'
# trading, not a cap table. Opening weights are their share of group revenue,
# which is why MLG opens above the 40% concentration limit.
#
# Each holding re-rates at REGIME_SPLIT: the portfolio drifts from defensive
# into high-beta small-cap growth without anyone rebalancing. `alpha` is TRUE
# annualized alpha -- these are private stakes in businesses the holdco actively
# operates, so genuine alpha is the premise of the strategy.
HOLDINGS = {
    "MLG": dict(
        name="Meridian Logistics LLC", business="Freight brokerage & last mile",
        ownership=1.00, weight=0.407, price=48.00, alpha=0.095,
        fy25=dict(mkt=0.75, smb=-0.10, hml=0.40, rmw=0.30, cma=0.05, idio=0.070),
        fy26=dict(mkt=1.15, smb=0.45, hml=-0.25, rmw=-0.15, cma=-0.10, idio=0.120),
    ),
    "CFS": dict(
        name="Cascade Freight Systems Inc", business="Asset-based trucking",
        ownership=0.80, weight=0.232, price=32.50, alpha=0.115,
        fy25=dict(mkt=1.05, smb=0.10, hml=0.55, rmw=0.40, cma=0.05, idio=0.095),
        fy26=dict(mkt=1.60, smb=0.75, hml=-0.35, rmw=-0.25, cma=-0.10, idio=0.150),
    ),
    "NWC": dict(
        name="Northwind Cargo B.V.", business="EU forwarding, customs & TMS software",
        ownership=0.75, weight=0.222, price=61.25, alpha=0.120,
        fy25=dict(mkt=0.70, smb=-0.25, hml=0.35, rmw=0.35, cma=0.05, idio=0.080),
        fy26=dict(mkt=1.10, smb=0.35, hml=-0.30, rmw=-0.20, cma=-0.10, idio=0.130),
    ),
    "APX": dict(
        name="Apex Warehousing LLC", business="Warehousing & fulfillment (3PL)",
        ownership=0.60, weight=0.139, price=27.80, alpha=0.080,
        fy25=dict(mkt=0.65, smb=-0.20, hml=0.45, rmw=0.35, cma=0.05, idio=0.075),
        fy26=dict(mkt=1.05, smb=0.40, hml=-0.30, rmw=-0.20, cma=-0.10, idio=0.125),
    ),
}
TICKERS = list(HOLDINGS)


def regime_of(timestamp) -> str:
    """Which loading set applies on a given date."""
    import pandas as pd
    return "fy25" if pd.Timestamp(timestamp) < pd.Timestamp(REGIME_SPLIT) else "fy26"


def expected_loading(regime: str, factor: str) -> float:
    """Opening-weight average loading -- what a regression should recover.

    Derived from HOLDINGS rather than stated separately, so the tests cannot
    drift away from the generator.
    """
    return sum(h["weight"] * h[regime][factor] for h in HOLDINGS.values())


# A six-week market selloff. Applied to the MARKET factor, not to any holding's
# residual: the drawdown must be something the portfolio amplified through its
# drifted beta, not an unexplained drag that would land in the regression
# intercept and corrupt the alpha figure.
SHOCK_START = "2026-02-02"
SHOCK_END = "2026-03-13"
SHOCK_DAILY = -0.0038         # daily excess-return drag on Mkt-RF

# --------------------------------------------------------------------------- #
#  Investment policy — what the Director of Finance is accountable for
# --------------------------------------------------------------------------- #
POLICY = {
    "max_beta": 1.00,         # rolling market beta ceiling
    "max_drawdown": 0.10,     # as a positive magnitude
    "max_weight": 0.40,       # single-position concentration ceiling
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
