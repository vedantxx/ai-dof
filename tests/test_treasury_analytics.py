"""Tests for the treasury analytics layer."""
from __future__ import annotations

import pathlib

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
        assert b.cash_at_risk < an.investable_notional()
        assert b.why and b.risk and b.action and b.owner and b.due


def test_beta_breach_is_sized_off_the_market_stress_assumption(breaches):
    beta_breach = breaches[0]
    # excess beta x stress x notional
    assert beta_breach.cash_at_risk == pytest.approx(
        (float(beta_breach.observed) - cfg.POLICY["max_beta"])
        * cfg.POLICY["market_stress"] * an.investable_notional(), rel=0.01)


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


# -------------------------------------------------------- operating model -- #
def test_operating_factor_model_returns_group_and_entity_loadings():
    panel = an.load_operating_panel()
    group, entities = an.operating_factor_model(panel)
    assert group.nobs == 59, "60 months of levels give 59 growth observations"
    assert {l.name for l in group.loadings} == {
        "Alpha", *cfg.OPERATING_FACTOR_LABELS.values()}
    assert list(entities.index) == cfg.OPERATING_ENTITIES
    assert list(entities.columns) == ["freight_beta", "tstat", "r_squared"]


def test_freight_rates_lift_revenue_and_diesel_costs_are_a_drag():
    """Signs must be economically sensible, or the section is noise."""
    panel = an.load_operating_panel()
    group, _ = an.operating_factor_model(panel)
    assert group.loading("Freight rate index").coef > 0
    assert group.loading("Freight rate index").significant
    assert group.loading("Diesel price").coef < 0


def test_the_cycle_amplifying_entities_are_the_ones_the_ledger_identifies():
    """Which entities amplify the freight cycle is DERIVED from actual ledger
    revenue, not assumed.

    Deliberately tests the PAIR rather than the single argmax. MLG and CFS come
    out within 0.02 of each other on the pooled sample -- statistically
    indistinguishable, and the ordering flips between the actual window and the
    modelled pre-history. Asserting a winner on a 0.02 gap would be a test of
    sampling noise. The robust fact is the ~0.3 gap between the freight-exposed
    pair and the contract-based pair.
    """
    panel = an.load_operating_panel()
    _, entities = an.operating_factor_model(panel)
    betas = entities["freight_beta"].astype(float).sort_values(ascending=False)

    actual = panel[panel["is_actual"] == 1]
    f = actual["freight_rate_index"].to_numpy()
    from_actual = {
        e: float(np.cov(actual[f"{e}_growth"].to_numpy(), f, ddof=1)[0, 1]
                 / np.var(f, ddof=1))
        for e in cfg.OPERATING_ENTITIES
    }
    top_actual = set(sorted(from_actual, key=from_actual.get, reverse=True)[:2])
    assert set(betas.index[:2]) == top_actual, f"{betas.to_dict()} vs {from_actual}"

    # And the separation between the pairs must be material, or the section
    # says nothing about who is exposed.
    assert betas.iloc[1] - betas.iloc[2] > 0.2, f"pairs not separated: {betas.to_dict()}"
