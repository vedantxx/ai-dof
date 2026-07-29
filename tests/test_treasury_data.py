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
    # The generator rounds to 6dp before writing, so the file carries 0.000171
    # rather than the exact 0.00017063. Compare against what the file must hold.
    expected_rf = round(cfg.RF_ANNUAL / cfg.TRADING_DAYS_PER_YEAR, 6)
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
