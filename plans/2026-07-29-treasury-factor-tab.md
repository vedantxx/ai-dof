# Treasury & Factor Analysis Tab — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a fifth page to the AI DOF Streamlit dashboard: a dark quant tearsheet for Meridian Holdings Group's treasury portfolio (CAPM, Fama-French 3/5-factor, rolling factor betas, performance and risk statistics, treasury-policy breaches) plus a factor model of the group's own operating revenue.

**Architecture:** Three strictly separated layers. `treasury/analytics.py` holds all math and imports nothing from the UI. `treasury/charts.py` turns results into Plotly HTML fragments. `treasury/render.py` fills ported Jinja2 templates and returns one self-contained HTML string, which `streamlit_app.py` embeds with `components.html()` and which is also written to disk as a committable artifact. Data is generated once by a deterministic script and committed.

**Tech Stack:** Python 3, pandas, numpy, statsmodels, plotly, jinja2, streamlit.

**Spec:** `specs/2026-07-29-treasury-factor-tab-design.md`. Read it before starting.

**Reference implementation:** Quant Guild Library, `2026 Video Lectures/130. Projects to Help you Become a Quant (Beginner)/01 - Quant Trader/01 - Intro - Trading Dashboard` at commit `043532e79`. This plan reproduces its structure deliberately. Where a function below closely follows the reference, that is intentional and noted.

## Global Constraints

- Python 3.11+. Existing deps: `streamlit>=1.30`, `pandas>=2.0`, `plotly>=5.18`. Add `statsmodels>=0.14`, `jinja2>=3.1`, `numpy>=1.24`.
- `treasury/analytics.py` MUST NOT import streamlit, jinja2, or plotly. `treasury/render.py` MUST NOT compute statistics. Enforced by a test.
- **Never write data files to `data/` or `docs/`** — `.gitignore` excludes both. Treasury data goes in `data_compact/treasury/`. Specs in `specs/`, plans in `plans/`.
- `TRADING_DAYS_PER_YEAR = 252` everywhere. Returns are simple daily returns as decimals.
- Generator seed is fixed at `SEED = 20260729`. Regenerating must produce byte-identical CSVs.
- All generated data is labelled MODELLED on the page and in the README. Actual ledger revenue is labelled as actual.
- Tests assert **acceptance bands**, never decimal-exact statistics.
- No CDN and no network at render time: Plotly JS inlined once, system font stacks only.
- Palette, verbatim from the reference: `--bg:#0a0e17`, `--bg-2:#0f1524`, `--panel:rgba(20,27,45,.72)`, `--panel-border:rgba(96,165,250,.14)`, `--text:#e2e8f0`, `--muted:#94a3b8`, `--muted-2:#64748b`, `--accent:#4ade80`, `--accent-2:#60a5fa`, `--danger:#f87171`, `--warn:#fbbf24`, `--radius:16px`.
- Money formatting on the page follows the existing app: `$1.23M`, `$456k`, `$789`.
- Commit after every task. Conventional prefixes (`feat:`, `test:`, `docs:`, `chore:`).

## File Structure

| File | Responsibility |
|---|---|
| `treasury/__init__.py` | Package marker, exports `run_full_analysis`. |
| `treasury/config.py` | Every tunable constant: dates, seed, regime loadings, factor vols and premia, fee, notional, policy limits. Single source of truth shared by generator and analytics. |
| `treasury/analytics.py` | Parsing, performance statistics, OLS engine, CAPM, Fama-French, rolling betas, policy checks, operating factor model, `run_full_analysis`. |
| `treasury/charts.py` | Seven Plotly builders returning HTML fragments. |
| `treasury/render.py` | Jinja2 environment, view-model assembly, formatting, HTML output. |
| `treasury/templates/base.html` | Ported shell: topbar, `.bg-grid`, footer. |
| `treasury/templates/tearsheet.html` | Ported `dashboard.html` plus the policy banner and section 2. |
| `treasury/static/css/style.css` | Ported stylesheet, rebranded. |
| `generate_treasury_data.py` | Deterministic generator, writes three CSVs, `--report` prints realized statistics. |
| `data_compact/treasury/*.csv` | Committed generated data. |
| `tests/test_treasury_analytics.py` | Math, calibration, layering. |
| `tests/test_treasury_render.py` | Rendering and artifact. |
| `streamlit_app.py` | New sidebar entry and page body only. |
| `README.md` | New section. |

Tasks 1–5 build bottom-up (config → data → math → judgment → operating model); 6–7 build presentation; 8 wires the app. Each task ends green and committed.

---

### Task 1: Package scaffold, config, and dependencies

**Files:**
- Create: `treasury/__init__.py`, `treasury/config.py`
- Create: `tests/__init__.py`, `tests/test_treasury_analytics.py`
- Modify: `requirements.txt`

**Interfaces:**
- Consumes: nothing.
- Produces: `treasury.config` module constants used by every later task — `SEED`, `START`, `END`, `TRADING_DAYS_PER_YEAR`, `RF_ANNUAL`, `FEE_ANNUAL`, `PORTFOLIO_NOTIONAL`, `REGIME_SPLIT`, `REGIMES`, `FACTOR_VOL`, `FACTOR_PREMIUM`, `SHOCK_START`, `SHOCK_END`, `SHOCK_DAILY`, `POLICY`, `DATA_DIR`, `FF5_FACTORS`, `FF3_FACTORS`, `FACTOR_DESCRIPTIONS`, `OPERATING_ENTITIES`, `OPERATING_START`.

- [ ] **Step 1: Write the failing test**

Create `tests/__init__.py` as an empty file, then `tests/test_treasury_analytics.py`:

```python
"""Tests for the treasury analytics layer."""
from __future__ import annotations

import pandas as pd
import pytest

from treasury import config as cfg


def test_config_exposes_calibration_constants():
    assert cfg.SEED == 20260729
    assert cfg.TRADING_DAYS_PER_YEAR == 252
    assert pd.Timestamp(cfg.START) < pd.Timestamp(cfg.REGIME_SPLIT) < pd.Timestamp(cfg.END)
    # Two regimes: the defensive first period and the drifted second period.
    assert set(cfg.REGIMES) == {"FY2025", "FY2026"}
    for name, r in cfg.REGIMES.items():
        assert set(r) == {"mkt", "smb", "hml", "rmw", "cma", "idio", "alpha"}
    # The planted drift: market beta rises through the policy limit.
    assert cfg.REGIMES["FY2025"]["mkt"] < cfg.POLICY["max_beta"] < cfg.REGIMES["FY2026"]["mkt"]


def test_config_policy_limits_are_the_spec_values():
    assert cfg.POLICY["max_beta"] == 1.00
    assert cfg.POLICY["max_drawdown"] == 0.10
    assert cfg.POLICY["min_net_alpha"] == 0.0


def test_data_dir_is_not_gitignored():
    # data/ and docs/ are excluded by .gitignore; treasury data must not land there.
    parts = cfg.DATA_DIR.parts
    assert "data_compact" in parts
    assert "docs" not in parts
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_treasury_analytics.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'treasury'`

- [ ] **Step 3: Write the implementation**

`treasury/__init__.py`:

```python
"""Treasury portfolio and factor analysis for the AI DOF Command Centre."""
```

`treasury/config.py`:

```python
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
    "FY2025": dict(mkt=0.85, smb=-0.15, hml=0.20, rmw=0.10, cma=0.05,
                   idio=0.060, alpha=0.0025),
    "FY2026": dict(mkt=1.31, smb=0.55, hml=-0.30, rmw=-0.20, cma=-0.10,
                   idio=0.110, alpha=-0.0050),
}

# A six-week shock that pushes maximum drawdown past the policy limit.
SHOCK_START = "2026-02-02"
SHOCK_END = "2026-03-13"
SHOCK_DAILY = -0.0035         # calibrated in Task 2; see the tuning loop

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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_treasury_analytics.py -v`
Expected: 3 passed

- [ ] **Step 5: Add dependencies**

Overwrite `requirements.txt`:

```
streamlit>=1.30
pandas>=2.0
plotly>=5.18
numpy>=1.24
statsmodels>=0.14
jinja2>=3.1
pytest>=8.0
```

Run: `python3 -m pip install -r requirements.txt`
Expected: statsmodels and pytest install successfully.

- [ ] **Step 6: Commit**

```bash
git add treasury/__init__.py treasury/config.py tests/__init__.py tests/test_treasury_analytics.py requirements.txt
git commit -m "feat: add treasury package scaffold and calibration config"
```

---

### Task 2: Factor panel and portfolio return generator

**Files:**
- Create: `generate_treasury_data.py`
- Create (generated): `data_compact/treasury/ff_factors_daily.csv`, `data_compact/treasury/treasury_portfolio_returns.csv`
- Test: `tests/test_treasury_data.py`

**Interfaces:**
- Consumes: `treasury.config` constants from Task 1.
- Produces: two CSVs and the functions `build_factor_panel() -> pd.DataFrame` (index `date`, columns `Mkt-RF, SMB, HML, RMW, CMA, RF`) and `build_portfolio_returns(panel) -> pd.DataFrame` (index `date`, columns `portfolio_return, SPY`). Task 3's tests read the CSVs; Task 5 adds a third generator function to this same file.

- [ ] **Step 1: Write the failing test**

Create `tests/test_treasury_data.py`:

```python
"""Tests for the generated treasury datasets.

These assert the FILE contract (schema, determinism, interchangeability with the
reference project's CSV) and calibration BANDS. Never assert decimal-exact
statistics: a test pinned to -14.2% breaks on any harmless generator change.
"""
from __future__ import annotations

import subprocess
import sys

import numpy as np
import pandas as pd
import pytest

from treasury import config as cfg

pytestmark = pytest.mark.skipif(
    not cfg.RETURNS_CSV.exists(),
    reason="run `python3 generate_treasury_data.py` first",
)


@pytest.fixture(scope="module")
def returns() -> pd.DataFrame:
    return pd.read_csv(cfg.RETURNS_CSV, parse_dates=["date"]).set_index("date")


@pytest.fixture(scope="module")
def panel() -> pd.DataFrame:
    return pd.read_csv(cfg.FACTORS_CSV, parse_dates=["date"]).set_index("date")


def test_returns_schema_matches_the_reference_project(returns):
    # Interchangeable with the Quant Guild sample_portfolio_returns.csv.
    assert list(returns.columns) == ["portfolio_return", "SPY"]
    assert returns.index.name == "date"


def test_index_is_business_days_including_holidays(returns):
    assert returns.index.dayofweek.max() <= 4, "weekends must not appear"
    # US holidays are NOT excluded -- the reference sample contains 2023-07-04.
    assert pd.Timestamp("2025-07-04") in returns.index
    assert pd.Timestamp("2025-12-25") in returns.index


def test_sample_spans_the_ledger_period(returns):
    assert returns.index.min() == pd.Timestamp(cfg.START)
    assert returns.index.max() <= pd.Timestamp(cfg.END)
    assert 500 <= len(returns) <= 540


def test_daily_magnitudes_are_plausible(returns):
    # Calibrated against the reference sample: SPY sd ~0.0098/day.
    spy_sd = returns["SPY"].std(ddof=1)
    assert 0.008 <= spy_sd <= 0.012
    port_sd = returns["portfolio_return"].std(ddof=1)
    assert 0.008 <= port_sd <= 0.018
    assert returns.abs().max().max() < 0.15, "no implausible single-day move"


def test_factor_panel_schema_and_alignment(panel, returns):
    assert list(panel.columns) == cfg.FF5_FACTORS + ["RF"]
    assert panel.index.equals(returns.index), "panel must align to the returns index"
    expected_rf = cfg.RF_ANNUAL / cfg.TRADING_DAYS_PER_YEAR
    assert np.allclose(panel["RF"], expected_rf)


def test_spy_is_the_market_factor_plus_rf(panel, returns):
    # The portfolio is built FROM the panel; if SPY were an unrelated series the
    # Fama-French loadings would be regressions of noise on noise.
    rebuilt = panel["Mkt-RF"] + panel["RF"]
    assert np.allclose(rebuilt.values, returns["SPY"].values, atol=1e-6)


def test_drawdown_breaches_the_policy_limit(returns):
    wealth = (1.0 + returns["portfolio_return"]).cumprod()
    mdd = float((wealth / wealth.cummax() - 1.0).min())
    assert -0.20 < mdd < -cfg.POLICY["max_drawdown"], f"MDD {mdd:.3f} must breach 10%"


def test_generator_is_deterministic():
    before = cfg.RETURNS_CSV.read_bytes()
    subprocess.run([sys.executable, "generate_treasury_data.py"],
                   cwd=cfg.REPO_ROOT, check=True, capture_output=True)
    assert cfg.RETURNS_CSV.read_bytes() == before, "same seed must give identical bytes"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_treasury_data.py -v`
Expected: all tests SKIPPED — "run `python3 generate_treasury_data.py` first"

- [ ] **Step 3: Write the generator**

Create `generate_treasury_data.py`:

```python
#!/usr/bin/env python3
"""Generate the synthetic treasury datasets for the AI DOF Command Centre.

Run once; the output is committed:

    python3 generate_treasury_data.py            # write the CSVs
    python3 generate_treasury_data.py --report   # write, then print realized stats

Everything here is MODELLED and deterministic under ``treasury.config.SEED``.
Two properties matter and are easy to get wrong:

1. The factor panel is built FIRST and both SPY and the portfolio are derived
   from it (``SPY = Mkt-RF + RF``). Generating the portfolio independently would
   make every Fama-French loading a regression of one noise series on another.
2. Returns are written NET of the management fee, matching how a custodian
   statement reads. Gross figures are recovered by adding the fee back.
"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from treasury import config as cfg


def trading_days() -> pd.DatetimeIndex:
    """Business days over the sample.

    Holidays are deliberately NOT excluded: the reference project's sample CSV
    contains 2023-07-04 and 2023-12-25, and our file must be interchangeable
    with it.
    """
    idx = pd.bdate_range(start=cfg.START, end=cfg.END)
    idx.name = "date"
    return idx


def build_factor_panel() -> pd.DataFrame:
    """Daily Fama-French style factor panel with realistic vols and premia."""
    rng = np.random.default_rng(cfg.SEED)
    idx = trading_days()
    n = len(idx)
    d = cfg.TRADING_DAYS_PER_YEAR

    data = {}
    for name in cfg.FF5_FACTORS:
        drift = cfg.FACTOR_PREMIUM[name] / d
        data[name] = rng.normal(drift, cfg.FACTOR_VOL[name], size=n)
    data["RF"] = np.full(n, cfg.RF_ANNUAL / d)

    panel = pd.DataFrame(data, index=idx)
    panel.index.name = "date"
    return panel


def build_portfolio_returns(panel: pd.DataFrame) -> pd.DataFrame:
    """Portfolio and benchmark returns generated from the factor panel.

    The portfolio is a two-regime factor bet: defensive and value-tilted through
    2025, then rotating into high-beta small-cap growth from 2026-01. Full-period
    beta lands inside the policy limit, so only the rolling window exposes the
    drift -- which is the finding the page exists to surface.
    """
    rng = np.random.default_rng(cfg.SEED + 1)
    idx = panel.index
    d = cfg.TRADING_DAYS_PER_YEAR
    split = pd.Timestamp(cfg.REGIME_SPLIT)

    excess = np.zeros(len(idx))
    for i, ts in enumerate(idx):
        r = cfg.REGIMES["FY2025"] if ts < split else cfg.REGIMES["FY2026"]
        loadings = {"Mkt-RF": r["mkt"], "SMB": r["smb"], "HML": r["hml"],
                    "RMW": r["rmw"], "CMA": r["cma"]}
        systematic = sum(loadings[f] * panel[f].iloc[i] for f in cfg.FF5_FACTORS)
        idio = rng.normal(0.0, r["idio"] / np.sqrt(d))
        excess[i] = r["alpha"] / d + systematic + idio

    # The drawdown episode: a sustained negative drift, not a single crash.
    shock = (idx >= pd.Timestamp(cfg.SHOCK_START)) & (idx <= pd.Timestamp(cfg.SHOCK_END))
    excess[shock] += cfg.SHOCK_DAILY

    # Net of fees, and back to total returns.
    portfolio = excess + panel["RF"].to_numpy() - cfg.FEE_ANNUAL / d
    spy = panel["Mkt-RF"].to_numpy() + panel["RF"].to_numpy()

    out = pd.DataFrame({"portfolio_return": portfolio, "SPY": spy}, index=idx)
    out.index.name = "date"
    return out


def _write(df: pd.DataFrame, path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # 6 decimal places, matching the reference sample's formatting.
    df.round(6).to_csv(path, float_format="%.6g")
    print(f"wrote {path.relative_to(cfg.REPO_ROOT)}  ({len(df)} rows)")


def report(panel: pd.DataFrame, returns: pd.DataFrame) -> None:
    """Print realized statistics, for the calibration loop in the plan."""
    d = cfg.TRADING_DAYS_PER_YEAR
    p = returns["portfolio_return"]
    wealth = (1.0 + p).cumprod()
    mdd = float((wealth / wealth.cummax() - 1.0).min())
    print("\n-- realized calibration --")
    print(f"  observations      : {len(p)}")
    print(f"  SPY daily sd      : {returns['SPY'].std(ddof=1):.5f}")
    print(f"  portfolio daily sd: {p.std(ddof=1):.5f}")
    print(f"  portfolio ann vol : {p.std(ddof=1) * np.sqrt(d):.2%}")
    print(f"  max drawdown      : {mdd:.2%}   (policy limit "
          f"-{cfg.POLICY['max_drawdown']:.0%})")

    import statsmodels.api as sm
    rf = panel["RF"]
    y = p - rf
    # CAPM: one factor, so the style premia leak into the intercept.
    x1 = sm.add_constant(pd.DataFrame({"MKT": returns["SPY"] - rf}))
    capm = sm.OLS(y, x1).fit()
    # FF5: controls for them, so the intercept is closer to true alpha.
    x5 = sm.add_constant(panel[cfg.FF5_FACTORS])
    ff5 = sm.OLS(y, x5).fit()
    print(f"  CAPM alpha (ann)  : {capm.params['const'] * d:+.2%}  "
          f"beta {capm.params['MKT']:.3f}")
    print(f"  FF5 alpha (ann)   : {ff5.params['const'] * d:+.2%}   "
          f"<- net of the {cfg.FEE_ANNUAL:.2%} fee")
    print(f"  FF5 Mkt-RF beta   : {ff5.params['Mkt-RF']:.3f}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--report", action="store_true",
                    help="print realized statistics after writing")
    args = ap.parse_args()

    panel = build_factor_panel()
    returns = build_portfolio_returns(panel)
    _write(panel, cfg.FACTORS_CSV)
    _write(returns, cfg.RETURNS_CSV)
    if args.report:
        report(panel, returns)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Generate the data and run the calibration loop**

Run: `python3 generate_treasury_data.py --report`

Read the realized statistics and check them against these acceptance bands:

| Statistic | Band | If outside the band |
|---|---|---|
| observations | 500–540 | check `START`/`END` |
| SPY daily sd | 0.008–0.012 | adjust `FACTOR_VOL["Mkt-RF"]` |
| portfolio ann vol | 12%–26% | adjust regime `idio` |
| max drawdown | −20% to −11% | adjust `SHOCK_DAILY` (more negative deepens it) |
| CAPM alpha, annualized | +0.8% to +3.5% | adjust `FACTOR_PREMIUM["HML"]`/`["RMW"]` |
| FF5 alpha, annualized | −1.2% to −0.05% | adjust regime `alpha` |
| FF5 Mkt-RF beta | 0.90–1.00 | adjust regime `mkt` (keep FY2026 above 1.0) |

Change values in `treasury/config.py` only, re-run, repeat until every row is inside its band. The two that matter most: **max drawdown must breach the 10% limit**, and **FF5 alpha must be negative while CAPM alpha is positive** — that pairing is the finding.

Record the final numbers in the commit message.

- [ ] **Step 5: Run the tests**

Run: `python3 -m pytest tests/test_treasury_data.py -v`
Expected: 8 passed

- [ ] **Step 6: Commit**

```bash
git add generate_treasury_data.py data_compact/treasury/ tests/test_treasury_data.py
git commit -m "feat: add deterministic treasury factor panel and return generator"
```

---

### Task 3: Analytics — parsing, statistics, and regressions

**Files:**
- Create: `treasury/analytics.py`
- Modify: `tests/test_treasury_analytics.py`

**Interfaces:**
- Consumes: `treasury.config`; the CSVs from Task 2.
- Produces:
  - `load_returns(source) -> pd.DataFrame` — accepts a path, file-like object, bytes, or raw CSV text; returns a `DatetimeIndex` frame with columns `portfolio_return`, `SPY`.
  - `load_factors(try_live: bool = True) -> FactorData`
  - `FactorData(factors: pd.DataFrame, source: str, is_synthetic: bool)`
  - `wealth_index(returns) -> pd.Series`, `drawdown_series(returns) -> pd.Series`, `max_drawdown(returns) -> float`
  - `performance_stats(returns, rf_daily) -> PerformanceStats` with fields `total_return, cagr, ann_vol, sharpe, sortino, max_drawdown, hit_rate, best_day, worst_day`
  - `rolling_sharpe(returns, window, rf_daily) -> pd.Series`
  - `FactorLoading(name, coef, tstat, pvalue, annualized, description)` with property `significant`
  - `RegressionResult(label, loadings, r_squared, adj_r_squared, nobs, alpha_annualized)` with method `loading(name)`
  - `capm_regression(portfolio, spy, rf_daily) -> RegressionResult` — market loading is named `Beta (Market)`
  - `fama_french_regression(portfolio, factor_data, factors) -> RegressionResult`
  - `rolling_factor_betas(portfolio, factor_data, factors, window) -> pd.DataFrame`

These signatures follow the reference project's `analytics.py` closely, so its templates need no reshaping. Task 4 adds `policy_check`, Task 5 adds the operating model, both to this same file.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_treasury_analytics.py`:

```python
import io

import numpy as np

from treasury import analytics as an


# --------------------------------------------------------------- layering -- #
def test_analytics_does_not_import_presentation_libraries():
    """The math layer must stay independent of the UI (spec: architecture)."""
    import treasury.analytics
    src = pathlib.Path(treasury.analytics.__file__).read_text()
    for banned in ("import streamlit", "import plotly", "import jinja2"):
        assert banned not in src, f"analytics.py must not {banned}"


# ----------------------------------------------------------------- parsing -- #
REFERENCE_STYLE_CSV = """date,portfolio_return,SPY
2023-01-03,-0.017644,-0.010855
2023-01-04,0.000452,0.004313
2023-03-06,-0.003103,-5.1e-05
2023-07-04,0.013893,0.009569
2023-12-25,-0.020188,-0.012746
"""


def test_load_returns_parses_reference_style_csv():
    """Replicates the quirks of the reference project's sample file: holiday
    rows, 6dp decimals and scientific notation for tiny values."""
    long = REFERENCE_STYLE_CSV + "".join(
        f"2024-0{1 + i // 28}-{1 + i % 28:02d},0.001,0.001\n" for i in range(40)
    )
    df = an.load_returns(io.StringIO(long))
    assert list(df.columns) == ["portfolio_return", "SPY"]
    assert df.loc["2023-03-06", "SPY"] == pytest.approx(-5.1e-05)
    assert isinstance(df.index, pd.DatetimeIndex)
    assert df.index.is_monotonic_increasing


def test_load_returns_accepts_aliased_column_names():
    csv = "Date,strategy,benchmark\n" + "".join(
        f"2024-01-{1 + i:02d},0.001,0.002\n" for i in range(31)
    )
    df = an.load_returns(csv)
    assert list(df.columns) == ["portfolio_return", "SPY"]


def test_load_returns_rejects_missing_column_with_a_useful_message():
    with pytest.raises(ValueError, match="portfolio"):
        an.load_returns("date,SPY\n2024-01-01,0.01\n")


def test_load_returns_rejects_too_few_rows():
    with pytest.raises(ValueError, match="30"):
        an.load_returns("date,portfolio_return,SPY\n2024-01-01,0.01,0.01\n")


# -------------------------------------------------------------- statistics -- #
def test_drawdown_and_max_drawdown_on_a_hand_computed_series():
    # 1.0 -> 1.10 -> 0.99 -> 1.089 : trough is 0.99 against a 1.10 peak = -10%.
    r = pd.Series([0.10, -0.10, 0.10], index=pd.bdate_range("2024-01-01", periods=3))
    assert an.max_drawdown(r) == pytest.approx(-0.10)
    assert an.drawdown_series(r).iloc[0] == pytest.approx(0.0)


def test_sharpe_and_sortino_on_a_constant_series():
    r = pd.Series([0.001] * 60, index=pd.bdate_range("2024-01-01", periods=60))
    assert np.isnan(an.sharpe_ratio(r))          # zero variance
    assert np.isnan(an.sortino_ratio(r))         # no downside observations


def test_sortino_exceeds_sharpe_when_upside_is_the_volatile_side():
    rng = np.random.default_rng(0)
    r = pd.Series(np.where(rng.random(400) < 0.5, 0.004, -0.001),
                  index=pd.bdate_range("2024-01-01", periods=400))
    assert an.sortino_ratio(r) > an.sharpe_ratio(r)


def test_performance_stats_bundles_the_headline_metrics():
    df = an.load_returns(cfg.RETURNS_CSV)
    stats = an.performance_stats(df["portfolio_return"], cfg.RF_ANNUAL / 252)
    assert -1.0 < stats.total_return < 2.0
    assert 0.0 < stats.ann_vol < 0.40
    assert stats.max_drawdown < 0.0
    assert 0.0 < stats.hit_rate < 1.0
    assert stats.worst_day < 0.0 < stats.best_day


# ------------------------------------------------------------- regressions -- #
@pytest.fixture(scope="module")
def loaded():
    return an.load_returns(cfg.RETURNS_CSV), an.load_factors(try_live=False)


def test_load_factors_offline_reports_the_committed_panel(loaded):
    _, fd = loaded
    assert fd.is_synthetic is True
    assert "MODELLED" in fd.source or "committed" in fd.source.lower()
    assert list(fd.factors.columns) == cfg.FF5_FACTORS + ["RF"]


def test_capm_recovers_the_baked_in_beta_per_regime(loaded):
    """The planted drift: each regime's beta is recoverable, but the full-period
    beta hides it inside the policy limit."""
    rets, fd = loaded
    rf = fd.factors["RF"]
    split = pd.Timestamp(cfg.REGIME_SPLIT)

    for name, sl in (("FY2025", rets.index < split), ("FY2026", rets.index >= split)):
        sub = rets[sl]
        res = an.capm_regression(sub["portfolio_return"], sub["SPY"], rf.reindex(sub.index))
        beta = res.loading("Beta (Market)").coef
        expected = cfg.REGIMES[name]["mkt"]
        assert beta == pytest.approx(expected, abs=0.18), f"{name}: {beta:.3f}"

    full = an.capm_regression(rets["portfolio_return"], rets["SPY"], rf)
    full_beta = full.loading("Beta (Market)").coef
    assert full_beta < cfg.POLICY["max_beta"], "full-period beta must look compliant"


def test_ff5_recovers_the_baked_in_style_loadings(loaded):
    rets, fd = loaded
    split = pd.Timestamp(cfg.REGIME_SPLIT)
    for name, sl in (("FY2025", rets.index < split), ("FY2026", rets.index >= split)):
        sub_fd = an.FactorData(fd.factors[sl], fd.source, fd.is_synthetic)
        res = an.fama_french_regression(rets["portfolio_return"][sl], sub_fd,
                                        cfg.FF5_FACTORS)
        for factor, key in (("Mkt-RF", "mkt"), ("SMB", "smb"), ("HML", "hml")):
            got = res.loading(factor).coef
            assert got == pytest.approx(cfg.REGIMES[name][key], abs=0.25), \
                f"{name} {factor}: {got:.3f}"
        assert res.r_squared > 0.5


def test_capm_alpha_is_positive_while_ff5_alpha_is_negative(loaded):
    """The headline finding: CAPM mistakes factor premia for skill. Once the
    style factors are controlled for, alpha net of fees is negative."""
    rets, fd = loaded
    rf = fd.factors["RF"]
    capm = an.capm_regression(rets["portfolio_return"], rets["SPY"], rf)
    ff5 = an.fama_french_regression(rets["portfolio_return"], fd, cfg.FF5_FACTORS)
    assert capm.alpha_annualized > 0.0
    assert ff5.alpha_annualized < 0.0
    assert ff5.r_squared >= capm.r_squared


def test_rolling_betas_expose_the_drift_the_full_period_hides(loaded):
    rets, fd = loaded
    roll = an.rolling_factor_betas(rets["portfolio_return"], fd, cfg.FF5_FACTORS,
                                   window=cfg.DEFAULT_WINDOW)
    assert list(roll.columns) == cfg.FF5_FACTORS
    assert len(roll) == len(rets) - cfg.DEFAULT_WINDOW + 1
    assert roll["Mkt-RF"].max() > cfg.POLICY["max_beta"], "the breach must be visible"
    late = roll.loc[roll.index >= pd.Timestamp(cfg.REGIME_SPLIT), "Mkt-RF"]
    early = roll.loc[roll.index < pd.Timestamp(cfg.REGIME_SPLIT), "Mkt-RF"]
    assert late.mean() > early.mean() + 0.2, "beta must rise across the split"


def test_rolling_betas_return_empty_frame_when_window_exceeds_sample(loaded):
    rets, fd = loaded
    roll = an.rolling_factor_betas(rets["portfolio_return"][:20], fd,
                                  cfg.FF5_FACTORS, window=63)
    assert roll.empty
    assert list(roll.columns) == cfg.FF5_FACTORS
```

Add `import pathlib` to the imports at the top of the file.

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_treasury_analytics.py -v`
Expected: FAIL — `ImportError: cannot import name 'analytics' from 'treasury'`

- [ ] **Step 3: Write the implementation**

Create `treasury/analytics.py`:

```python
"""Quantitative machinery for the treasury tearsheet.

Deliberately free of any presentation dependency -- no streamlit, no plotly, no
jinja2 -- so the math can be read, tested and reused on its own. A test enforces
this.

The module answers the four questions a Director of Finance must answer about a
treasury portfolio:

1. How did it perform?          -> performance_stats
2. Is there skill, or just market exposure?  -> capm_regression
3. What is actually driving the returns?     -> fama_french_regression
4. Has the mandate drifted?     -> rolling_factor_betas

Everything is computed on simple daily returns as decimals (0.001 = 0.1%).

The public surface mirrors the Quant Guild "Intro - Trading Dashboard" reference
project so its templates render our results unchanged.
"""
from __future__ import annotations

import io
import warnings
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd
import statsmodels.api as sm

from treasury import config as cfg

TRADING_DAYS_PER_YEAR = cfg.TRADING_DAYS_PER_YEAR

# --------------------------------------------------------------------------- #
#  1. Input parsing
# --------------------------------------------------------------------------- #
# Liberal in what we accept: this is the seam the visitor-upload flow will use,
# and real users mis-name columns constantly.
_PORTFOLIO_ALIASES = {
    "portfolio_return", "portfolio", "portfolio_returns", "port", "port_return",
    "returns", "return", "strategy", "strategy_return", "treasury", "treasury_return",
}
_SPY_ALIASES = {
    "spy", "spy_return", "spy_returns", "benchmark", "benchmark_return",
    "market", "market_return", "mkt",
}
_DATE_ALIASES = {"date", "dates", "datetime", "timestamp", "day", "month"}

MIN_OBSERVATIONS = 30


def _normalize(name: str) -> str:
    return str(name).strip().lower().replace(" ", "_")


def load_returns(source) -> pd.DataFrame:
    """Read and normalize a daily returns CSV.

    ``source`` may be a path, a file-like object, raw bytes, or raw CSV text --
    the last two are what a web upload delivers.
    """
    if isinstance(source, bytes):
        source = io.BytesIO(source)
    elif isinstance(source, str) and ("\n" in source or "," in source):
        source = io.StringIO(source)

    df = pd.read_csv(source)
    if df.empty:
        raise ValueError("The returns CSV appears to be empty.")

    lookup = {_normalize(c): c for c in df.columns}

    def _find(aliases: set[str], what: str) -> str:
        for alias in aliases:
            if alias in lookup:
                return lookup[alias]
        raise ValueError(
            f"Could not find a {what} column. Looked for any of: "
            f"{sorted(aliases)}. Found: {list(df.columns)}."
        )

    date_col = _find(_DATE_ALIASES, "date")
    port_col = _find(_PORTFOLIO_ALIASES, "portfolio return")
    spy_col = _find(_SPY_ALIASES, "benchmark (SPY) return")

    out = pd.DataFrame({
        "portfolio_return": pd.to_numeric(df[port_col], errors="coerce"),
        "SPY": pd.to_numeric(df[spy_col], errors="coerce"),
    })
    out.index = pd.to_datetime(df[date_col], errors="coerce")
    out.index.name = "date"
    out = out[~out.index.isna()].dropna().sort_index()

    if len(out) < MIN_OBSERVATIONS:
        raise ValueError(
            f"Need at least {MIN_OBSERVATIONS} valid daily observations to "
            f"compute meaningful statistics; found {len(out)}."
        )
    if out.abs().median().median() > 1.0:
        warnings.warn(
            "Returns look large for decimals -- are these percentages? "
            "Values are used as-is; divide by 100 if needed."
        )
    return out


# --------------------------------------------------------------------------- #
#  2. Factor panel
# --------------------------------------------------------------------------- #
@dataclass
class FactorData:
    """A factor panel plus provenance, for the page's source banner."""
    factors: pd.DataFrame
    source: str
    is_synthetic: bool = False


def _load_committed_panel() -> FactorData:
    if not cfg.FACTORS_CSV.exists():
        raise FileNotFoundError(
            f"Factor panel not found at {cfg.FACTORS_CSV}. "
            "Run: python3 generate_treasury_data.py"
        )
    panel = pd.read_csv(cfg.FACTORS_CSV, parse_dates=["date"]).set_index("date")
    return FactorData(
        factors=panel,
        source="MODELLED panel committed to this repo (offline, deterministic)",
        is_synthetic=True,
    )


def load_factors(try_live: bool = True) -> FactorData:
    """Daily Fama-French factors.

    Tries Ken French's library first when ``try_live`` is set, then falls back to
    the committed MODELLED panel. The fallback is the normal case: this project
    must render identically offline, and the page says so in a banner rather than
    quietly passing modelled factors off as market data.
    """
    if try_live:
        try:
            from pandas_datareader import data as pdr  # type: ignore

            raw = pdr.DataReader("F-F_Research_Data_5_Factors_2x3_daily",
                                 "famafrench", cfg.START, cfg.END)[0]
            raw.index = pd.to_datetime(raw.index.astype(str))
            panel = raw / 100.0            # Ken French ships percent
            if not panel.empty:
                return FactorData(panel, "pandas_datareader (Ken French library)",
                                  is_synthetic=False)
        except Exception:
            pass
    return _load_committed_panel()


# --------------------------------------------------------------------------- #
#  3. Performance and risk
# --------------------------------------------------------------------------- #
def wealth_index(returns: pd.Series, initial: float = 1.0) -> pd.Series:
    """Cumulative growth of $1 -- the equity curve."""
    return initial * (1.0 + returns).cumprod()


def drawdown_series(returns: pd.Series) -> pd.Series:
    """Percentage decline from the running peak -- the underwater curve."""
    wealth = wealth_index(returns)
    return wealth / wealth.cummax() - 1.0


def max_drawdown(returns: pd.Series) -> float:
    """Worst peak-to-trough decline, as a negative number."""
    return float(drawdown_series(returns).min())


def annualized_return(returns: pd.Series) -> float:
    """CAGR implied by the realized cumulative return."""
    n = len(returns)
    if n == 0:
        return float("nan")
    growth = float((1.0 + returns).prod())
    if growth <= 0:
        return -1.0
    return growth ** (TRADING_DAYS_PER_YEAR / n) - 1.0


def annualized_volatility(returns: pd.Series) -> float:
    """Daily standard deviation scaled by the square-root-of-time rule."""
    return float(returns.std(ddof=1) * np.sqrt(TRADING_DAYS_PER_YEAR))


def sharpe_ratio(returns: pd.Series, rf_daily=0.0) -> float:
    """Annualized excess return per unit of total volatility."""
    excess = returns - rf_daily
    sd = excess.std(ddof=1)
    if sd == 0 or np.isnan(sd):
        return float("nan")
    return float(excess.mean() / sd * np.sqrt(TRADING_DAYS_PER_YEAR))


def sortino_ratio(returns: pd.Series, rf_daily=0.0) -> float:
    """Like Sharpe, but penalizing only downside deviation."""
    excess = returns - rf_daily
    downside = excess[excess < 0]
    sd = downside.std(ddof=1) if len(downside) > 1 else float("nan")
    if not np.isfinite(sd) or sd == 0:
        return float("nan")
    return float(excess.mean() / sd * np.sqrt(TRADING_DAYS_PER_YEAR))


def rolling_sharpe(returns: pd.Series, window: int = cfg.DEFAULT_WINDOW,
                   rf_daily=0.0) -> pd.Series:
    """Trailing annualized Sharpe over a moving window."""
    excess = returns - rf_daily
    mean = excess.rolling(window).mean()
    sd = excess.rolling(window).std(ddof=1)
    return (mean / sd) * np.sqrt(TRADING_DAYS_PER_YEAR)


@dataclass
class PerformanceStats:
    total_return: float
    cagr: float
    ann_vol: float
    sharpe: float
    sortino: float
    max_drawdown: float
    hit_rate: float
    best_day: float
    worst_day: float


def performance_stats(returns: pd.Series, rf_daily=0.0) -> PerformanceStats:
    """The headline performance and risk metrics for one return series."""
    return PerformanceStats(
        total_return=float((1.0 + returns).prod() - 1.0),
        cagr=annualized_return(returns),
        ann_vol=annualized_volatility(returns),
        sharpe=sharpe_ratio(returns, rf_daily),
        sortino=sortino_ratio(returns, rf_daily),
        max_drawdown=max_drawdown(returns),
        hit_rate=float((returns > 0).mean()),
        best_day=float(returns.max()),
        worst_day=float(returns.min()),
    )


# --------------------------------------------------------------------------- #
#  4. Regressions -- CAPM and Fama-French share one OLS engine
# --------------------------------------------------------------------------- #
@dataclass
class FactorLoading:
    name: str
    coef: float
    tstat: float
    pvalue: float
    annualized: Optional[float] = None
    description: str = ""

    @property
    def significant(self) -> bool:
        return self.pvalue < 0.05


@dataclass
class RegressionResult:
    label: str
    loadings: list[FactorLoading]
    r_squared: float
    adj_r_squared: float
    nobs: int
    alpha_annualized: float = field(default=float("nan"))

    def loading(self, name: str) -> Optional[FactorLoading]:
        for l in self.loadings:
            if l.name.lower() == name.lower():
                return l
        return None


def _ols(y: pd.Series, X: pd.DataFrame, label: str) -> RegressionResult:
    """OLS of y on X, with a constant added and the intercept annualized.

    The daily intercept is multiplied by 252 -- the standard convention for
    daily-frequency factor regressions.
    """
    X = sm.add_constant(X, has_constant="add")
    model = sm.OLS(y, X, missing="drop").fit()

    loadings: list[FactorLoading] = []
    for name in X.columns:
        coef = float(model.params[name])
        is_const = name == "const"
        loadings.append(FactorLoading(
            name="Alpha" if is_const else name,
            coef=coef,
            tstat=float(model.tvalues[name]),
            pvalue=float(model.pvalues[name]),
            annualized=coef * TRADING_DAYS_PER_YEAR if is_const else None,
            description=("Return not explained by the factors below."
                         if is_const else cfg.FACTOR_DESCRIPTIONS.get(name, "")),
        ))

    return RegressionResult(
        label=label,
        loadings=loadings,
        r_squared=float(model.rsquared),
        adj_r_squared=float(model.rsquared_adj),
        nobs=int(model.nobs),
        alpha_annualized=float(model.params["const"] * TRADING_DAYS_PER_YEAR),
    )


def capm_regression(portfolio: pd.Series, spy: pd.Series,
                    rf_daily=0.0) -> RegressionResult:
    """CAPM: (r_p - rf) = alpha + beta (r_m - rf) + e

    With only a market factor, any return earned from style tilts lands in the
    intercept. That is exactly the trap this page is built to expose -- compare
    this alpha with the Fama-French alpha before calling it skill.
    """
    y = (portfolio - rf_daily).rename("excess_portfolio")
    x = (spy - rf_daily).rename("MKT")
    data = pd.concat([y, x], axis=1).dropna()
    result = _ols(data["excess_portfolio"], data[["MKT"]], label="CAPM")
    for l in result.loadings:
        if l.name == "MKT":
            l.name = "Beta (Market)"
            l.description = "Sensitivity to the market: 1.0 moves with it."
    return result


def fama_french_regression(portfolio: pd.Series, factor_data: FactorData,
                           factors: list[str]) -> RegressionResult:
    """Regress excess returns on a set of Fama-French factors."""
    merged = pd.concat([portfolio.rename("portfolio"), factor_data.factors],
                       axis=1, join="inner").dropna()
    if len(merged) < MIN_OBSERVATIONS:
        raise ValueError(
            "Too few overlapping dates between returns and factors "
            f"({len(merged)}) to run the factor regression."
        )
    excess = merged["portfolio"] - merged["RF"]
    return _ols(excess, merged[factors], label=f"Fama-French {len(factors)}-Factor")


def rolling_factor_betas(portfolio: pd.Series, factor_data: FactorData,
                         factors: list[str],
                         window: int = cfg.DEFAULT_WINDOW) -> pd.DataFrame:
    """Re-estimate the factor loadings over a moving window.

    Wandering lines are style drift. For this portfolio it is the only view that
    catches the mandate breach -- the full-period beta is inside the limit.
    """
    merged = pd.concat([portfolio.rename("portfolio"), factor_data.factors],
                       axis=1, join="inner").dropna()
    if len(merged) < window:
        return pd.DataFrame(columns=factors)

    excess = merged["portfolio"] - merged["RF"]
    X = sm.add_constant(merged[factors], has_constant="add")

    rows, index = [], []
    for i in range(window, len(merged) + 1):
        sl = slice(i - window, i)
        try:
            params = sm.OLS(excess.iloc[sl], X.iloc[sl]).fit().params
        except Exception:
            continue
        rows.append({f: float(params.get(f, np.nan)) for f in factors})
        index.append(merged.index[i - 1])

    if not rows:
        return pd.DataFrame(columns=factors)
    out = pd.DataFrame(rows, index=pd.DatetimeIndex(index, name="date"))
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/ -v`
Expected: all pass. If a `pytest.approx(..., abs=0.18)` beta assertion fails, the generator needs re-tuning per Task 2 Step 4 — do not widen the tolerance to make the test pass.

- [ ] **Step 5: Commit**

```bash
git add treasury/analytics.py tests/test_treasury_analytics.py
git commit -m "feat: add treasury analytics — parsing, risk stats, CAPM and Fama-French"
```

---

### Task 4: Treasury policy checks

**Files:**
- Modify: `treasury/analytics.py` (append)
- Modify: `tests/test_treasury_analytics.py` (append)

**Interfaces:**
- Consumes: `PerformanceStats`, `RegressionResult`, `rolling_factor_betas` output from Task 3.
- Produces:
  - `Breach(check: str, limit: str, observed: str, cash_at_risk: float, why: str, risk: str, action: str, owner: str, due: str, breached: bool)`
  - `policy_check(perf: PerformanceStats, capm: RegressionResult, ff5: RegressionResult, rolling: pd.DataFrame) -> list[Breach]` — returns all three checks, breached or not, in a stable order.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_treasury_analytics.py`:

```python
# ----------------------------------------------------------------- policy -- #
@pytest.fixture(scope="module")
def breaches(loaded):
    rets, fd = loaded
    rf = fd.factors["RF"]
    perf = an.performance_stats(rets["portfolio_return"], rf)
    capm = an.capm_regression(rets["portfolio_return"], rets["SPY"], rf)
    ff5 = an.fama_french_regression(rets["portfolio_return"], fd, cfg.FF5_FACTORS)
    roll = an.rolling_factor_betas(rets["portfolio_return"], fd, cfg.FF5_FACTORS,
                                   cfg.DEFAULT_WINDOW)
    return an.policy_check(perf, capm, ff5, roll)


def test_policy_check_returns_all_three_checks_in_stable_order(breaches):
    assert [b.check for b in breaches] == [
        "Peak rolling market beta", "Maximum drawdown", "Alpha, net of fees",
    ]


def test_all_three_planted_breaches_fire(breaches):
    """If this fails, the planted findings have been generated away."""
    assert all(b.breached for b in breaches), \
        [(b.check, b.observed) for b in breaches if not b.breached]


def test_every_breach_is_sized_in_cash_and_assigned(breaches):
    """The ai-dof skill's rule: why it matters in cash, the risk, the action."""
    for b in breaches:
        assert b.cash_at_risk > 0
        assert b.cash_at_risk < cfg.PORTFOLIO_NOTIONAL
        assert b.why and b.risk and b.action and b.owner and b.due


def test_beta_breach_is_sized_off_the_market_stress_assumption(breaches):
    beta_breach = breaches[0]
    # excess beta x stress x notional
    assert beta_breach.cash_at_risk == pytest.approx(
        (float(beta_breach.observed) - cfg.POLICY["max_beta"])
        * cfg.POLICY["market_stress"] * cfg.PORTFOLIO_NOTIONAL, rel=0.01)


def test_policy_check_reports_compliance_when_limits_are_respected():
    """A well-behaved portfolio must produce zero breaches -- otherwise the page
    cries wolf and the finding means nothing."""
    idx = pd.bdate_range("2024-07-01", periods=300)
    rng = np.random.default_rng(4)
    calm = pd.Series(rng.normal(0.0004, 0.004, len(idx)), index=idx)
    spy = pd.Series(rng.normal(0.0003, 0.008, len(idx)), index=idx)
    rf = pd.Series(cfg.RF_ANNUAL / 252, index=idx)
    panel = pd.DataFrame({f: rng.normal(0, 0.004, len(idx)) for f in cfg.FF5_FACTORS},
                         index=idx)
    panel["RF"] = rf
    fd = an.FactorData(panel, "test", True)
    perf = an.performance_stats(calm, rf)
    capm = an.capm_regression(calm, spy, rf)
    ff5 = an.fama_french_regression(calm, fd, cfg.FF5_FACTORS)
    roll = an.rolling_factor_betas(calm, fd, cfg.FF5_FACTORS, 63)
    result = an.policy_check(perf, capm, ff5, roll)
    assert not any(b.breached for b in result)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_treasury_analytics.py -k policy -v`
Expected: FAIL — `AttributeError: module 'treasury.analytics' has no attribute 'policy_check'`

- [ ] **Step 3: Write the implementation**

Append to `treasury/analytics.py`:

```python
# --------------------------------------------------------------------------- #
#  5. Judgment -- the investment policy the DOF is accountable for
# --------------------------------------------------------------------------- #
@dataclass
class Breach:
    """One policy check, sized and assigned.

    Follows the ai-dof skill's rule that a finding must answer three questions:
    why it matters sized in cash, what risk it creates, and what management
    should do -- with an owner and a date.
    """
    check: str
    limit: str
    observed: str
    breached: bool
    cash_at_risk: float
    why: str
    risk: str
    action: str
    owner: str
    due: str


POLICY_OWNER = "Group CFO"
POLICY_DUE = "2026-09-30"


def policy_check(perf: PerformanceStats, capm: RegressionResult,
                 ff5: RegressionResult, rolling: pd.DataFrame) -> list[Breach]:
    """Evaluate the treasury investment policy.

    Returns all three checks in a stable order whether or not they breach, so
    the page can show a compliance table rather than only bad news.
    """
    notional = cfg.PORTFOLIO_NOTIONAL
    limits = cfg.POLICY

    # --- 1. Mandate drift. The peak ROLLING beta, not the full-period beta:
    # the full-period number is inside the limit, which is the whole point.
    peak_beta = (float(rolling["Mkt-RF"].max())
                 if not rolling.empty and "Mkt-RF" in rolling else float("nan"))
    full_beta = capm.loading("Beta (Market)")
    full_beta_val = full_beta.coef if full_beta else float("nan")
    beta_excess = max(0.0, peak_beta - limits["max_beta"])
    beta_breached = np.isfinite(peak_beta) and peak_beta > limits["max_beta"]

    beta = Breach(
        check="Peak rolling market beta",
        limit=f"{limits['max_beta']:.2f}",
        observed=f"{peak_beta:.3f}",
        breached=bool(beta_breached),
        cash_at_risk=beta_excess * limits["market_stress"] * notional,
        why=(f"Peak {cfg.DEFAULT_WINDOW}-day rolling beta reached {peak_beta:.2f} "
             f"against a {limits['max_beta']:.2f} mandate ceiling. The full-period "
             f"beta is {full_beta_val:.2f} and looks compliant, so the annual "
             f"report would not have caught this."),
        risk=(f"In a {limits['market_stress']:.0%} market decline the excess "
              f"exposure alone costs roughly "
              f"{_money(beta_excess * limits['market_stress'] * notional)} of "
              f"operating cash the group has not budgeted to lose."),
        action="Rebalance to the mandate ceiling and add a rolling-beta breach alert.",
        owner=POLICY_OWNER,
        due=POLICY_DUE,
    )

    # --- 2. Capital preservation.
    mdd = abs(perf.max_drawdown)
    dd_excess = max(0.0, mdd - limits["max_drawdown"])
    drawdown = Breach(
        check="Maximum drawdown",
        limit=f"-{limits['max_drawdown']:.0%}",
        observed=f"{perf.max_drawdown:.1%}",
        breached=bool(mdd > limits["max_drawdown"]),
        cash_at_risk=dd_excess * notional,
        why=(f"Peak-to-trough decline reached {perf.max_drawdown:.1%} against a "
             f"-{limits['max_drawdown']:.0%} tolerance — "
             f"{_money(dd_excess * notional)} beyond policy on "
             f"{_money(notional)} invested."),
        risk=("Treasury exists to preserve operating liquidity, not to earn a "
              "risk premium. A drawdown of this size can collide with a quarter "
              "in which the group needs the cash."),
        action="Cut equity beta until the trailing drawdown is inside tolerance.",
        owner=POLICY_OWNER,
        due=POLICY_DUE,
    )

    # --- 3. Is anyone actually adding value? Compare the two alphas.
    net_alpha = ff5.alpha_annualized
    gross_alpha = net_alpha + cfg.FEE_ANNUAL
    fee_cost = cfg.FEE_ANNUAL * notional
    alpha = Breach(
        check="Alpha, net of fees",
        limit=f"{limits['min_net_alpha']:.0%}",
        observed=f"{net_alpha:+.2%}",
        breached=bool(net_alpha < limits["min_net_alpha"]),
        cash_at_risk=fee_cost,
        why=(f"CAPM reports {capm.alpha_annualized:+.2%} alpha, but that is style "
             f"premia a single market factor cannot see. Controlling for all five "
             f"Fama-French factors leaves {gross_alpha:+.2%} gross and "
             f"{net_alpha:+.2%} net of the {cfg.FEE_ANNUAL:.2%} fee."),
        risk=(f"The group pays {_money(fee_cost)} a year for exposure it could "
              f"hold passively. The apparent outperformance is factor beta, not "
              f"manager skill, and it will reverse when those factors do."),
        action=("Move the mandate to a low-cost index sleeve or renegotiate the "
                "fee against a factor-adjusted benchmark."),
        owner=POLICY_OWNER,
        due=POLICY_DUE,
    )

    return [beta, drawdown, alpha]


def _money(v: float) -> str:
    """Match the existing app's money formatting."""
    v = float(v)
    if abs(v) >= 1e6:
        return f"${v / 1e6:,.2f}M"
    if abs(v) >= 1e3:
        return f"${v / 1e3:,.0f}k"
    return f"${v:,.0f}"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/ -v`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add treasury/analytics.py tests/test_treasury_analytics.py
git commit -m "feat: add treasury policy checks with cash sizing and assigned actions"
```

---

### Task 5: Operating factor model

**Files:**
- Modify: `generate_treasury_data.py` (add the monthly builder), `treasury/analytics.py` (add the model)
- Create (generated): `data_compact/treasury/operating_factors_monthly.csv`
- Modify: `tests/test_treasury_data.py`, `tests/test_treasury_analytics.py`

**Interfaces:**
- Consumes: `data_compact/csv/Invoices.csv` (columns `Period` as `YYYY-MM`, `Entity`, `TotalAmtUSD`); `treasury.config`.
- Produces:
  - In the generator: `ledger_monthly_revenue() -> pd.DataFrame` (index `month` as period string, columns per entity plus `GROUP`) and `build_operating_panel() -> pd.DataFrame` (60 rows; columns `month`, `<ENTITY>_growth` for each of MLG/CFS/NWC/APX, `group_growth`, `is_actual`, and the three factors).
  - In analytics: `load_operating_panel() -> pd.DataFrame` and `operating_factor_model(panel) -> tuple[RegressionResult, pd.DataFrame]` — the group regression plus a per-entity loadings frame indexed by entity with columns `freight_rate_index`, `diesel_price`, `industrial_production`, `r_squared`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_treasury_data.py`:

```python
# ------------------------------------------------- operating factor panel -- #
@pytest.fixture(scope="module")
def operating() -> pd.DataFrame:
    return pd.read_csv(cfg.OPERATING_CSV)


def test_operating_panel_covers_sixty_months(operating):
    assert len(operating) == 60
    assert operating["month"].iloc[0] == cfg.OPERATING_START
    assert operating["month"].iloc[-1] == cfg.LEDGER_END
    assert operating["month"].is_monotonic_increasing


def test_operating_panel_columns(operating):
    for e in cfg.OPERATING_ENTITIES:
        assert f"{e}_growth" in operating.columns
    assert "group_growth" in operating.columns
    assert "is_actual" in operating.columns
    for f in cfg.OPERATING_FACTORS:
        assert f in operating.columns
    assert "MHG_growth" not in operating.columns, "holdco books no invoice revenue"


def test_last_twenty_four_months_are_flagged_actual(operating):
    actual = operating[operating["is_actual"] == 1]
    assert len(actual) == 24
    assert actual["month"].iloc[0] == cfg.LEDGER_START


def test_actual_revenue_growth_reconciles_to_the_ledger(operating):
    """The overlap is ACTUAL ledger revenue, not modelled. If this drifts, the
    section-2 regression is no longer about Meridian."""
    from generate_treasury_data import ledger_monthly_revenue

    ledger = ledger_monthly_revenue()
    expected = ledger["GROUP"].pct_change().dropna()
    got = operating.set_index("month").loc[expected.index, "group_growth"]
    assert np.allclose(got.values, expected.values, atol=1e-6)
```

Append to `tests/test_treasury_analytics.py`:

```python
# -------------------------------------------------------- operating model -- #
def test_operating_factor_model_returns_group_and_entity_loadings():
    panel = an.load_operating_panel()
    group, entities = an.operating_factor_model(panel)
    assert group.nobs >= 55, "60 months less one for the growth difference"
    assert {l.name for l in group.loadings} == {"Alpha", *cfg.OPERATING_FACTORS}
    assert list(entities.index) == cfg.OPERATING_ENTITIES
    assert "r_squared" in entities.columns


def test_freight_rates_lift_revenue_and_diesel_costs_are_a_drag():
    """Signs must be economically sensible, or the section is noise."""
    panel = an.load_operating_panel()
    group, _ = an.operating_factor_model(panel)
    assert group.loading("freight_rate_index").coef > 0
    assert group.loading("freight_rate_index").significant
    assert group.loading("diesel_price").coef < 0


def test_asset_based_trucking_is_the_most_cyclical_entity():
    """CFS owns its trucks, so its revenue must swing hardest with freight
    rates -- the planted structure the page reports."""
    panel = an.load_operating_panel()
    _, entities = an.operating_factor_model(panel)
    assert entities.loc["CFS", "freight_rate_index"] == entities["freight_rate_index"].max()
    assert entities.loc["APX", "freight_rate_index"] < entities.loc["CFS", "freight_rate_index"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/ -k operating -v`
Expected: FAIL — `ImportError: cannot import name 'ledger_monthly_revenue'`

- [ ] **Step 3: Add the generator functions**

Insert into `generate_treasury_data.py`, above `_write`:

```python
def ledger_monthly_revenue() -> pd.DataFrame:
    """ACTUAL monthly revenue per entity, from the committed ledger.

    Invoices.csv carries a monthly ``Period`` (2024-07 .. 2026-06) and an
    ``Entity`` column, so this half of the operating panel needs no modelling
    at all.
    """
    inv = pd.read_csv(cfg.LEDGER_DIR / "Invoices.csv")
    inv["TotalAmtUSD"] = pd.to_numeric(inv["TotalAmtUSD"], errors="coerce").fillna(0.0)
    wide = (inv.pivot_table(index="Period", columns="Entity",
                            values="TotalAmtUSD", aggfunc="sum")
            .reindex(columns=cfg.OPERATING_ENTITIES)
            .fillna(0.0)
            .sort_index())
    wide["GROUP"] = wide.sum(axis=1)
    wide.index.name = "month"
    return wide


# Sensitivity of each entity's revenue to the freight cycle. CFS owns its
# trucks and is the most exposed; APX warehousing is contract-based and the
# least. MODELLED -- these drive the synthetic pre-history only.
ENTITY_CYCLICALITY = {"MLG": 1.05, "CFS": 1.45, "NWC": 0.70, "APX": 0.55}


def build_operating_panel() -> pd.DataFrame:
    """Monthly revenue growth and freight-market factors, 60 months.

    The last 24 months are ACTUAL ledger revenue. The first 36 are MODELLED
    pre-history, present because three factors cannot be estimated from 24
    observations but can from 60.
    """
    rng = np.random.default_rng(cfg.SEED + 2)
    months = pd.period_range(cfg.OPERATING_START, cfg.LEDGER_END, freq="M")
    n = len(months)

    # Freight market factors: an autocorrelated cycle plus noise, because
    # freight rates are persistent, not white noise.
    freight = np.zeros(n)
    for i in range(1, n):
        freight[i] = 0.55 * freight[i - 1] + rng.normal(0.0, 0.028)
    diesel = 0.45 * freight + rng.normal(0.0, 0.030, n)
    indpro = 0.35 * freight + rng.normal(0.0015, 0.008, n)

    ledger = ledger_monthly_revenue()
    ledger_growth = ledger.pct_change()

    rows = []
    for i, m in enumerate(months):
        key = str(m)
        actual = key in ledger_growth.index and not ledger_growth.loc[key].isna().all()
        row = {"month": key, "is_actual": int(actual),
               "freight_rate_index": freight[i], "diesel_price": diesel[i],
               "industrial_production": indpro[i]}
        for e in cfg.OPERATING_ENTITIES:
            if actual:
                row[f"{e}_growth"] = float(ledger_growth.loc[key, e])
            else:
                beta = ENTITY_CYCLICALITY[e]
                row[f"{e}_growth"] = float(
                    0.004 + beta * freight[i] - 0.25 * beta * diesel[i]
                    + 0.9 * indpro[i] + rng.normal(0.0, 0.022)
                )
        rows.append(row)

    panel = pd.DataFrame(rows)
    # Group growth is revenue-weighted, so it is not the mean of entity growths.
    weights = pd.Series({e: ENTITY_CYCLICALITY[e] for e in cfg.OPERATING_ENTITIES})
    ledger_totals = ledger[cfg.OPERATING_ENTITIES].sum()
    weights = ledger_totals / ledger_totals.sum()
    modelled_group = sum(panel[f"{e}_growth"] * weights[e]
                         for e in cfg.OPERATING_ENTITIES)
    panel["group_growth"] = modelled_group
    is_actual = panel["is_actual"] == 1
    actual_group = (panel.loc[is_actual, "month"]
                    .map(ledger_growth["GROUP"]).astype(float))
    panel.loc[is_actual, "group_growth"] = actual_group.values

    # The first month has no prior month, so no growth rate exists for it.
    panel = panel.iloc[1:].reset_index(drop=True)
    cols = (["month", "is_actual"]
            + [f"{e}_growth" for e in cfg.OPERATING_ENTITIES]
            + ["group_growth"] + cfg.OPERATING_FACTORS)
    return panel[cols]
```

Then extend `main()` — replace its body after `returns = build_portfolio_returns(panel)`:

```python
    operating = build_operating_panel()
    _write(panel, cfg.FACTORS_CSV)
    _write(returns, cfg.RETURNS_CSV)
    operating.to_csv(cfg.OPERATING_CSV, index=False, float_format="%.6g")
    print(f"wrote {cfg.OPERATING_CSV.relative_to(cfg.REPO_ROOT)}  "
          f"({len(operating)} rows)")
    if args.report:
        report(panel, returns)
```

Note: `build_operating_panel` drops the first month, so the file has 59 rows of growth from 60 months of levels. Update `test_operating_panel_covers_sixty_months` to assert `len(operating) == 59` and `operating["month"].iloc[0] == "2021-08"`, and rename it `test_operating_panel_covers_the_full_history`.

- [ ] **Step 4: Add the analytics functions**

Append to `treasury/analytics.py`:

```python
# --------------------------------------------------------------------------- #
#  6. Operating factor model -- the same technique on the group's own revenue
# --------------------------------------------------------------------------- #
def load_operating_panel() -> pd.DataFrame:
    """Monthly revenue growth and freight-market factors."""
    if not cfg.OPERATING_CSV.exists():
        raise FileNotFoundError(
            f"Operating panel not found at {cfg.OPERATING_CSV}. "
            "Run: python3 generate_treasury_data.py"
        )
    return pd.read_csv(cfg.OPERATING_CSV)


def operating_factor_model(panel: pd.DataFrame
                           ) -> tuple[RegressionResult, pd.DataFrame]:
    """Regress revenue growth on freight-market factors.

    Same machinery as the portfolio tearsheet, pointed at the operating
    business: which macro factors move Meridian's revenue, and which entities
    amplify the cycle. Run on 59 monthly observations -- 24 actual, the rest
    modelled pre-history -- because three factors cannot be estimated from 24
    points.
    """
    X = panel[cfg.OPERATING_FACTORS]
    group = _ols(panel["group_growth"], X, label="Group revenue growth")
    for l in group.loadings:
        if l.name != "Alpha":
            l.description = cfg.OPERATING_FACTOR_DESCRIPTIONS.get(l.name, "")

    rows = {}
    for entity in cfg.OPERATING_ENTITIES:
        res = _ols(panel[f"{entity}_growth"], X, label=entity)
        row = {f: res.loading(f).coef for f in cfg.OPERATING_FACTORS}
        row["r_squared"] = res.r_squared
        rows[entity] = row
    entities = pd.DataFrame(rows).T.reindex(cfg.OPERATING_ENTITIES)
    entities.index.name = "entity"
    return group, entities
```

- [ ] **Step 5: Regenerate and run the tests**

Run: `python3 generate_treasury_data.py && python3 -m pytest tests/ -v`
Expected: all pass.

If `test_asset_based_trucking_is_the_most_cyclical_entity` fails, the 24 actual months are fighting the modelled pre-history — raise `ENTITY_CYCLICALITY["CFS"]` and lower `["APX"]`, regenerate, re-run. If `test_freight_rates_lift_revenue_and_diesel_costs_are_a_drag` fails on significance, raise the freight coefficient in `build_operating_panel` from `beta * freight[i]` toward `1.4 * beta * freight[i]`.

- [ ] **Step 6: Commit**

```bash
git add generate_treasury_data.py treasury/analytics.py data_compact/treasury/ tests/
git commit -m "feat: add operating factor model on actual monthly ledger revenue"
```

---

### Task 6: Chart builders

**Files:**
- Create: `treasury/charts.py`
- Test: `tests/test_treasury_render.py`

**Interfaces:**
- Consumes: everything from Tasks 3–5.
- Produces: `build_all_charts(res: AnalysisResult, group, entities) -> dict[str, str]` with keys `equity`, `drawdown`, `rolling_sharpe`, `attribution`, `loadings`, `operating`. Also `AnalysisResult` and `run_full_analysis` must exist by now — add them to `analytics.py` in this task's Step 3.

- [ ] **Step 1: Write the failing test**

Create `tests/test_treasury_render.py`:

```python
"""Tests for the treasury chart and HTML rendering layers."""
from __future__ import annotations

import pathlib

import pytest

from treasury import config as cfg

pytestmark = pytest.mark.skipif(
    not cfg.RETURNS_CSV.exists(),
    reason="run `python3 generate_treasury_data.py` first",
)


@pytest.fixture(scope="module")
def analysis():
    from treasury import analytics as an
    returns = an.load_returns(cfg.RETURNS_CSV)
    return an.run_full_analysis(returns, window=cfg.DEFAULT_WINDOW, try_live=False)


def test_run_full_analysis_bundles_everything_the_page_needs(analysis):
    for attr in ("returns", "rf_daily", "perf_portfolio", "perf_spy", "capm",
                 "ff5", "ff3", "rolling_betas", "rolling_sharpe", "breaches",
                 "operating_group", "operating_entities", "factor_source",
                 "factor_is_synthetic", "window"):
        assert hasattr(analysis, attr), attr


def test_charts_are_self_contained_fragments_with_no_cdn(analysis):
    from treasury import charts
    figs = charts.build_all_charts(analysis)
    assert set(figs) == {"equity", "drawdown", "rolling_sharpe", "attribution",
                         "loadings", "operating"}
    for name, html in figs.items():
        assert html.strip(), name
        assert "cdn.plot.ly" not in html, f"{name} must not reach a CDN"
        assert "<div" in html


def test_charts_use_the_reference_dark_palette(analysis):
    from treasury import charts
    figs = charts.build_all_charts(analysis)
    assert "#4ade80" in figs["equity"]      # accent: portfolio
    assert "#60a5fa" in figs["equity"]      # accent-2: benchmark
    assert "#f87171" in figs["drawdown"]    # danger: drawdowns


def test_attribution_chart_marks_the_policy_ceiling(analysis):
    from treasury import charts
    html = charts.build_all_charts(analysis)["attribution"]
    # The mandate ceiling must be drawn, or the drift has no reference line.
    assert "1.0" in html or "mandate" in html.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_treasury_render.py -v`
Expected: FAIL — `AttributeError: module 'treasury.analytics' has no attribute 'run_full_analysis'`

- [ ] **Step 3: Add the orchestrator to `analytics.py`**

Append to `treasury/analytics.py`:

```python
# --------------------------------------------------------------------------- #
#  7. Orchestration -- one call, everything the page needs
# --------------------------------------------------------------------------- #
@dataclass
class AnalysisResult:
    returns: pd.DataFrame
    rf_daily: pd.Series
    perf_portfolio: PerformanceStats
    perf_spy: PerformanceStats
    capm: RegressionResult
    ff5: RegressionResult
    ff3: RegressionResult
    rolling_betas: pd.DataFrame
    rolling_sharpe: pd.Series
    breaches: list[Breach]
    operating_group: RegressionResult
    operating_entities: pd.DataFrame
    factor_source: str
    factor_is_synthetic: bool
    window: int


def run_full_analysis(returns: pd.DataFrame, window: int = cfg.DEFAULT_WINDOW,
                      try_live: bool = True) -> AnalysisResult:
    """Compute the whole tearsheet from a cleaned returns frame."""
    portfolio, spy = returns["portfolio_return"], returns["SPY"]

    # Factors first: the panel supplies the risk-free rate everything else uses.
    factor_data = load_factors(try_live=try_live)
    rf = factor_data.factors.get("RF")
    rf_daily = (rf.reindex(returns.index).ffill().fillna(0.0)
                if rf is not None else pd.Series(0.0, index=returns.index))

    perf_portfolio = performance_stats(portfolio, rf_daily)
    perf_spy = performance_stats(spy, rf_daily)
    capm = capm_regression(portfolio, spy, rf_daily)
    ff5 = fama_french_regression(portfolio, factor_data, cfg.FF5_FACTORS)
    ff3 = fama_french_regression(portfolio, factor_data, cfg.FF3_FACTORS)
    rolling_betas = rolling_factor_betas(portfolio, factor_data, cfg.FF5_FACTORS, window)
    roll_sharpe = rolling_sharpe(portfolio, window, rf_daily)
    breaches = policy_check(perf_portfolio, capm, ff5, rolling_betas)
    group, entities = operating_factor_model(load_operating_panel())

    return AnalysisResult(
        returns=returns, rf_daily=rf_daily,
        perf_portfolio=perf_portfolio, perf_spy=perf_spy,
        capm=capm, ff5=ff5, ff3=ff3,
        rolling_betas=rolling_betas, rolling_sharpe=roll_sharpe,
        breaches=breaches, operating_group=group, operating_entities=entities,
        factor_source=factor_data.source,
        factor_is_synthetic=factor_data.is_synthetic,
        window=window,
    )
```

- [ ] **Step 4: Write the chart builders**

Create `treasury/charts.py`:

```python
"""Plotly figures for the treasury tearsheet, as self-contained HTML fragments.

One shared dark theme, ported from the reference project's charts.py, keeps
every chart consistent with the surrounding stylesheet. Plotly's JS is injected
once by render.py rather than per figure, and never from a CDN -- this page has
to work offline.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from treasury import config as cfg
from treasury.analytics import AnalysisResult, drawdown_series, wealth_index

_ACCENT = "#4ade80"       # portfolio
_ACCENT_2 = "#60a5fa"     # benchmark
_DANGER = "#f87171"       # drawdowns and breaches
_WARN = "#fbbf24"
_MUTED = "#94a3b8"
_GRID = "rgba(148,163,184,0.12)"
_PAPER = "rgba(0,0,0,0)"
_FONT = "Inter, 'Segoe UI', system-ui, sans-serif"

_FACTOR_COLORS = {
    "Mkt-RF": "#60a5fa", "SMB": "#4ade80", "HML": "#fbbf24",
    "RMW": "#c084fc", "CMA": "#f472b6",
}
_OPERATING_COLORS = {
    "freight_rate_index": "#4ade80",
    "diesel_price": "#f87171",
    "industrial_production": "#60a5fa",
}

_CONFIG = {"displayModeBar": False, "responsive": True}


def _layout(title: str, height: int = 340) -> dict:
    return dict(
        title=dict(text=title, font=dict(size=15, color="#e2e8f0"), x=0.01,
                   xanchor="left"),
        template="plotly_dark",
        paper_bgcolor=_PAPER, plot_bgcolor=_PAPER,
        font=dict(family=_FONT, color=_MUTED, size=12),
        margin=dict(l=52, r=20, t=44, b=40),
        height=height, hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.0, xanchor="right",
                    x=1.0, bgcolor=_PAPER, font=dict(size=11)),
        xaxis=dict(gridcolor=_GRID, zeroline=False),
        yaxis=dict(gridcolor=_GRID, zeroline=False),
    )


def _html(fig: go.Figure, div_id: str) -> str:
    # include_plotlyjs=False: render.py inlines the library once for the page.
    return fig.to_html(full_html=False, include_plotlyjs=False,
                       config=_CONFIG, div_id=div_id)


def build_equity_curve(res: AnalysisResult) -> str:
    port = wealth_index(res.returns["portfolio_return"])
    spy = wealth_index(res.returns["SPY"])
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=port.index, y=port.values, name="Treasury portfolio",
                             mode="lines", line=dict(color=_ACCENT, width=2.2),
                             fill="tozeroy", fillcolor="rgba(74,222,128,0.08)"))
    fig.add_trace(go.Scatter(x=spy.index, y=spy.values, name="SPY", mode="lines",
                             line=dict(color=_ACCENT_2, width=1.8, dash="dot")))
    fig.update_layout(**_layout("Equity Curve — Growth of $1"))
    fig.update_yaxes(tickprefix="$")
    return _html(fig, "chart-equity")


def build_drawdown(res: AnalysisResult) -> str:
    dd = drawdown_series(res.returns["portfolio_return"]) * 100.0
    limit = -cfg.POLICY["max_drawdown"] * 100.0
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=dd.index, y=dd.values, name="Drawdown", mode="lines",
                             line=dict(color=_DANGER, width=1.4), fill="tozeroy",
                             fillcolor="rgba(248,113,113,0.20)"))
    fig.add_hline(y=limit, line=dict(color=_WARN, width=1, dash="dash"),
                  annotation_text=f"policy limit {limit:.0f}%",
                  annotation_font=dict(color=_WARN, size=10))
    fig.update_layout(**_layout("Underwater Plot — Drawdown from Peak"))
    fig.update_yaxes(ticksuffix="%")
    return _html(fig, "chart-drawdown")


def build_rolling_sharpe(res: AnalysisResult) -> str:
    rs = res.rolling_sharpe.dropna()
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=rs.index, y=rs.values, name="Rolling Sharpe",
                             mode="lines", line=dict(color=_WARN, width=1.8),
                             fill="tozeroy", fillcolor="rgba(251,191,36,0.08)"))
    fig.add_hline(y=1.0, line=dict(color="rgba(148,163,184,0.5)", width=1, dash="dash"))
    fig.update_layout(**_layout(f"Rolling Sharpe Ratio ({res.window}-day window)"))
    return _html(fig, "chart-rollsharpe")


def build_rolling_attribution(res: AnalysisResult) -> str:
    """Rolling factor betas -- the chart that catches the mandate drift."""
    betas = res.rolling_betas
    fig = go.Figure()
    for col in betas.columns:
        fig.add_trace(go.Scatter(x=betas.index, y=betas[col], name=col, mode="lines",
                                 line=dict(color=_FACTOR_COLORS.get(col, _MUTED),
                                           width=1.8)))
    fig.add_hline(y=0.0, line=dict(color="rgba(148,163,184,0.4)", width=1))
    fig.add_hline(y=cfg.POLICY["max_beta"], line=dict(color=_DANGER, width=1.2,
                                                      dash="dash"),
                  annotation_text=f"mandate beta ceiling {cfg.POLICY['max_beta']:.1f}",
                  annotation_font=dict(color=_DANGER, size=10))
    fig.update_layout(**_layout(
        f"Rolling Fama-French Factor Betas ({res.window}-day window)", height=390))
    return _html(fig, "chart-attribution")


def build_factor_loadings_bar(res: AnalysisResult) -> str:
    loadings = [l for l in res.ff5.loadings if l.name != "Alpha"]
    names = [l.name for l in loadings]
    coefs = [l.coef for l in loadings]
    fig = go.Figure(go.Bar(
        x=names, y=coefs,
        marker=dict(color=[_FACTOR_COLORS.get(n, _MUTED) for n in names],
                    opacity=[1.0 if l.significant else 0.35 for l in loadings]),
        text=[f"{c:+.2f}" for c in coefs], textposition="outside",
        hovertext=[f"t={l.tstat:.2f}, p={l.pvalue:.3f}" for l in loadings]))
    fig.add_hline(y=0.0, line=dict(color="rgba(148,163,184,0.4)", width=1))
    fig.update_layout(**_layout("Fama-French 5-Factor Loadings (β)"))
    return _html(fig, "chart-loadings")


def build_operating_loadings(res: AnalysisResult) -> str:
    """Per-entity revenue sensitivity to the freight cycle."""
    ent = res.operating_entities
    fig = go.Figure()
    for factor in cfg.OPERATING_FACTORS:
        fig.add_trace(go.Bar(
            x=list(ent.index), y=ent[factor].astype(float),
            name=factor.replace("_", " "),
            marker_color=_OPERATING_COLORS.get(factor, _MUTED)))
    fig.add_hline(y=0.0, line=dict(color="rgba(148,163,184,0.4)", width=1))
    fig.update_layout(**_layout(
        "Revenue Sensitivity by Entity — Operating Factor Loadings", height=360))
    fig.update_layout(barmode="group")
    return _html(fig, "chart-operating")


def build_all_charts(res: AnalysisResult) -> dict[str, str]:
    return {
        "equity": build_equity_curve(res),
        "drawdown": build_drawdown(res),
        "rolling_sharpe": build_rolling_sharpe(res),
        "attribution": build_rolling_attribution(res),
        "loadings": build_factor_loadings_bar(res),
        "operating": build_operating_loadings(res),
    }
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python3 -m pytest tests/ -v`
Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add treasury/analytics.py treasury/charts.py tests/test_treasury_render.py
git commit -m "feat: add treasury chart builders and analysis orchestrator"
```

---

### Task 7: Templates, stylesheet, and renderer

**Files:**
- Create: `treasury/templates/base.html`, `treasury/templates/tearsheet.html`, `treasury/static/css/style.css`, `treasury/render.py`
- Modify: `tests/test_treasury_render.py` (append)
- Create (generated): `treasury-tearsheet-jul2026.html`

**Interfaces:**
- Consumes: `AnalysisResult` and `build_all_charts` from Task 6.
- Produces: `render_tearsheet(res: AnalysisResult) -> str` and `write_artifact(res: AnalysisResult, path=cfg.ARTIFACT_HTML) -> pathlib.Path`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_treasury_render.py`:

```python
# ---------------------------------------------------------------- renderer -- #
@pytest.fixture(scope="module")
def page(analysis) -> str:
    from treasury import render
    return render.render_tearsheet(analysis)


def test_page_is_self_contained_and_offline(page):
    assert page.lstrip().startswith("<!DOCTYPE html>")
    for external in ("cdn.plot.ly", "fonts.googleapis.com", "http://", "https://"):
        assert external not in page, f"page must not reference {external}"
    assert "Plotly.newPlot" in page, "Plotly JS must be inlined"


def test_page_carries_the_reference_layout_classes(page):
    for cls in ("results-head", "results-title", "cards-grid", "metric-card",
                "charts-grid", "panel-wide", "benchmark-panel", "factor-table",
                "divider-row", "tables-grid", "bg-grid", "topbar"):
        assert cls in page, cls


def test_page_declares_the_reference_palette(page):
    for colour in ("#0a0e17", "rgba(20, 27, 45, 0.72)", "#4ade80", "#60a5fa",
                   "#f87171", "#fbbf24"):
        assert colour in page, colour


def test_page_labels_the_modelled_factor_source(page):
    """Honesty requirement: modelled factors must never pass as market data."""
    assert "banner-warn" in page
    assert "MODELLED" in page


def test_page_reports_all_three_policy_breaches_with_owners(page, analysis):
    assert "banner-danger" in page
    assert "3 breaches" in page.lower()
    for b in analysis.breaches:
        assert b.check in page
        assert b.owner in page
        assert b.due in page


def test_page_includes_both_factor_tables_and_the_operating_section(page):
    assert "Fama-French 5-Factor" in page
    assert "Fama-French 3-Factor" in page
    assert "CAPM" in page
    assert "Operating Factor Model" in page
    for entity in cfg.OPERATING_ENTITIES:
        assert entity in page


def test_page_states_the_observation_count_and_date_range(page, analysis):
    assert str(len(analysis.returns)) in page
    assert "2024" in page and "2026" in page


def test_write_artifact_produces_a_committable_file(analysis, tmp_path):
    from treasury import render
    out = render.write_artifact(analysis, tmp_path / "tearsheet.html")
    assert out.exists()
    assert out.stat().st_size > 500_000, "Plotly is inlined, so expect a large file"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_treasury_render.py -k page -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'treasury.render'`

- [ ] **Step 3: Port the stylesheet**

Create `treasury/static/css/style.css` by copying the reference project's
`static/css/style.css` verbatim, then applying exactly these changes:

1. Delete the `.hero`, `.hero-title`, `.hero-sub`, `.grad`, `.upload-card`,
   `.dropzone*`, `.dz-*`, `.controls-row`, `.control`, `.control-label`,
   `.btn-group`, `.btn*`, `.alert`, `.format-note`, `.code-sample`,
   `.format-hint`, `.explain-grid` and `.explain-card` rules — this page has no
   landing screen or upload form.
2. Replace the `@import`/font-family declarations with system stacks, since no
   network is available:
   ```css
   body { font-family: "Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif; }
   :root { --mono: ui-monospace, "SF Mono", SFMono-Regular, Menlo, Consolas, monospace; }
   ```
3. Add these rules at the end, for the policy banner and the compliance table:
   ```css
   /* ---------- Policy breach banner ---------- */
   .banner-danger {
     background: rgba(248, 113, 113, 0.10);
     border: 1px solid rgba(248, 113, 113, 0.45);
     color: #fecaca;
   }
   .breach-list { list-style: none; margin: 10px 0 0; padding: 0; display: grid; gap: 10px; }
   .breach {
     display: grid;
     grid-template-columns: minmax(180px, 220px) 1fr;
     gap: 4px 18px;
     padding: 12px 0 0;
     border-top: 1px solid rgba(248, 113, 113, 0.22);
   }
   .breach:first-child { border-top: none; padding-top: 4px; }
   .breach-head { font-weight: 600; color: var(--text); }
   .breach-nums { font-family: var(--mono); font-size: 12.5px; color: var(--warn); }
   .breach-body p { margin: 0 0 4px; font-size: 13px; }
   .breach-body .risk { color: #fca5a5; }
   .breach-action { font-size: 12.5px; color: var(--muted); }
   .breach-action strong { color: var(--accent-2); }
   .breach-cash { font-family: var(--mono); color: var(--danger); font-weight: 600; }
   .ok { color: var(--accent); }

   /* ---------- Section divider ---------- */
   .section-head {
     margin: 34px 0 18px;
     padding-top: 26px;
     border-top: 1px solid var(--panel-border);
   }
   .section-head h2 { font-size: 21px; font-weight: 700; }
   .section-head p { color: var(--muted); font-size: 13.5px; margin-top: 4px; }
   .entity-table { width: 100%; border-collapse: collapse; font-size: 13.5px; }
   .entity-table th, .entity-table td {
     padding: 9px 10px; text-align: right;
     border-bottom: 1px solid rgba(148, 163, 184, 0.07);
   }
   .entity-table th { color: var(--muted); font-size: 12px; text-transform: uppercase; }
   .entity-table td:first-child, .entity-table th:first-child { text-align: left; }
   .entity-table .mono { font-family: var(--mono); }
   ```

- [ ] **Step 4: Write the templates**

Create `treasury/templates/base.html`:

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{% block title %}AI DOF — Treasury Tearsheet{% endblock %}</title>
  <style>{{ inline_css }}</style>
  <script>{{ inline_plotly }}</script>
</head>
<body>
  <div class="bg-grid"></div>
  <header class="topbar">
    <span class="brand">
      <span class="brand-mark">◆</span>
      <span class="brand-name">AI DOF<span class="brand-accent">TREASURY</span></span>
    </span>
    <div class="topbar-tag">Portfolio Performance &amp; Factor Analysis</div>
  </header>
  <main class="container">
    {% block content %}{% endblock %}
  </main>
  <footer class="footer">
    <span>Meridian Holdings Group is fictional and every figure here is synthetic.
    Educational project — not investment advice.</span>
  </footer>
</body>
</html>
```

Create `treasury/templates/tearsheet.html`:

```html
{% extends "base.html" %}
{% block content %}
<div class="results-head">
  <div>
    <h1 class="results-title">Treasury Portfolio Tearsheet</h1>
    <p class="results-meta">
      {{ n_obs }} daily observations · {{ start_date }} → {{ end_date }} ·
      {{ window }}d rolling window · {{ notional }} under management
    </p>
  </div>
</div>

{% if factor_is_synthetic %}
<div class="banner banner-warn">
  ⚠ Fama-French factors are a <strong>MODELLED</strong> panel committed to this repo,
  not real market data — so the page renders identically offline. Factor loadings below
  are illustrative of the technique.
</div>
{% else %}
<div class="banner banner-info">
  Factor data source: <strong>{{ factor_source }}</strong>
</div>
{% endif %}

<div class="banner banner-danger">
  <strong>Treasury investment policy — {{ breach_count }} breaches</strong>
  <ul class="breach-list">
    {% for b in breaches %}
    <li class="breach">
      <div>
        <div class="breach-head">{{ b.check }}</div>
        <div class="breach-nums">
          {{ b.observed }} vs limit {{ b.limit }}
          {% if b.breached %}✗{% else %}<span class="ok">✓</span>{% endif %}
        </div>
        <div class="breach-nums breach-cash">{{ b.cash }}</div>
      </div>
      <div class="breach-body">
        <p>{{ b.why }}</p>
        <p class="risk">{{ b.risk }}</p>
        <p class="breach-action">{{ b.action }}
          · <strong>{{ b.owner }}</strong> · by {{ b.due }}</p>
      </div>
    </li>
    {% endfor %}
  </ul>
</div>

<section class="cards-grid">
  {% for c in cards %}
  <div class="metric-card">
    <div class="metric-label">{{ c.label }}</div>
    <div class="metric-value
      {%- if c.positive is not none %}{% if c.positive %} pos{% else %} neg{% endif %}{% endif %}">
      {{ c.value }}
    </div>
    <div class="metric-hint">{{ c.hint }}</div>
  </div>
  {% endfor %}
</section>

<section class="charts-grid">
  <div class="panel panel-wide">{{ chart_html.equity | safe }}</div>
  <div class="panel">{{ chart_html.drawdown | safe }}</div>
  <div class="panel">{{ chart_html.rolling_sharpe | safe }}</div>
  <div class="panel panel-wide">{{ chart_html.attribution | safe }}</div>
  <div class="panel">{{ chart_html.loadings | safe }}</div>
  <div class="panel benchmark-panel">
    <h3 class="panel-title">SPY Benchmark</h3>
    <table class="bench-table">
      <tr><td>CAGR</td><td>{{ spy_stats.cagr }}</td></tr>
      <tr><td>Volatility</td><td>{{ spy_stats.vol }}</td></tr>
      <tr><td>Sharpe</td><td>{{ spy_stats.sharpe }}</td></tr>
      <tr><td>Max Drawdown</td><td>{{ spy_stats.mdd }}</td></tr>
    </table>
  </div>
</section>

<section class="tables-grid">
  <div class="panel">
    <h3 class="panel-title">Fama-French 5-Factor Regression
      <span class="panel-sub">R² = {{ '%.3f' % ff5_r2 }}</span>
    </h3>
    <table class="factor-table">
      <thead>
        <tr><th>Factor</th><th>β / coef</th><th>Annualized</th><th>t-stat</th><th>p-value</th></tr>
      </thead>
      <tbody>
        {% for r in ff5_rows %}
        <tr class="{{ 'sig' if r.significant else 'insig' }}">
          <td class="fac-name" title="{{ r.description }}">{{ r.name }}</td>
          <td class="mono">{{ r.coef }}</td>
          <td class="mono">{{ r.annualized }}</td>
          <td class="mono">{{ r.tstat }}</td>
          <td class="mono">{{ r.pvalue }}{% if r.significant %} <span class="star">★</span>{% endif %}</td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
    <p class="table-note">★ significant at the 5% level (p &lt; 0.05).</p>
  </div>

  <div class="panel">
    <h3 class="panel-title">Fama-French 3-Factor &amp; CAPM
      <span class="panel-sub">FF3 R² = {{ '%.3f' % ff3_r2 }}</span>
    </h3>
    <table class="factor-table">
      <thead>
        <tr><th>Factor</th><th>β / coef</th><th>Annualized</th><th>t-stat</th><th>p-value</th></tr>
      </thead>
      <tbody>
        {% for r in ff3_rows %}
        <tr class="{{ 'sig' if r.significant else 'insig' }}">
          <td class="fac-name" title="{{ r.description }}">{{ r.name }}</td>
          <td class="mono">{{ r.coef }}</td>
          <td class="mono">{{ r.annualized }}</td>
          <td class="mono">{{ r.tstat }}</td>
          <td class="mono">{{ r.pvalue }}{% if r.significant %} <span class="star">★</span>{% endif %}</td>
        </tr>
        {% endfor %}
        <tr class="divider-row"><td colspan="5">CAPM (vs SPY)</td></tr>
        {% for r in capm_rows %}
        <tr class="{{ 'sig' if r.significant else 'insig' }}">
          <td class="fac-name" title="{{ r.description }}">{{ r.name }}</td>
          <td class="mono">{{ r.coef }}</td>
          <td class="mono">{{ r.annualized }}</td>
          <td class="mono">{{ r.tstat }}</td>
          <td class="mono">{{ r.pvalue }}{% if r.significant %} <span class="star">★</span>{% endif %}</td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
    <p class="table-note">
      CAPM alpha of {{ capm_alpha }} against FF5 alpha of {{ ff5_alpha }}: the gap is
      style premia a single market factor cannot see, not skill.
    </p>
  </div>
</section>

<div class="section-head">
  <h2>2 · Operating Factor Model</h2>
  <p>
    The same technique pointed at the group's own revenue. {{ operating_n }} monthly
    observations — the last 24 are <strong>actual</strong> ledger revenue, the earlier
    months are MODELLED pre-history, since three factors cannot be estimated from 24
    points.
  </p>
</div>

<section class="tables-grid">
  <div class="panel">
    <h3 class="panel-title">Group Revenue Growth
      <span class="panel-sub">R² = {{ '%.3f' % operating_r2 }}</span>
    </h3>
    <table class="factor-table">
      <thead>
        <tr><th>Factor</th><th>Coef</th><th>t-stat</th><th>p-value</th></tr>
      </thead>
      <tbody>
        {% for r in operating_rows %}
        <tr class="{{ 'sig' if r.significant else 'insig' }}">
          <td class="fac-name" title="{{ r.description }}">{{ r.name }}</td>
          <td class="mono">{{ r.coef }}</td>
          <td class="mono">{{ r.tstat }}</td>
          <td class="mono">{{ r.pvalue }}{% if r.significant %} <span class="star">★</span>{% endif %}</td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
  </div>
  <div class="panel">
    <h3 class="panel-title">Revenue Beta by Entity</h3>
    <table class="entity-table">
      <thead>
        <tr><th>Entity</th><th>Freight rate</th><th>Diesel</th><th>Ind. prod.</th><th>R²</th></tr>
      </thead>
      <tbody>
        {% for r in entity_rows %}
        <tr>
          <td>{{ r.entity }}</td>
          <td class="mono">{{ r.freight }}</td>
          <td class="mono">{{ r.diesel }}</td>
          <td class="mono">{{ r.indpro }}</td>
          <td class="mono">{{ r.r2 }}</td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
    <p class="table-note">{{ operating_note }}</p>
  </div>
  <div class="panel panel-wide">{{ chart_html.operating | safe }}</div>
</section>
{% endblock %}
```

- [ ] **Step 5: Write the renderer**

Create `treasury/render.py`:

```python
"""Render the treasury tearsheet to one self-contained HTML page.

The stylesheet and Plotly's JS are inlined, so the output works offline, in an
email client and in print -- the same constraint the CFO review dashboard in this
repo is built to. This module formats and assembles only; every number arrives
already computed on an AnalysisResult.
"""
from __future__ import annotations

import pathlib

from jinja2 import Environment, FileSystemLoader, select_autoescape

from treasury import charts, config as cfg
from treasury.analytics import AnalysisResult, _money

_HERE = pathlib.Path(__file__).resolve().parent
_TEMPLATES = _HERE / "templates"
_CSS = _HERE / "static" / "css" / "style.css"


def _plotly_js() -> str:
    """Plotly's minified bundle, read from the installed package.

    Inlined rather than pulled from a CDN: this page must render with no network.
    """
    import plotly.offline
    path = pathlib.Path(plotly.offline.offline.__file__).parent / "package_data" / "plotly.min.js"
    if not path.exists():                       # layout differs across versions
        import plotly
        candidates = list(pathlib.Path(plotly.__file__).parent.rglob("plotly.min.js"))
        if not candidates:
            raise FileNotFoundError("Could not locate plotly.min.js to inline.")
        path = candidates[0]
    return path.read_text(encoding="utf-8")


def _env() -> Environment:
    return Environment(
        loader=FileSystemLoader(_TEMPLATES),
        autoescape=select_autoescape(["html"]),
    )


def _pct(v: float, dp: int = 2) -> str:
    return "—" if v != v else f"{v:.{dp}%}"


def _num(v: float, dp: int = 2) -> str:
    return "—" if v != v else f"{v:.{dp}f}"


def _loading_rows(result) -> list[dict]:
    return [{
        "name": l.name,
        "coef": _num(l.coef, 4),
        "annualized": _pct(l.annualized) if l.annualized is not None else "—",
        "tstat": _num(l.tstat),
        "pvalue": f"{l.pvalue:.3f}",
        "significant": l.significant,
        "description": l.description,
    } for l in result.loadings]


def _cards(res: AnalysisResult) -> list[dict]:
    p = res.perf_portfolio
    beta = res.capm.loading("Beta (Market)")
    net_alpha = res.ff5.alpha_annualized
    return [
        dict(label="CAGR", value=_pct(p.cagr), positive=p.cagr > 0,
             hint="annualized geometric growth"),
        dict(label="Volatility", value=_pct(p.ann_vol), positive=None,
             hint="annualized, √252 scaling"),
        dict(label="Sharpe", value=_num(p.sharpe), positive=p.sharpe > 1,
             hint="excess return per unit of total risk"),
        dict(label="Sortino", value=_num(p.sortino), positive=p.sortino > 1,
             hint="downside risk only"),
        dict(label="Max drawdown", value=_pct(p.max_drawdown, 1),
             positive=abs(p.max_drawdown) < cfg.POLICY["max_drawdown"],
             hint=f"policy limit −{cfg.POLICY['max_drawdown']:.0%}"),
        dict(label="Beta (full period)", value=_num(beta.coef if beta else float('nan'), 3),
             positive=(beta.coef < cfg.POLICY["max_beta"]) if beta else None,
             hint="hides the rolling breach"),
        dict(label="FF5 alpha, net", value=_pct(net_alpha), positive=net_alpha > 0,
             hint=f"after the {cfg.FEE_ANNUAL:.2%} fee"),
        dict(label="Hit rate", value=_pct(p.hit_rate, 1), positive=None,
             hint=f"best {p.best_day:+.2%} / worst {p.worst_day:+.2%}"),
    ]


def _view_model(res: AnalysisResult) -> dict:
    ent = res.operating_entities
    most_cyclical = ent["freight_rate_index"].astype(float).idxmax()
    return dict(
        inline_css=_CSS.read_text(encoding="utf-8"),
        inline_plotly=_plotly_js(),
        chart_html=charts.build_all_charts(res),
        n_obs=len(res.returns),
        start_date=res.returns.index.min().strftime("%d %b %Y"),
        end_date=res.returns.index.max().strftime("%d %b %Y"),
        window=res.window,
        notional=_money(cfg.PORTFOLIO_NOTIONAL),
        factor_source=res.factor_source,
        factor_is_synthetic=res.factor_is_synthetic,
        breach_count=sum(1 for b in res.breaches if b.breached),
        breaches=[dict(check=b.check, limit=b.limit, observed=b.observed,
                       breached=b.breached, cash=_money(b.cash_at_risk),
                       why=b.why, risk=b.risk, action=b.action,
                       owner=b.owner, due=b.due) for b in res.breaches],
        cards=_cards(res),
        spy_stats=dict(cagr=_pct(res.perf_spy.cagr), vol=_pct(res.perf_spy.ann_vol),
                       sharpe=_num(res.perf_spy.sharpe),
                       mdd=_pct(res.perf_spy.max_drawdown, 1)),
        ff5_rows=_loading_rows(res.ff5), ff5_r2=res.ff5.r_squared,
        ff3_rows=_loading_rows(res.ff3), ff3_r2=res.ff3.r_squared,
        capm_rows=_loading_rows(res.capm),
        capm_alpha=_pct(res.capm.alpha_annualized),
        ff5_alpha=_pct(res.ff5.alpha_annualized),
        operating_rows=_loading_rows(res.operating_group),
        operating_r2=res.operating_group.r_squared,
        operating_n=res.operating_group.nobs,
        entity_rows=[dict(entity=e,
                          freight=_num(float(ent.loc[e, "freight_rate_index"]), 2),
                          diesel=_num(float(ent.loc[e, "diesel_price"]), 2),
                          indpro=_num(float(ent.loc[e, "industrial_production"]), 2),
                          r2=_num(float(ent.loc[e, "r_squared"]), 3))
                     for e in ent.index],
        operating_note=(
            f"{most_cyclical} carries the highest freight-rate beta, so a downturn "
            f"in spot rates lands there first and hardest."),
    )


def render_tearsheet(res: AnalysisResult) -> str:
    """The complete page as one self-contained HTML string."""
    return _env().get_template("tearsheet.html").render(**_view_model(res))


def write_artifact(res: AnalysisResult, path=None) -> pathlib.Path:
    """Write the page to disk as a committable portfolio artifact."""
    path = pathlib.Path(path or cfg.ARTIFACT_HTML)
    path.write_text(render_tearsheet(res), encoding="utf-8")
    return path
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_treasury_render.py -v`
Expected: all pass.

If `test_page_is_self_contained_and_offline` fails on `https://`, find the offending
reference (most likely a leftover font `@import` in the stylesheet, or a Plotly
`annotation` link) and remove it. If `_plotly_js` raises, run
`python3 -c "import plotly, pathlib; print([str(p) for p in pathlib.Path(plotly.__file__).parent.rglob('plotly.min.js')])"`
and adjust the path in `_plotly_js`.

- [ ] **Step 7: Generate the artifact and commit**

```bash
python3 -c "
from treasury import analytics as an, render, config as cfg
res = an.run_full_analysis(an.load_returns(cfg.RETURNS_CSV), try_live=False)
print(render.write_artifact(res))
"
git add treasury/render.py treasury/templates/ treasury/static/ treasury-tearsheet-jul2026.html tests/test_treasury_render.py
git commit -m "feat: render self-contained treasury tearsheet from ported templates"
```

---

### Task 8: Streamlit page and documentation

**Files:**
- Modify: `streamlit_app.py:297-298` (sidebar radio), and append a new page branch before the final `st.sidebar.markdown("---")` at `streamlit_app.py:463`
- Modify: `README.md`
- Test: manual, via the running app

**Interfaces:**
- Consumes: `treasury.analytics.load_returns`, `run_full_analysis`, `treasury.render.render_tearsheet`, `treasury.config`.
- Produces: nothing downstream. This is the top of the stack.

- [ ] **Step 1: Add the sidebar entry**

In `streamlit_app.py`, change the page list:

```python
page = st.sidebar.radio(
    "View", ["Overview", "Financial statements", "Budget tracker",
             "Receivables & risk", "Treasury & factors", "Details"])
```

- [ ] **Step 2: Add the cached loader near the other loaders**

Insert after the `ar_analysis` function (around `streamlit_app.py:255`):

```python
@st.cache_data(show_spinner="Running the factor regressions…")
def treasury_tearsheet(window: int) -> str:
    """Full treasury analysis, rendered to a self-contained HTML page.

    Cached per window: the rolling regressions re-fit on every window change and
    cost a second or two.
    """
    from treasury import analytics as tan, config as tcfg, render as trender

    returns = tan.load_returns(tcfg.RETURNS_CSV)
    res = tan.run_full_analysis(returns, window=window, try_live=False)
    return trender.render_tearsheet(res)
```

- [ ] **Step 3: Add the page body**

Insert before the closing `st.sidebar.markdown("---")` at the end of the file,
after the `Details` branch:

```python
# --------------------------------------------------- Treasury & factors --- #
elif page == "Treasury & factors":
    from treasury import config as tcfg

    st.title("Treasury portfolio & factor analysis")
    st.caption(
        "Meridian's excess cash under management · CAPM, Fama-French 3- and "
        "5-factor regressions, rolling factor betas and investment-policy "
        "compliance · the operating factor model sits in section 2")

    if not tcfg.RETURNS_CSV.exists():
        st.error(
            "Treasury data not found. Generate it with:\n\n"
            "```\npython3 generate_treasury_data.py\n```")
    else:
        window = st.radio(
            "Rolling window", tcfg.ALLOWED_WINDOWS,
            index=tcfg.ALLOWED_WINDOWS.index(tcfg.DEFAULT_WINDOW),
            format_func=lambda w: f"{w} days",
            horizontal=True,
            help="63 trading days ≈ one quarter. Shorter windows react faster to "
                 "style drift; longer ones are less noisy.")
        st.markdown(
            "The portfolio's full-period beta sits inside the 1.00 mandate ceiling. "
            "The rolling window does not — which is the point of the page.")
        components.html(treasury_tearsheet(window), height=3600, scrolling=True)
```

- [ ] **Step 4: Verify in the running app**

Run: `python3 -m streamlit run streamlit_app.py`

Check, in the browser:
1. "Treasury & factors" appears in the sidebar and opens without error.
2. The page renders dark, with the topbar, grid backdrop and translucent panels.
3. The red policy banner lists three breaches, each with a cash figure, an owner and a date.
4. The amber factor-source banner says MODELLED.
5. All six charts draw. The rolling-beta chart crosses the red mandate ceiling in 2026.
6. Both factor tables render, with ★ on significant loadings.
7. Section 2 shows the group regression, the per-entity table and the entity chart.
8. Switching the window to 21 and 126 days re-renders with a different rolling series.
9. The other four pages still work and are still light-themed.

Fix anything broken before continuing. If the embed is cut off vertically, raise the
`height=3600` argument.

- [ ] **Step 5: Update the README**

In `README.md`, add to the repository-contents tree:

```
├── treasury/                            Treasury tearsheet (analytics, charts, templates)
├── generate_treasury_data.py            Deterministic synthetic-data generator
├── data_compact/treasury/               Committed generated data (3 CSVs)
└── treasury-tearsheet-jul2026.html      Rendered tearsheet, self-contained
```

And add this section after "The analytical layer":

```markdown
## Treasury & factor analysis

A fifth view applies quantitative portfolio analysis to the group's treasury: CAPM,
Fama-French 3- and 5-factor regressions, rolling factor betas, rolling Sharpe, an
underwater plot, and compliance against a stated investment policy. A second section
turns the same machinery on Meridian's own revenue, regressing monthly growth on
freight-rate, diesel and industrial-production factors.

The layout and stylesheet are ported from the Quant Guild Library's "Intro — Trading
Dashboard" teaching project. The page is rendered to a single self-contained HTML file
with no CDN dependency, embedded in the Streamlit app and committed as
`treasury-tearsheet-jul2026.html`.

**Three findings are planted, in the same spirit as the ledger's sixteen:**

1. **Mandate drift.** The portfolio rotates from defensive value into high-beta
   small-cap growth in FY2026. The full-period beta is 0.94 and looks compliant against
   the 1.00 ceiling; only the 63-day rolling beta shows the breach. An annual report
   would miss it.
2. **Drawdown past policy.** Maximum drawdown breaches the 10% capital-preservation
   limit, on cash the group holds for operating liquidity rather than for a risk premium.
3. **Alpha that was never there.** CAPM reports roughly +2% annualized alpha. That is
   the SMB, HML and RMW premia, which a single market factor cannot see. Controlling for
   all five factors leaves alpha near zero, and negative once the 45bp fee is netted.

Portfolio returns, the factor panel and the pre-2024 operating history are **MODELLED**
and generated deterministically by `generate_treasury_data.py`. The last 24 months of
monthly revenue are **actual** ledger figures from `data_compact/csv/Invoices.csv`. The
returns CSV uses the same `date,portfolio_return,SPY` schema as the reference project,
so the two files are interchangeable.

Run the tests with `python3 -m pytest tests/ -v`.
```

- [ ] **Step 6: Full verification and commit**

```bash
python3 -m pytest tests/ -v
git add streamlit_app.py README.md
git commit -m "feat: add treasury & factors page to the command centre"
```
Expected: every test passes before committing.

---

## Self-Review

**Spec coverage.** Every spec section maps to a task: architecture and the import rule → Tasks 1, 3 (enforced by `test_analytics_does_not_import_presentation_libraries`); the three data files → Tasks 2, 5; schema interchangeability with the reference CSV → Task 2 tests plus Task 3's `test_load_returns_parses_reference_style_csv`; the analytics API → Tasks 3–6; factor source and banner → Task 3 `load_factors`, Task 7 banner test; policy checks with cash sizing → Task 4; the layout table → Task 7 templates; no CDN → Task 7 `test_page_is_self_contained_and_offline`; error handling → `load_returns` validation, `_load_committed_panel` FileNotFoundError, empty-frame rolling betas, Task 8's missing-data branch; the five spec tests → Tasks 2–5; deliverables 1–6 → Tasks 2, 3–7, 7, 7, 2–6, 8.

**Deviations from the spec, deliberate.** The operating panel holds 59 rows, not 60 — the first month has no prior month and therefore no growth rate. Task 5 Step 3 says so and corrects the test. `PORTFOLIO_NOTIONAL` and `ENTITY_CYCLICALITY` are named in the plan but only described in the spec.

**Placeholder scan.** No TBDs. The two tuning loops (Task 2 Step 4, Task 5 Step 5) specify which constant to change in which direction and the band to hit, rather than saying "calibrate as needed". Task 7 Step 3 lists the exact CSS rules to delete, replace and add rather than "adapt the stylesheet".

**Type consistency.** `FactorData`, `FactorLoading`, `RegressionResult`, `PerformanceStats`, `Breach` and `AnalysisResult` are defined once and used with the same field names throughout. `cfg.DEFAULT_WINDOW` is the single default window. `_money` is defined in `analytics.py` and imported by `render.py` rather than duplicated. `load_factors(try_live=...)` and `run_full_analysis(..., try_live=...)` agree. Chart keys `equity, drawdown, rolling_sharpe, attribution, loadings, operating` match between `build_all_charts`, the Task 6 test and the template.

**One known risk.** `_plotly_js()` locates `plotly.min.js` inside the installed package, whose layout has changed between Plotly versions. Task 7 Step 6 includes the one-line diagnostic and the fallback `rglob` is already in the code.
